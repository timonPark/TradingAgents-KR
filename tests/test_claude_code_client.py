"""Task 1a (#2): ChatClaudeCodeHeadless 기본 subprocess 래퍼 유닛 테스트.

subprocess 는 모킹한다 — 실제 `claude` CLI 는 호출하지 않는다. 하위 이슈
에서 테스트가 확장된다 (세마포어, 타임아웃, 재시도, 429, 격리 플래그 전수).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from tradingagents.llm_clients.claude_code_client import (
    ChatClaudeCodeHeadless,
    ClaudeCodeClient,
    _messages_to_prompt,
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


@pytest.mark.unit
def test_messages_to_prompt_formats_roles():
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
    # 리스트형 content 는 str() 로 처리되어 깨지지 않음을 확인 (내용 포맷은 Task 1c 범위)
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
    assert "--no-session-persistence" in args_list
    assert "--permission-mode" in args_list
    assert "plan" in args_list
    assert kwargs.get("capture_output") is True
    assert kwargs.get("text") is True
    assert kwargs.get("check") is True


@pytest.mark.unit
@patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
def test_generate_prompt_contains_message_text(mock_run):
    mock_run.return_value = MagicMock(stdout=_success_payload(), returncode=0)

    ChatClaudeCodeHeadless(model="sonnet")._generate(
        [
            SystemMessage(content="System rule."),
            HumanMessage(content="User ask."),
        ]
    )

    (args_list,), _ = mock_run.call_args
    prompt = args_list[args_list.index("-p") + 1]
    assert "System: System rule." in prompt
    assert "User: User ask." in prompt


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
