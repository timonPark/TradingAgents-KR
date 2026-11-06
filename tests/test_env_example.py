"""#169: ``.env.example`` 은 실제 코드·``.env`` 와 어긋나지 않아야 한다 (원작 설정이 그대로 남아 있었다)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_VAR = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]+)=", re.MULTILINE)
_SOURCES = [*(ROOT / d for d in ("tradingagents", "api", "cli")), ROOT / "docker-compose.yml"]
# 사용자가 반드시 채워야 하는 vendor 키 — 예시 맨 위에 값 없이 노출돼야 한다.
_VENDOR_KEYS = {"DART_API_KEY", "ECOS_API_KEY", "NAVER_API_HUB_CLIENT_ID", "NAVER_API_HUB_CLIENT_SECRET",
                "KRX_ID", "KRX_PW"}
# 하드 포크 결정(ADR-0001, CLAUDE.md 4.6)으로 `.env` 에 두면 안 되는 외부 LLM 키.
_FORBIDDEN = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY",
              "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "TRADINGAGENTS_LLM_PROVIDER")


def _example_vars() -> set[str]:
    return set(_VAR.findall((ROOT / ".env.example").read_text(encoding="utf-8")))


def _source_text() -> str:
    parts = []
    for src in _SOURCES:
        files = [src] if src.is_file() else src.rglob("*.py")
        parts.extend(f.read_text(encoding="utf-8", errors="ignore") for f in files)
    return "\n".join(parts)


@pytest.mark.unit
def test_every_example_variable_is_read_by_the_code():
    text = _source_text()
    unused = sorted(v for v in _example_vars() if not re.search(rf"\b{v}\b", text))
    assert unused == [], f".env.example 에만 있고 코드가 읽지 않는 변수: {unused}"


@pytest.mark.unit
def test_vendor_keys_are_listed_and_left_blank():
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    for key in _VENDOR_KEYS:
        assert f"{key}=" in lines, f"{key} 가 예시에 값 없이 있어야 한다"


@pytest.mark.unit
def test_no_external_llm_keys_in_the_example():
    leaked = sorted(set(_FORBIDDEN) & _example_vars())
    assert leaked == [], f"하드 포크에서 쓰지 않는 변수: {leaked}"
