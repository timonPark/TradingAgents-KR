"""API 설정 로드.

환경변수:
- ``TRADINGAGENTS_API_PORT`` — uvicorn 기동 포트 (기본 8000)
- ``TRADINGAGENTS_API_CORS_ORIGINS`` — 콤마로 구분된 origin 리스트
  (기본 ``http://localhost:4321``, Astro dev 서버)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_DEFAULT_PORT = 8000
_DEFAULT_CORS_ORIGINS: tuple[str, ...] = ("http://localhost:4321",)


@dataclass(frozen=True)
class Settings:
    port: int
    cors_origins: tuple[str, ...]


def _parse_port(raw: str) -> int:
    raw = raw.strip()
    if not raw:
        return _DEFAULT_PORT
    try:
        value = int(raw)
    except ValueError:
        logger.warning("TRADINGAGENTS_API_PORT=%r 해석 실패, 기본값 사용", raw)
        return _DEFAULT_PORT
    if not 1 <= value <= 65535:
        logger.warning("TRADINGAGENTS_API_PORT=%d 는 범위를 벗어남, 기본값 사용", value)
        return _DEFAULT_PORT
    return value


def _parse_origins(raw: str) -> tuple[str, ...]:
    raw = raw.strip()
    if not raw:
        return _DEFAULT_CORS_ORIGINS
    parts = tuple(origin.strip() for origin in raw.split(",") if origin.strip())
    return parts or _DEFAULT_CORS_ORIGINS


def load_settings() -> Settings:
    """환경변수에서 설정 로드."""
    return Settings(
        port=_parse_port(os.environ.get("TRADINGAGENTS_API_PORT", "")),
        cors_origins=_parse_origins(
            os.environ.get("TRADINGAGENTS_API_CORS_ORIGINS", "")
        ),
    )
