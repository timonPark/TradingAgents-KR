"""Claude Code 헤드리스 LLM 어댑터.

`claude -p` subprocess 호출을 LangChain `BaseChatModel` 로 래핑한다.
외부 LLM API SDK 를 직접 사용하지 않고 로컬 Claude Code CLI 를 호출해
Max/Pro 플랜 쿼터로 추론한다 (ADR-0001 참조).

구현 범위:
- Task 1a (#2): 기본 subprocess 래퍼 + JSON 응답 파싱 + AIMessage 반환
- Task 1b (#3): with_structured_output(Schema) → --json-schema 매핑
- Task 1c (#4): 어댑터 격리 플래그 전체 세트 + SystemMessage 분리 전달
- Task 1d (#5): 동시 실행 세마포어 (TRADINGAGENTS_CLAUDE_CONCURRENCY)

타임아웃·재시도는 하위 이슈에서 확장된다.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.prompt_values import PromptValue
from pydantic import BaseModel, ValidationError

from .base_client import BaseLLMClient


def _split_messages(messages: list[BaseMessage]) -> tuple[str, str]:
    """LangChain 메시지 리스트를 (system_prompt, conversation_prompt) 로 분리.

    SystemMessage 는 `--append-system-prompt` 로 Claude Code 의 시스템 영역에
    주입되고, Human/AI 메시지는 `-p` 로 전달되는 대화 영역에 배치된다. Task 1a
    에서 사용하던 역할 접두사 단일 문자열 포맷 (`System: ...\\n\\nUser: ...`) 보다
    정확한 역할 전달이 가능하다.

    여러 SystemMessage 는 합쳐지며, 하나도 없으면 빈 문자열을 반환해 호출부가
    `--append-system-prompt` 플래그를 생략할 수 있게 한다.
    """
    system_parts: list[str] = []
    conversation_parts: list[str] = []
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if isinstance(msg, SystemMessage):
            system_parts.append(content)
        elif isinstance(msg, HumanMessage):
            conversation_parts.append(f"User: {content}")
        elif isinstance(msg, AIMessage):
            conversation_parts.append(f"Assistant: {content}")
        else:
            conversation_parts.append(content)
    return "\n\n".join(system_parts), "\n\n".join(conversation_parts)


# Task 1a 호환 별칭 — 외부 코드/테스트에서 참조 중일 수 있어 유지. 신규 호출
# 코드는 `_split_messages` 사용 권장. 이 함수는 single-string 포맷이 필요한
# 상황에서만 쓰고, SystemMessage 를 "System:" 접두사와 함께 섞어 반환한다.
def _messages_to_prompt(messages: list[BaseMessage]) -> str:
    """레거시 호환: 역할 접두사 단일 문자열. 신규 코드는 `_split_messages` 사용."""
    system_prompt, conversation = _split_messages(messages)
    if not system_prompt:
        return conversation
    system_block = f"System: {system_prompt}"
    return system_block if not conversation else f"{system_block}\n\n{conversation}"


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


# 동시 실행 세마포어 (Task 1d #5) ------------------------------------------
#
# OAuth Max/Pro 쿼터와 머신 메모리 (Node.js 런타임당 300~500MB) 를 보호하기
# 위해 모든 `claude -p` subprocess 호출을 모듈 레벨 세마포어로 통과시킨다.
# LangGraph 가 분석가를 병렬로 띄우거나 백테스트가 여러 종목을 동시에 돌릴
# 때 세마포어가 동일하게 공유된다 — ChatClaudeCodeHeadless 가 여러 번
# 인스턴스화되어도 쿼터는 하나이기 때문.
#
# 세마포어는 lazy singleton: 첫 호출 시 환경변수를 읽고 생성한다. 이후 환경
# 변수 변경은 반영되지 않는다 — 실행 중인 분석이 동시성 예산을 바꾸는 것을
# 막기 위함. 테스트는 `_reset_semaphore()` 로 재초기화한다.

_CONCURRENCY_ENV = "TRADINGAGENTS_CLAUDE_CONCURRENCY"
_DEFAULT_CONCURRENCY = 2

_SEMAPHORE: threading.Semaphore | None = None
_SEMAPHORE_LOCK = threading.Lock()


def _resolve_concurrency() -> int:
    """환경변수에서 동시 실행 한도를 읽는다. 미설정 시 디폴트, 부적합 시 ValueError."""
    raw = os.environ.get(_CONCURRENCY_ENV, "").strip()
    if not raw:
        return _DEFAULT_CONCURRENCY
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{_CONCURRENCY_ENV} must be a positive integer, got {raw!r}"
        ) from exc
    if value <= 0:
        raise ValueError(
            f"{_CONCURRENCY_ENV} must be a positive integer, got {value}"
        )
    return value


def _get_semaphore() -> threading.Semaphore:
    """세마포어 lazy singleton. 테스트는 `_reset_semaphore()` 로 재초기화."""
    global _SEMAPHORE
    if _SEMAPHORE is None:
        with _SEMAPHORE_LOCK:
            if _SEMAPHORE is None:
                _SEMAPHORE = threading.Semaphore(_resolve_concurrency())
    return _SEMAPHORE


def _reset_semaphore() -> None:
    """다음 `_get_semaphore()` 호출 시 환경변수를 다시 읽도록 재설정. 테스트 전용."""
    global _SEMAPHORE
    with _SEMAPHORE_LOCK:
        _SEMAPHORE = None


def _run_claude_subprocess(args: list[str]) -> dict:
    """Claude Code CLI subprocess 호출. JSON payload dict 반환.

    세마포어로 동시 실행이 제한된다 (`TRADINGAGENTS_CLAUDE_CONCURRENCY`,
    디폴트 2). `is_error=True` 응답은 RuntimeError 로 전파한다. subprocess
    자체의 non-zero exit (CalledProcessError) 는 호출부로 그대로 전파된다 —
    Task 1e (#6) 에서 재시도 로직 추가 시 처리.
    """
    with _get_semaphore():
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

    def _base_cli_args(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> list[str]:
        """구조화/비구조화 호출 공통 CLI 인자. 격리 플래그 전체 세트 포함.

        격리 플래그 (ADR-0001 §4.5, CLAUDE.md):
        - `--permission-mode plan`: 호스트 파일/Bash 수정 전면 차단
        - `--no-session-persistence`: 세션 디스크 저장 끔
        - `--disable-slash-commands`: SKILLS / slash command 로딩 차단
        - `--exclude-dynamic-system-prompt-sections`: cwd/env/git status 등
          호스트 종속 섹션을 시스템 프롬프트에서 제거 (프롬프트 캐시 재사용성
          향상 및 호스트 상태 유출 방지)
        - `--append-system-prompt`: SystemMessage 가 있을 때만 추가. 상위
          `~/.claude/CLAUDE.md` 자동 발견 내용을 TradingAgents 지침으로 희석.
        """
        args = [
            "claude",
            "-p", prompt,
            "--output-format", "json",
            "--model", self.model,
            "--no-session-persistence",
            "--permission-mode", "plan",
            "--disable-slash-commands",
            "--exclude-dynamic-system-prompt-sections",
        ]
        if system_prompt:
            args.extend(["--append-system-prompt", system_prompt])
        return args

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        system_prompt, conversation = _split_messages(messages)
        args = self._base_cli_args(conversation, system_prompt=system_prompt)
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
        system_prompt, conversation = _split_messages(messages)
        schema_json = json.dumps(self._schema.model_json_schema())
        args = self._llm._base_cli_args(conversation, system_prompt=system_prompt) + [
            "--json-schema",
            schema_json,
        ]

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
