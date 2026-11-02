"""LLM 클라이언트 팩토리.

TradingAgents-KR 포크는 Claude Code 헤드리스가 유일한 LLM 백엔드입니다
(ADR-0001: Claude Code 헤드리스를 유일 LLM 백엔드로). 이 모듈은 config 를
`ClaudeCodeClient` 인스턴스로 변환합니다. 상류의 다중 provider 추상화는
Task 2 (#21) 에서 전부 제거되었습니다.
"""

from typing import Any

from .base_client import BaseLLMClient
from .claude_code_client import ClaudeCodeClient


def create_llm_client(
    provider: str,
    model: str,
    base_url: str | None = None,
    **kwargs: Any,
) -> BaseLLMClient:
    """`claude-code` provider 전용 클라이언트 생성.

    다른 provider 가 요청되면 명확한 ValueError 로 거부합니다 (하드 포크 결정 —
    ADR-0001, CLAUDE.md §4.6).
    """
    provider_lower = provider.lower()
    if provider_lower != "claude-code":
        raise ValueError(
            f"Unsupported LLM provider: {provider!r}. "
            "This fork supports only 'claude-code' (ADR-0001). "
            "External LLM provider abstractions were removed in Task 2 (#21)."
        )
    return ClaudeCodeClient(model, base_url, **kwargs)


def build_llm_kwargs(config: dict) -> dict[str, Any]:
    """Config → `create_llm_client` kwargs.

    Claude Code 는 `effort` 하나만 인수로 받는다 — 티어별 effort 매핑은
    `create_tier_client` 가 담당 (Task 1f #7).
    """
    kwargs: dict[str, Any] = {}
    effort = config.get("effort")
    if effort:
        kwargs["effort"] = effort
    return kwargs


def tier_provider(config: dict, tier: str) -> str:
    """티어의 provider — 하드 포크 결정으로 항상 ``claude-code``."""
    return "claude-code"


def create_tier_client(config: dict, tier: str, **extra: Any) -> BaseLLMClient:
    """``quick`` 또는 ``deep`` 티어의 클라이언트.

    티어별 effort 매핑: deep → ``effort``, quick → ``quick_effort``. 양쪽 모두
    ``effort`` 키로 정규화해 ``build_llm_kwargs`` 로 넘긴다 (tier-agnostic).
    """
    effort_key = "quick_effort" if tier == "quick" else "effort"
    tier_effort = config.get(effort_key)
    tier_config = {**config, "llm_provider": "claude-code"}
    if tier_effort:
        tier_config["effort"] = tier_effort
    kwargs = build_llm_kwargs(tier_config)
    return create_llm_client(
        provider="claude-code",
        model=config[f"{tier}_think_llm"],
        **kwargs,
        **extra,
    )
