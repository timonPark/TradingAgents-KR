"""헬스 체크 엔드포인트."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """``{"status": "ok"}`` 반환. uvicorn 기동 확인용."""
    return {"status": "ok"}
