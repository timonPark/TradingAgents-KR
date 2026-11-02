"""Canonical provider → API-key env-var mapping.

A single source of truth for which environment variable holds the API key for
each supported LLM provider. Used by the CLI's interactive key prompt and by
anything else that needs to ask "does this provider require a key, and which
env var is it?".

TradingAgents-KR 포크는 Claude Code 헤드리스가 유일한 LLM 백엔드이며
(ADR-0001), OAuth 토큰(`~/.claude/.credentials.json`) 으로 인증합니다 —
환경변수 API 키 자체가 필요 없습니다. Task 2 (#21) 로 다른 provider 들은
전부 제거되었습니다.
"""

from __future__ import annotations

PROVIDER_API_KEY_ENV: dict[str, str | None] = {
    "claude-code": None,
}


def get_api_key_env(provider: str) -> str | None:
    """Return the env var name for `provider`'s API key, or None if not applicable.

    Unknown providers also return None — callers should treat that as "no key
    check possible" rather than as "no key required".
    """
    return PROVIDER_API_KEY_ENV.get(provider.lower())
