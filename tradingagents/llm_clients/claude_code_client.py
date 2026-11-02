"""Claude Code 헤드리스 LLM 어댑터.

`claude -p` subprocess 호출을 LangChain `BaseChatModel` 로 래핑한다.
외부 LLM API SDK 를 직접 사용하지 않고 로컬 Claude Code CLI 를 호출해
Max/Pro 플랜 쿼터로 추론한다 (ADR-0001 참조).

Task 1a 범위: 기본 subprocess 래퍼 + JSON 응답 파싱 + AIMessage 반환.
세마포어·타임아웃·재시도·추가 격리 플래그는 하위 이슈에서 확장된다.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .base_client import BaseLLMClient


def _messages_to_prompt(messages: list[BaseMessage]) -> str:
    """LangChain 메시지 리스트를 단일 프롬프트 문자열로 변환.

    Claude Code `-p` 는 단일 텍스트 입력만 받으므로 역할 접두사(System/User/
    Assistant) 로 대화 흐름을 표기해 전달한다. 역할 분리는 Task 1c (#4) 에서
    `--append-system-prompt` 로 더 정교화된다.
    """
    parts: list[str] = []
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if isinstance(msg, SystemMessage):
            parts.append(f"System: {content}")
        elif isinstance(msg, HumanMessage):
            parts.append(f"User: {content}")
        elif isinstance(msg, AIMessage):
            parts.append(f"Assistant: {content}")
        else:
            parts.append(content)
    return "\n\n".join(parts)


class ChatClaudeCodeHeadless(BaseChatModel):
    """Claude Code `claude -p` subprocess 를 LangChain BaseChatModel 로 래핑.

    Task 1a 스코프: 기본 subprocess 호출 + JSON 응답 파싱만. 다음 하위 이슈에서
    확장:
    - #4 격리 플래그 (`--disable-slash-commands`, `--exclude-dynamic-system-prompt-sections`)
    - #5 세마포어 (`TRADINGAGENTS_CLAUDE_CONCURRENCY`)
    - #6 타임아웃·재시도·429 처리
    - #7 티어별 effort / 모델 매핑
    """

    model: str = "sonnet"

    @property
    def _llm_type(self) -> str:
        return "claude-code"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        prompt = _messages_to_prompt(messages)
        args = [
            "claude",
            "-p", prompt,
            "--output-format", "json",
            "--model", self.model,
            "--no-session-persistence",
            "--permission-mode", "plan",
        ]
        completed = subprocess.run(args, capture_output=True, text=True, check=True)
        payload = json.loads(completed.stdout)

        if payload.get("is_error"):
            raise RuntimeError(
                f"Claude Code returned error: subtype={payload.get('subtype')!r} "
                f"session_id={payload.get('session_id')!r}"
            )

        text = payload.get("result", "")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


class ClaudeCodeClient(BaseLLMClient):
    """TradingAgents 의 BaseLLMClient 어댑터.

    `factory.create_llm_client(provider="claude-code", model="sonnet")` 가
    이 클래스의 인스턴스를 반환한다 (Task 1g #8 에서 factory.py 분기 추가).
    """

    _KNOWN_MODELS = frozenset({"sonnet", "opus", "haiku"})

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        return ChatClaudeCodeHeadless(model=self.model)

    def validate_model(self) -> bool:
        return self.model in self._KNOWN_MODELS
