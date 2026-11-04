"""ChatClaudeCodeHeadless 유닛 테스트.

Task 1a (#2): 기본 subprocess 래퍼
Task 1b (#3): with_structured_output → --json-schema 매핑
Task 1c (#4): 격리 플래그 전체 세트 + SystemMessage 분리 전달
Task 1d (#5): 동시 실행 세마포어
Task 1e (#6): 오류 처리 정책 (타임아웃·재시도·429)
Task 1f (#7): 티어별 --effort 플래그 + effort 유효성 검증
Task 1h (#9): TRADINGAGENTS_CLAUDE_BARE escape hatch

subprocess 는 모킹한다 — 실제 `claude` CLI 는 호출하지 않는다.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from typing import Literal
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from tradingagents.llm_clients.claude_code_client import (
    _ANTHROPIC_API_KEY_ENV,
    _BARE_ENV,
    _QUOTA_RETRY_AFTER_SECONDS,
    ChatClaudeCodeHeadless,
    ClaudeCodeClient,
    _bare_mode_enabled,
    _coerce_input_to_messages,
    _is_quota_error,
    _messages_to_prompt,
    _parse_structured_output,
    _reset_semaphore,
    _resolve_concurrency,
    _resolve_timeout,
    _run_claude_subprocess,
    _split_messages,
    _validate_bare_prereqs,
)


@pytest.fixture(autouse=True)
def _fresh_semaphore(monkeypatch):
    """매 테스트마다 세마포어 재초기화. 환경변수 오버라이드도 함께 초기화."""
    monkeypatch.delenv("TRADINGAGENTS_CLAUDE_CONCURRENCY", raising=False)
    _reset_semaphore()
    yield
    _reset_semaphore()


def _success_payload(result_text: str = "pong") -> str:
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": result_text,
            "session_id": "test-session",
            "stop_reason": "end_turn",
        }
    )


def _structured_payload(data: dict | None) -> str:
    """--json-schema 응답 포맷: result 는 빈 문자열, structured_output 에 데이터."""
    payload = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "",
        "session_id": "test-session",
        "stop_reason": "end_turn",
    }
    if data is not None:
        payload["structured_output"] = data
    return json.dumps(payload)


class _Decision(BaseModel):
    action: Literal["BUY", "SELL", "HOLD"]
    reason: str


@pytest.mark.unit
def test_messages_to_prompt_legacy_format_still_works():
    """레거시 호환: _messages_to_prompt 는 System: 접두사 포함 단일 문자열 유지."""
    prompt = _messages_to_prompt(
        [
            SystemMessage(content="You are helpful."),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi."),
            HumanMessage(content="Say pong."),
        ]
    )
    assert "System: You are helpful." in prompt
    assert "User: Hello" in prompt
    assert "Assistant: Hi." in prompt
    assert "User: Say pong." in prompt


@pytest.mark.unit
def test_messages_to_prompt_handles_non_string_content():
    msg = HumanMessage(content=[{"type": "text", "text": "block"}])
    out = _messages_to_prompt([msg])
    # 리스트형 content 는 str() 로 변환됨
    assert "User:" in out


@pytest.mark.unit
def test_llm_type_returns_claude_code():
    assert ChatClaudeCodeHeadless(model="sonnet")._llm_type == "claude-code"


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_generate_returns_result_text(mock_run):
    mock_run.return_value = MagicMock(stdout=_success_payload("pong"), returncode=0)

    llm = ChatClaudeCodeHeadless(model="sonnet")
    result = llm._generate([HumanMessage(content="say pong")])

    assert len(result.generations) == 1
    assert result.generations[0].message.content == "pong"
    assert isinstance(result.generations[0].message, AIMessage)


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_generate_passes_cli_args(mock_run):
    mock_run.return_value = MagicMock(stdout=_success_payload(), returncode=0)

    ChatClaudeCodeHeadless(model="haiku")._generate([HumanMessage(content="hi")])

    (args_list,), kwargs = mock_run.call_args
    assert args_list[0] == "claude"
    assert "-p" in args_list
    assert "--output-format" in args_list
    assert "json" in args_list
    assert "--model" in args_list
    assert "haiku" in args_list
    # Task 1c 격리 플래그 + #134: --tools "" 로 모든 툴 비활성 (plan 모드 제거)
    assert "--no-session-persistence" in args_list
    assert "--tools" in args_list
    # --tools 다음 토큰은 빈 문자열이어야 함.
    assert args_list[args_list.index("--tools") + 1] == ""
    # #134: plan 모드는 제거 — 보고서 응답이 메타 요약으로 변질됨.
    assert "--permission-mode" not in args_list
    assert "--disable-slash-commands" in args_list
    assert "--exclude-dynamic-system-prompt-sections" in args_list
    # SystemMessage 없으므로 --append-system-prompt 는 포함되지 않아야 함
    assert "--append-system-prompt" not in args_list
    assert kwargs.get("capture_output") is True
    assert kwargs.get("text") is True
    assert kwargs.get("check") is True


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_generate_system_message_goes_to_append_system_prompt(mock_run):
    """Task 1c: SystemMessage 는 -p 가 아니라 --append-system-prompt 로 전달."""
    mock_run.return_value = MagicMock(stdout=_success_payload(), returncode=0)

    ChatClaudeCodeHeadless(model="sonnet")._generate(
        [
            SystemMessage(content="System rule."),
            HumanMessage(content="User ask."),
        ]
    )

    (args_list,), _ = mock_run.call_args
    # 대화 영역 (-p)
    prompt = args_list[args_list.index("-p") + 1]
    assert "User: User ask." in prompt
    assert "System rule." not in prompt  # System 은 -p 가 아니라 append 로 가야 함
    # 시스템 영역 (--append-system-prompt)
    assert "--append-system-prompt" in args_list
    sys_arg = args_list[args_list.index("--append-system-prompt") + 1]
    assert sys_arg == "System rule."


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_generate_multiple_system_messages_concatenated(mock_run):
    """여러 SystemMessage 는 하나의 --append-system-prompt 로 합쳐짐."""
    mock_run.return_value = MagicMock(stdout=_success_payload(), returncode=0)

    ChatClaudeCodeHeadless(model="sonnet")._generate(
        [
            SystemMessage(content="Rule A."),
            SystemMessage(content="Rule B."),
            HumanMessage(content="Hi"),
        ]
    )

    (args_list,), _ = mock_run.call_args
    sys_arg = args_list[args_list.index("--append-system-prompt") + 1]
    assert "Rule A." in sys_arg
    assert "Rule B." in sys_arg


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_generate_raises_when_is_error_true(mock_run):
    payload = json.dumps(
        {
            "type": "result",
            "subtype": "error",
            "is_error": True,
            "session_id": "err-session",
        }
    )
    mock_run.return_value = MagicMock(stdout=payload, returncode=0)

    with pytest.raises(RuntimeError, match="Claude Code returned error"):
        ChatClaudeCodeHeadless(model="sonnet")._generate([HumanMessage(content="hi")])


@pytest.mark.unit
def test_client_wrapper_returns_adapter():
    client = ClaudeCodeClient(model="sonnet")
    llm = client.get_llm()

    assert isinstance(llm, ChatClaudeCodeHeadless)
    assert llm.model == "sonnet"


@pytest.mark.unit
def test_client_validates_known_models():
    assert ClaudeCodeClient(model="sonnet").validate_model() is True
    assert ClaudeCodeClient(model="opus").validate_model() is True
    assert ClaudeCodeClient(model="haiku").validate_model() is True
    assert ClaudeCodeClient(model="gpt-5").validate_model() is False


# ---------------------------------------------------------------------------
# Task 1b (#3): with_structured_output → --json-schema 매핑
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_coerce_input_to_messages_from_string():
    msgs = _coerce_input_to_messages("hello")
    assert len(msgs) == 1
    assert isinstance(msgs[0], HumanMessage)
    assert msgs[0].content == "hello"


@pytest.mark.unit
def test_coerce_input_to_messages_from_list_passthrough():
    inputs = [SystemMessage(content="s"), HumanMessage(content="h")]
    assert _coerce_input_to_messages(inputs) == inputs


@pytest.mark.unit
def test_coerce_input_to_messages_from_prompt_value():
    tmpl = ChatPromptTemplate.from_messages(
        [("system", "sys"), ("human", "hum")]
    )
    pv = tmpl.format_prompt()
    msgs = _coerce_input_to_messages(pv)
    assert len(msgs) == 2
    assert isinstance(msgs[0], SystemMessage)
    assert isinstance(msgs[1], HumanMessage)


@pytest.mark.unit
def test_parse_structured_output_success():
    data = {"action": "BUY", "reason": "trend up"}
    result = _parse_structured_output({"structured_output": data}, _Decision)
    assert isinstance(result, _Decision)
    assert result.action == "BUY"
    assert result.reason == "trend up"


@pytest.mark.unit
def test_parse_structured_output_missing_field_returns_none():
    assert _parse_structured_output({}, _Decision) is None


@pytest.mark.unit
def test_parse_structured_output_non_dict_returns_none():
    assert _parse_structured_output({"structured_output": "not a dict"}, _Decision) is None


@pytest.mark.unit
def test_parse_structured_output_schema_violation_returns_none():
    # action must be one of BUY/SELL/HOLD
    assert _parse_structured_output(
        {"structured_output": {"action": "MAYBE", "reason": "x"}}, _Decision
    ) is None


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_structured_output_returns_schema_instance(mock_run):
    mock_run.return_value = MagicMock(
        stdout=_structured_payload({"action": "BUY", "reason": "trend up"}),
        returncode=0,
    )

    llm = ChatClaudeCodeHeadless(model="sonnet")
    structured = llm.with_structured_output(_Decision)
    result = structured.invoke("Analyze this.")

    assert isinstance(result, _Decision)
    assert result.action == "BUY"
    assert result.reason == "trend up"


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_structured_output_passes_json_schema_arg(mock_run):
    mock_run.return_value = MagicMock(
        stdout=_structured_payload({"action": "HOLD", "reason": "x"}),
        returncode=0,
    )

    ChatClaudeCodeHeadless(model="haiku").with_structured_output(_Decision).invoke("hi")

    (args_list,), _ = mock_run.call_args
    assert "--json-schema" in args_list
    schema_arg = args_list[args_list.index("--json-schema") + 1]
    schema_data = json.loads(schema_arg)
    # Pydantic 이 생성한 JSON Schema 에 action/reason 필드가 포함되어야 함
    assert "action" in schema_data.get("properties", {})
    assert "reason" in schema_data.get("properties", {})


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_structured_output_accepts_message_list(mock_run):
    mock_run.return_value = MagicMock(
        stdout=_structured_payload({"action": "SELL", "reason": "overvalued"}),
        returncode=0,
    )

    llm = ChatClaudeCodeHeadless(model="sonnet")
    result = llm.with_structured_output(_Decision).invoke(
        [SystemMessage(content="Be concise."), HumanMessage(content="Decide.")]
    )

    assert isinstance(result, _Decision)
    assert result.action == "SELL"


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_structured_output_accepts_chat_prompt_template(mock_run):
    mock_run.return_value = MagicMock(
        stdout=_structured_payload({"action": "BUY", "reason": "growth"}),
        returncode=0,
    )

    tmpl = ChatPromptTemplate.from_messages(
        [("system", "You are an analyst."), ("human", "Decide on {ticker}.")]
    )
    prompt_value = tmpl.format_prompt(ticker="005930")

    llm = ChatClaudeCodeHeadless(model="sonnet")
    result = llm.with_structured_output(_Decision).invoke(prompt_value)

    assert isinstance(result, _Decision)
    assert result.action == "BUY"


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_structured_output_returns_none_on_missing_structured_field(mock_run):
    mock_run.return_value = MagicMock(stdout=_structured_payload(None), returncode=0)

    llm = ChatClaudeCodeHeadless(model="sonnet")
    result = llm.with_structured_output(_Decision).invoke("hi")

    assert result is None


# ---------------------------------------------------------------------------
# Task 1c (#4): 격리 플래그 + SystemMessage 분리 전달
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_split_messages_separates_system_from_conversation():
    system_prompt, conversation = _split_messages(
        [
            SystemMessage(content="You are helpful."),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi."),
            HumanMessage(content="Say pong."),
        ]
    )
    assert system_prompt == "You are helpful."
    assert "User: Hello" in conversation
    assert "Assistant: Hi." in conversation
    assert "User: Say pong." in conversation
    assert "System:" not in conversation


@pytest.mark.unit
def test_split_messages_empty_when_no_system():
    system_prompt, conversation = _split_messages(
        [HumanMessage(content="only user")]
    )
    assert system_prompt == ""
    assert "User: only user" in conversation


@pytest.mark.unit
def test_split_messages_empty_when_only_system():
    system_prompt, conversation = _split_messages(
        [SystemMessage(content="just rules")]
    )
    assert system_prompt == "just rules"
    assert conversation == ""


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_structured_output_also_uses_isolation_flags_and_system_split(mock_run):
    """structured 경로도 격리 플래그 + SystemMessage 분리를 똑같이 적용."""
    mock_run.return_value = MagicMock(
        stdout=_structured_payload({"action": "BUY", "reason": "x"}),
        returncode=0,
    )

    tmpl = ChatPromptTemplate.from_messages(
        [("system", "Analyst persona."), ("human", "Decide {ticker}.")]
    )
    prompt_value = tmpl.format_prompt(ticker="005930")

    ChatClaudeCodeHeadless(model="sonnet").with_structured_output(_Decision).invoke(
        prompt_value
    )

    (args_list,), _ = mock_run.call_args
    # 격리 플래그
    assert "--disable-slash-commands" in args_list
    assert "--exclude-dynamic-system-prompt-sections" in args_list
    # SystemMessage 분리
    assert "--append-system-prompt" in args_list
    sys_arg = args_list[args_list.index("--append-system-prompt") + 1]
    assert "Analyst persona." in sys_arg
    # 대화는 -p 에
    prompt = args_list[args_list.index("-p") + 1]
    assert "User: Decide 005930." in prompt
    # --json-schema 도 여전히 포함
    assert "--json-schema" in args_list


# ---------------------------------------------------------------------------
# Task 1d (#5): 동시 실행 세마포어
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_concurrency_default():
    assert _resolve_concurrency() == 2


@pytest.mark.unit
def test_resolve_concurrency_from_env(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CLAUDE_CONCURRENCY", "5")
    assert _resolve_concurrency() == 5


@pytest.mark.unit
def test_resolve_concurrency_empty_string_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CLAUDE_CONCURRENCY", "")
    assert _resolve_concurrency() == 2


@pytest.mark.unit
def test_resolve_concurrency_rejects_non_integer(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CLAUDE_CONCURRENCY", "abc")
    with pytest.raises(ValueError, match="positive integer"):
        _resolve_concurrency()


@pytest.mark.unit
def test_resolve_concurrency_rejects_zero(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CLAUDE_CONCURRENCY", "0")
    with pytest.raises(ValueError, match="positive integer"):
        _resolve_concurrency()


@pytest.mark.unit
def test_resolve_concurrency_rejects_negative(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CLAUDE_CONCURRENCY", "-1")
    with pytest.raises(ValueError, match="positive integer"):
        _resolve_concurrency()


@pytest.mark.unit
def test_semaphore_limits_concurrent_subprocess_calls(monkeypatch):
    """concurrency=2 설정 시 3개 쓰레드 중 하나는 반드시 대기해야 한다."""
    monkeypatch.setenv("TRADINGAGENTS_CLAUDE_CONCURRENCY", "2")
    _reset_semaphore()

    in_flight = 0
    max_in_flight = 0
    stats_lock = threading.Lock()

    def _slow_run(*args, **kwargs):
        nonlocal in_flight, max_in_flight
        with stats_lock:
            in_flight += 1
            if in_flight > max_in_flight:
                max_in_flight = in_flight
        time.sleep(0.1)
        with stats_lock:
            in_flight -= 1
        return MagicMock(stdout=_success_payload(), returncode=0)

    with patch(
        "tradingagents.llm_clients.claude_code_client.subprocess.run",
        side_effect=_slow_run,
    ):
        threads = [
            threading.Thread(
                target=_run_claude_subprocess, args=(["claude", "-p", "x"], 300)
            )
            for _ in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    # 디폴트 2 로 제한되므로 동시에 3개는 불가능
    assert max_in_flight <= 2


@pytest.mark.unit
def test_semaphore_concurrency_one_fully_serializes(monkeypatch):
    """concurrency=1 → 완전 직렬 실행."""
    monkeypatch.setenv("TRADINGAGENTS_CLAUDE_CONCURRENCY", "1")
    _reset_semaphore()

    in_flight = 0
    max_in_flight = 0
    stats_lock = threading.Lock()

    def _slow_run(*args, **kwargs):
        nonlocal in_flight, max_in_flight
        with stats_lock:
            in_flight += 1
            if in_flight > max_in_flight:
                max_in_flight = in_flight
        time.sleep(0.05)
        with stats_lock:
            in_flight -= 1
        return MagicMock(stdout=_success_payload(), returncode=0)

    with patch(
        "tradingagents.llm_clients.claude_code_client.subprocess.run",
        side_effect=_slow_run,
    ):
        threads = [
            threading.Thread(
                target=_run_claude_subprocess, args=(["claude", "-p", "x"], 300)
            )
            for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert max_in_flight == 1


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_structured_output_raises_on_is_error(mock_run):
    payload = json.dumps(
        {
            "type": "result",
            "subtype": "error",
            "is_error": True,
            "session_id": "err",
        }
    )
    mock_run.return_value = MagicMock(stdout=payload, returncode=0)

    with pytest.raises(RuntimeError, match="Claude Code returned error"):
        ChatClaudeCodeHeadless(model="sonnet").with_structured_output(_Decision).invoke("hi")


# ---------------------------------------------------------------------------
# Task 1e (#6): 오류 처리 정책 (타임아웃·재시도·429)
# ---------------------------------------------------------------------------


# -- _resolve_timeout --------------------------------------------------------


@pytest.mark.unit
def test_resolve_timeout_default_medium():
    assert _resolve_timeout("medium") == 300


@pytest.mark.unit
def test_resolve_timeout_effort_levels():
    assert _resolve_timeout("low") == 180
    assert _resolve_timeout("medium") == 300
    assert _resolve_timeout("high") == 600
    assert _resolve_timeout("xhigh") == 900
    assert _resolve_timeout("max") == 1200


@pytest.mark.unit
def test_resolve_timeout_unknown_effort_falls_back_to_medium():
    assert _resolve_timeout("totally-unknown") == 300


@pytest.mark.unit
def test_resolve_timeout_env_override_wins(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CLAUDE_TIMEOUT", "42")
    # effort 가 어떻든 환경변수가 우선
    assert _resolve_timeout("high") == 42
    assert _resolve_timeout("low") == 42


@pytest.mark.unit
def test_resolve_timeout_rejects_invalid_env(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CLAUDE_TIMEOUT", "nope")
    with pytest.raises(ValueError, match="positive integer"):
        _resolve_timeout("medium")


@pytest.mark.unit
def test_resolve_timeout_rejects_zero_env(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CLAUDE_TIMEOUT", "0")
    with pytest.raises(ValueError, match="positive integer"):
        _resolve_timeout("medium")


# -- _is_quota_error ---------------------------------------------------------


@pytest.mark.unit
def test_is_quota_error_detects_429_status():
    assert _is_quota_error(
        {"is_error": True, "api_error_status": 429, "subtype": "whatever"}
    ) is True


@pytest.mark.unit
def test_is_quota_error_detects_rate_limit_subtype():
    assert _is_quota_error(
        {"is_error": True, "subtype": "rate_limit_exceeded"}
    ) is True


@pytest.mark.unit
def test_is_quota_error_detects_quota_subtype():
    assert _is_quota_error({"is_error": True, "subtype": "quota_exceeded"}) is True


@pytest.mark.unit
def test_is_quota_error_ignores_other_errors():
    assert _is_quota_error({"is_error": True, "subtype": "invalid_input"}) is False


@pytest.mark.unit
def test_is_quota_error_requires_is_error_flag():
    # api_error_status 가 429 라도 is_error 가 False 면 쿼터로 간주하지 않음
    assert _is_quota_error({"is_error": False, "api_error_status": 429}) is False


# -- subprocess 호출 시 timeout 전달 ----------------------------------------


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_run_passes_timeout_to_subprocess(mock_run):
    mock_run.return_value = MagicMock(stdout=_success_payload(), returncode=0)
    _run_claude_subprocess(["claude", "-p", "x"], timeout=42)
    (_, kwargs) = mock_run.call_args
    assert kwargs.get("timeout") == 42


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_generate_uses_effort_based_timeout(mock_run):
    mock_run.return_value = MagicMock(stdout=_success_payload(), returncode=0)
    llm = ChatClaudeCodeHeadless(model="sonnet", effort="high")
    llm._generate([HumanMessage(content="hi")])
    (_, kwargs) = mock_run.call_args
    assert kwargs.get("timeout") == 600  # high


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_generate_env_timeout_overrides_effort(mock_run, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CLAUDE_TIMEOUT", "77")
    mock_run.return_value = MagicMock(stdout=_success_payload(), returncode=0)
    llm = ChatClaudeCodeHeadless(model="sonnet", effort="max")
    llm._generate([HumanMessage(content="hi")])
    (_, kwargs) = mock_run.call_args
    assert kwargs.get("timeout") == 77


# -- non-zero exit 재시도 ---------------------------------------------------


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_non_zero_exit_retried_once_then_succeeds(mock_run):
    """첫 호출은 CalledProcessError, 두 번째는 성공."""
    mock_run.side_effect = [
        subprocess.CalledProcessError(returncode=1, cmd="claude"),
        MagicMock(stdout=_success_payload("ok"), returncode=0),
    ]
    payload = _run_claude_subprocess(["claude", "-p", "x"], timeout=300)
    assert payload["result"] == "ok"
    assert mock_run.call_count == 2


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_non_zero_exit_propagates_after_retry(mock_run):
    """두 번 다 CalledProcessError → 전파."""
    mock_run.side_effect = subprocess.CalledProcessError(returncode=1, cmd="claude")
    with pytest.raises(subprocess.CalledProcessError):
        _run_claude_subprocess(["claude", "-p", "x"], timeout=300)
    assert mock_run.call_count == 2


# -- 타임아웃 (재시도 없이 전파) ---------------------------------------------


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_timeout_propagates_without_retry(mock_run):
    """subprocess.TimeoutExpired 는 재시도 없이 전파."""
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=1)
    with pytest.raises(subprocess.TimeoutExpired):
        _run_claude_subprocess(["claude", "-p", "x"], timeout=1)
    assert mock_run.call_count == 1  # 재시도 없음


# -- JSON 파싱 실패 (재시도 없이 전파) --------------------------------------


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_malformed_json_propagates_without_retry(mock_run):
    mock_run.return_value = MagicMock(stdout="not json at all", returncode=0)
    with pytest.raises(json.JSONDecodeError):
        _run_claude_subprocess(["claude", "-p", "x"], timeout=300)
    assert mock_run.call_count == 1


# -- 429 쿼터 재시도 ---------------------------------------------------------


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.time.sleep")
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_quota_error_waits_and_retries_success(mock_run, mock_sleep):
    """429 → 60초 대기 → 재시도 성공."""
    quota = json.dumps(
        {
            "type": "result",
            "subtype": "rate_limit_exceeded",
            "is_error": True,
            "api_error_status": 429,
            "session_id": "quota",
        }
    )
    mock_run.side_effect = [
        MagicMock(stdout=quota, returncode=0),
        MagicMock(stdout=_success_payload("ok"), returncode=0),
    ]
    payload = _run_claude_subprocess(["claude", "-p", "x"], timeout=300)
    assert payload["result"] == "ok"
    assert mock_run.call_count == 2
    mock_sleep.assert_called_once_with(_QUOTA_RETRY_AFTER_SECONDS)


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.time.sleep")
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_quota_error_twice_raises_with_korean_message(mock_run, mock_sleep):
    quota = json.dumps(
        {
            "type": "result",
            "subtype": "rate_limit_exceeded",
            "is_error": True,
            "api_error_status": 429,
            "session_id": "quota",
        }
    )
    mock_run.return_value = MagicMock(stdout=quota, returncode=0)
    with pytest.raises(RuntimeError, match="Max 플랜 쿼터 소진"):
        _run_claude_subprocess(["claude", "-p", "x"], timeout=300)
    assert mock_run.call_count == 2
    mock_sleep.assert_called_once_with(_QUOTA_RETRY_AFTER_SECONDS)


# ---------------------------------------------------------------------------
# Task 1f (#7): 티어 매핑 (--effort CLI 플래그 + ClaudeCodeClient effort kwarg)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_generate_passes_effort_flag_to_cli(mock_run):
    mock_run.return_value = MagicMock(stdout=_success_payload(), returncode=0)
    llm = ChatClaudeCodeHeadless(model="sonnet", effort="high")
    llm._generate([HumanMessage(content="hi")])
    (args_list,), _ = mock_run.call_args
    assert "--effort" in args_list
    assert args_list[args_list.index("--effort") + 1] == "high"


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_structured_output_passes_effort_flag(mock_run):
    mock_run.return_value = MagicMock(
        stdout=_structured_payload({"action": "BUY", "reason": "x"}),
        returncode=0,
    )
    llm = ChatClaudeCodeHeadless(model="haiku", effort="max")
    llm.with_structured_output(_Decision).invoke("decide")
    (args_list,), _ = mock_run.call_args
    assert args_list[args_list.index("--effort") + 1] == "max"


@pytest.mark.unit
def test_client_wrapper_forwards_effort_kwarg():
    client = ClaudeCodeClient("sonnet", effort="high")
    llm = client.get_llm()
    assert isinstance(llm, ChatClaudeCodeHeadless)
    assert llm.effort == "high"


@pytest.mark.unit
def test_client_wrapper_rejects_invalid_effort():
    client = ClaudeCodeClient("sonnet", effort="not-a-real-level")
    with pytest.raises(ValueError, match="effort must be one of"):
        client.get_llm()


@pytest.mark.unit
def test_client_wrapper_default_effort_when_no_kwarg():
    """effort 를 kwarg 로 넘기지 않으면 ChatClaudeCodeHeadless 가 자체 디폴트(medium)."""
    client = ClaudeCodeClient("sonnet")
    llm = client.get_llm()
    assert llm.effort == "medium"


# -- factory.create_tier_client 가 티어별 effort 를 올바르게 매핑 ----------


@pytest.mark.unit
def test_factory_deep_tier_uses_effort_key():
    """deep 티어 호출 시 config['effort'] 가 어댑터로 넘어감."""
    from tradingagents.llm_clients.factory import create_tier_client

    config = {
        "llm_provider": "claude-code",
        "deep_think_llm": "sonnet",
        "quick_think_llm": "haiku",
        "effort": "high",
        "quick_effort": "medium",
    }
    client = create_tier_client(config, tier="deep")
    assert isinstance(client, ClaudeCodeClient)
    assert client.model == "sonnet"
    llm = client.get_llm()
    assert llm.effort == "high"


@pytest.mark.unit
def test_factory_quick_tier_uses_quick_effort_key():
    """quick 티어 호출 시 config['quick_effort'] 가 어댑터로 넘어감."""
    from tradingagents.llm_clients.factory import create_tier_client

    config = {
        "llm_provider": "claude-code",
        "deep_think_llm": "sonnet",
        "quick_think_llm": "haiku",
        "effort": "high",
        "quick_effort": "medium",
    }
    client = create_tier_client(config, tier="quick")
    assert isinstance(client, ClaudeCodeClient)
    assert client.model == "haiku"
    llm = client.get_llm()
    assert llm.effort == "medium"


@pytest.mark.unit
def test_factory_claude_code_requires_no_api_key():
    """api_key_env 는 claude-code 를 키 불필요로 표시해야 함 (OAuth 사용)."""
    from tradingagents.llm_clients.api_key_env import get_api_key_env

    assert get_api_key_env("claude-code") is None


# ---------------------------------------------------------------------------
# Task 1h (#9): TRADINGAGENTS_CLAUDE_BARE escape hatch
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_bare_mode_disabled_by_default(monkeypatch):
    monkeypatch.delenv(_BARE_ENV, raising=False)
    assert _bare_mode_enabled() is False


@pytest.mark.unit
def test_bare_mode_enabled_when_env_is_1(monkeypatch):
    monkeypatch.setenv(_BARE_ENV, "1")
    assert _bare_mode_enabled() is True


@pytest.mark.unit
def test_bare_mode_other_truthy_values_not_accepted(monkeypatch):
    """엄격한 '1' 매칭 — true/yes/on 은 수용하지 않는다 (오타로 켜지는 것 방지)."""
    for val in ("true", "yes", "on", "True", "01", " 1 "):
        monkeypatch.setenv(_BARE_ENV, val)
        if val.strip() == "1":
            assert _bare_mode_enabled() is True
        else:
            assert _bare_mode_enabled() is False, f"should reject {val!r}"


@pytest.mark.unit
def test_validate_bare_prereqs_passes_when_key_set(monkeypatch):
    monkeypatch.setenv(_ANTHROPIC_API_KEY_ENV, "sk-ant-test")
    _validate_bare_prereqs()  # no raise


@pytest.mark.unit
def test_validate_bare_prereqs_raises_when_key_missing(monkeypatch):
    monkeypatch.delenv(_ANTHROPIC_API_KEY_ENV, raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        _validate_bare_prereqs()


@pytest.mark.unit
def test_validate_bare_prereqs_raises_when_key_empty(monkeypatch):
    monkeypatch.setenv(_ANTHROPIC_API_KEY_ENV, "   ")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        _validate_bare_prereqs()


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_bare_flag_not_in_args_by_default(mock_run, monkeypatch):
    monkeypatch.delenv(_BARE_ENV, raising=False)
    mock_run.return_value = MagicMock(stdout=_success_payload(), returncode=0)

    ChatClaudeCodeHeadless(model="sonnet")._generate([HumanMessage(content="hi")])

    (args_list,), _ = mock_run.call_args
    assert "--bare" not in args_list


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_bare_flag_added_when_env_set_and_key_present(mock_run, monkeypatch):
    monkeypatch.setenv(_BARE_ENV, "1")
    monkeypatch.setenv(_ANTHROPIC_API_KEY_ENV, "sk-ant-test")
    mock_run.return_value = MagicMock(stdout=_success_payload(), returncode=0)

    ChatClaudeCodeHeadless(model="sonnet")._generate([HumanMessage(content="hi")])

    (args_list,), _ = mock_run.call_args
    assert "--bare" in args_list


@pytest.mark.unit
def test_bare_mode_without_api_key_raises_from_adapter(monkeypatch):
    """어댑터 레벨에서 선검증 → subprocess 호출 전에 명확히 실패."""
    monkeypatch.setenv(_BARE_ENV, "1")
    monkeypatch.delenv(_ANTHROPIC_API_KEY_ENV, raising=False)

    llm = ChatClaudeCodeHeadless(model="sonnet")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        llm._generate([HumanMessage(content="hi")])


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_bare_flag_applied_to_structured_output_path(mock_run, monkeypatch):
    monkeypatch.setenv(_BARE_ENV, "1")
    monkeypatch.setenv(_ANTHROPIC_API_KEY_ENV, "sk-ant-test")
    mock_run.return_value = MagicMock(
        stdout=_structured_payload({"action": "BUY", "reason": "x"}),
        returncode=0,
    )

    ChatClaudeCodeHeadless(model="sonnet").with_structured_output(_Decision).invoke("hi")

    (args_list,), _ = mock_run.call_args
    assert "--bare" in args_list


# ---------------------------------------------------------------------------
# Task 1g (#8): llm_clients 패키지 공개 심볼
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_package_exposes_claude_code_symbols():
    """`from tradingagents.llm_clients import ...` 로 Claude Code 어댑터 접근 가능."""
    from tradingagents import llm_clients as pkg

    assert hasattr(pkg, "ChatClaudeCodeHeadless")
    assert hasattr(pkg, "ClaudeCodeClient")
    assert "ChatClaudeCodeHeadless" in pkg.__all__
    assert "ClaudeCodeClient" in pkg.__all__


@pytest.mark.unit
def test_factory_create_llm_client_returns_claude_code_client():
    """create_llm_client(provider='claude-code', ...) 가 ClaudeCodeClient 반환."""
    from tradingagents.llm_clients import create_llm_client

    client = create_llm_client(provider="claude-code", model="sonnet")
    assert isinstance(client, ClaudeCodeClient)
    assert client.model == "sonnet"


@pytest.mark.unit
def test_factory_create_llm_client_passes_kwargs_through():
    """effort 같은 kwargs 가 어댑터로 넘어감."""
    from tradingagents.llm_clients import create_llm_client

    client = create_llm_client(provider="claude-code", model="haiku", effort="high")
    llm = client.get_llm()
    assert llm.effort == "high"


# ============================================================================
# Integration tests (Task 11c, #94) — 실제 ``claude -p`` 호출.
#   로컬 실행: ``pytest tests/test_claude_code_client.py -m integration``
#   claude CLI 가 PATH 에 있어야 하며 Max/Pro 플랜 OAuth 로그인 완료 상태여야 함.
#   테스트가 실제 쿼터를 소모하므로 짧은 프롬프트만 사용.
# ============================================================================


@pytest.mark.integration
def test_live_claude_code_responds_to_short_prompt(claude_cli_available):
    """``claude -p "Reply with the word READY"`` 가 "READY" 를 포함해 응답."""
    client = ChatClaudeCodeHeadless(model="haiku", effort="low")
    result = client.invoke([HumanMessage(content="Reply with the single word READY and nothing else.")])
    assert isinstance(result, AIMessage)
    assert "READY" in result.content.upper()
