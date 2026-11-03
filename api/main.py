"""FastAPI 앱 팩토리.

로컬 기동:

    uvicorn api.main:app --reload --port 8000

환경변수 설정은 ``api.config`` 참조.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import load_settings
from api.routes import health, symbols


def create_app() -> FastAPI:
    """FastAPI 앱 조립. 테스트에서도 같은 팩토리로 fresh 앱을 받는다."""
    settings = load_settings()

    app = FastAPI(
        title="TradingAgents-KR API",
        description="한국 증시 분석 백엔드 (로컬 전용).",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api", tags=["meta"])
    app.include_router(symbols.router, prefix="/api/symbols", tags=["symbols"])
    return app


app = create_app()
