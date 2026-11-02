"""ChatClaudeCodeHeadless 유닛 테스트.

Task 1a (#2): 기본 subprocess 래퍼
Task 1b (#3): with_structured_output → --json-schema 매핑
Task 1c (#4): 격리 플래그 전체 세트 + SystemMessage 분리 전달

subprocess 는 모킹한다 — 실제 `claude` CLI 는 호출하지 않는다. 하위 이슈
에서 테스트가 확장된다 (세마포어, 타임아웃, 재시도, 429).
"""

from __future__ import annotations

import json
from typing import Literal
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from tradingagents.llm_clients.claude_code_client import (
    ChatClaudeCodeHeadless,
    ClaudeCodeClient,
    _coerce_input_to_messages,
    _messages_to_prompt,
    _parse_structured_output,
    _split_messages,
)


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
    # Task 1c 격리 플래그 전체 세트
    assert "--no-session-persistence" in args_list
    assert "--permission-mode" in args_list
    assert "plan" in args_list
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
