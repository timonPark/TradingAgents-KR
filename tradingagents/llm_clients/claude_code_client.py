"""Claude Code 헤드리스 LLM 어댑터.

`claude -p` subprocess 호출을 LangChain `BaseChatModel` 로 래핑한다.
외부 LLM API SDK 를 직접 사용하지 않고 로컬 Claude Code CLI 를 호출해
Max/Pro 플랜 쿼터로 추론한다 (ADR-0001 참조).

구현 범위:
- Task 1a (#2): 기본 subprocess 래퍼 + JSON 응답 파싱 + AIMessage 반환
- Task 1b (#3): with_structured_output(Schema) → --json-schema 매핑

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
from langchain_core.prompt_values import PromptValue
from pydantic import BaseModel, ValidationError

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


def _coerce_input_to_messages(input_: Any) -> list[BaseMessage]:
    """Runnable.invoke() 가 받는 다양한 입력을 BaseMessage 리스트로 통일.

    LangChain 의 structured_llm.invoke(prompt) 호출부가 전달하는 입력 종류:
    - str: 단일 사용자 메시지로 변환
    - list[BaseMessage]: 그대로 사용
    - PromptValue (ChatPromptTemplate 결과): .to_messages() 로 변환
    """
    if isinstance(input_, str):
        return [HumanMessage(content=input_)]
    if isinstance(input_, PromptValue):
        return input_.to_messages()
    if isinstance(input_, list):
        return input_
    return [HumanMessage(content=str(input_))]


def _run_claude_subprocess(args: list[str]) -> dict:
    """Claude Code CLI subprocess 호출. JSON payload dict 반환.

    `is_error=True` 응답은 RuntimeError 로 전파한다. subprocess 자체의
    non-zero exit (CalledProcessError) 는 호출부로 그대로 전파된다 — Task 1e
    (#6) 에서 재시도 로직 추가 시 처리.
    """
    completed = subprocess.run(args, capture_output=True, text=True, check=True)
    payload = json.loads(completed.stdout)
    if payload.get("is_error"):
        raise RuntimeError(
            f"Claude Code returned error: subtype={payload.get('subtype')!r} "
            f"session_id={payload.get('session_id')!r}"
        )
    return payload


class ChatClaudeCodeHeadless(BaseChatModel):
    """Claude Code `claude -p` subprocess 를 LangChain BaseChatModel 로 래핑.

    다음 하위 이슈에서 확장:
    - #4 격리 플래그 (`--disable-slash-commands`, `--exclude-dynamic-system-prompt-sections`)
    - #5 세마포어 (`TRADINGAGENTS_CLAUDE_CONCURRENCY`)
    - #6 타임아웃·재시도·429 처리
    - #7 티어별 effort / 모델 매핑
    """

    model: str = "sonnet"

    @property
    def _llm_type(self) -> str:
        return "claude-code"

    def _base_cli_args(self, prompt: str) -> list[str]:
        """구조화/비구조화 호출 공통 CLI 인자."""
        return [
            "claude",
            "-p", prompt,
            "--output-format", "json",
            "--model", self.model,
            "--no-session-persistence",
            "--permission-mode", "plan",
        ]

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        args = self._base_cli_args(_messages_to_prompt(messages))
        payload = _run_claude_subprocess(args)
        text = payload.get("result", "")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def with_structured_output(
        self,
        schema: type[BaseModel],
        **kwargs: Any,
    ) -> _StructuredClaudeCode:
        """Pydantic 스키마 기반 구조화 출력 Runnable 반환.

        LangChain 공식 `BaseChatModel.with_structured_output` 과 호환되는
        시그니처. kwargs (method, include_raw 등) 는 Task 1b 범위에서 지원하지
        않음 — Claude Code 의 `--json-schema` 가 단일 경로이므로 method 선택
        여지가 없음.
        """
        return _StructuredClaudeCode(self, schema)


class _StructuredClaudeCode:
    """`ChatClaudeCodeHeadless.with_structured_output()` 반환 Runnable.

    `.invoke(input)` 호출 시:
    1. 입력을 BaseMessage 리스트로 변환
    2. `claude -p ... --json-schema <schema_json>` subprocess 호출
    3. 응답의 `structured_output` 필드를 Pydantic 인스턴스로 복원
    4. 복원 실패 시 None 반환 — `structured.py` 가 free-text 폴백 처리

    주의: `--json-schema` 사용 시 Claude Code 는 응답을 `result` 가 아니라
    `structured_output` 필드에 담는다 (실제 CLI 동작 확인). `result` 는 빈
    문자열이다.
    """

    def __init__(self, llm: ChatClaudeCodeHeadless, schema: type[BaseModel]) -> None:
        self._llm = llm
        self._schema = schema

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> BaseModel | None:
        messages = _coerce_input_to_messages(input)
        prompt = _messages_to_prompt(messages)
        schema_json = json.dumps(self._schema.model_json_schema())
        args = self._llm._base_cli_args(prompt) + ["--json-schema", schema_json]

        payload = _run_claude_subprocess(args)
        return _parse_structured_output(payload, self._schema)


def _parse_structured_output(
    payload: dict, schema: type[BaseModel]
) -> BaseModel | None:
    """payload['structured_output'] 를 Pydantic 인스턴스로 복원.

    복원 실패 (필드 없음, 타입 불일치, 스키마 검증 실패) 는 None 반환으로
    처리하여 `structured.py` 의 free-text 폴백 경로가 작동하게 한다.
    """
    data = payload.get("structured_output")
    if data is None:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return schema(**data)
    except (TypeError, ValidationError):
        return None


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
