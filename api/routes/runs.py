"""Task 14e (#110): 분석 실행 라우트.

- ``POST /api/runs``                  — 새 run 시작, ``{run_id, already_running}`` 반환.
                                        같은 종목·기준일 분석이 이미 돌고 있으면 새로
                                        시작하지 않고 그 ``run_id`` 를 200 으로 반환 (#172)
- ``GET  /api/runs``                  — 최근 run 목록. ``ticker``/``trade_date``/``status`` 로
                                        거른 뒤 ``limit`` 적용, ``include_reports=false`` 로
                                        보고서 본문 제외 (#171)
- ``GET  /api/runs/{run_id}``         — 상태 스냅샷
- ``GET  /api/runs/{run_id}/events``  — SSE 스트림 (완료 또는 에러 시 종료)
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from api.run_store import RunState, store
from api.runner import RunRequest, launch_run

logger = logging.getLogger(__name__)

router = APIRouter()


class RunCreate(BaseModel):
    """새 run 생성 요청 body."""

    ticker: str = Field(pattern=r"^\d{6}$", description="6자리 KRX 종목코드")
    trade_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    analysts: list[Literal["market", "social", "news", "fundamentals"]] = Field(
        default_factory=lambda: ["market", "social", "news", "fundamentals"],
        min_length=1,
    )
    deep_think_llm: str = Field(default="sonnet")
    quick_think_llm: str = Field(default="haiku")
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"


class RunCreated(BaseModel):
    run_id: str
    # #172: true 면 같은 종목·기준일 분석이 이미 돌고 있어 새로 시작하지 않고
    # 그 run_id 를 돌려준 것이다 (HTTP 200). 새로 시작했으면 false (HTTP 201).
    already_running: bool = False


class RunSnapshot(BaseModel):
    run_id: str
    ticker: str
    trade_date: str
    status: str
    created_at: str
    updated_at: str
    decision: str | None = None
    error: str | None = None
    # #126: 지금 돌고 있는 agent 라벨 (예: "약세 리서처"). running 이 아닐 때는
    # null. active_node_started_at 는 ISO8601 (UTC).
    active_node: str | None = None
    active_node_started_at: str | None = None
    # #132: 노드별 리포트 본문. 폴링만으로도 지금까지의 분석 결과 전체 복구.
    reports: dict[str, str] = Field(default_factory=dict)


def _snapshot(state: RunState, *, include_reports: bool = True) -> RunSnapshot:
    return RunSnapshot(
        run_id=state.run_id,
        ticker=state.ticker,
        trade_date=state.trade_date,
        status=state.status,
        created_at=state.created_at.isoformat(),
        updated_at=state.updated_at.isoformat(),
        decision=state.decision,
        error=state.error,
        active_node=state.active_node,
        active_node_started_at=(
            state.active_node_started_at.isoformat()
            if state.active_node_started_at is not None
            else None
        ),
        reports=dict(state.reports) if include_reports else {},
    )


@router.post("", response_model=RunCreated, status_code=status.HTTP_201_CREATED)
async def create_run(body: RunCreate, response: Response) -> RunCreated:
    # 확인과 등록 사이에 await 가 없어 단일 이벤트 루프에서 끼어들 틈이 없다.
    active = store.find_active(body.ticker, body.trade_date)
    if active is not None:
        response.status_code = status.HTTP_200_OK
        return RunCreated(run_id=active.run_id, already_running=True)

    request = RunRequest(
        ticker=body.ticker,
        trade_date=body.trade_date,
        analysts=tuple(body.analysts),
        deep_think_llm=body.deep_think_llm,
        quick_think_llm=body.quick_think_llm,
        effort=body.effort,
    )
    run_id = await launch_run(request, store)
    return RunCreated(run_id=run_id)


@router.get("", response_model=list[RunSnapshot])
def list_runs(
    limit: int = 20,
    ticker: str | None = None,
    trade_date: str | None = None,
    run_status: Literal["pending", "running", "done", "error"] | None = Query(
        default=None, alias="status"
    ),
    include_reports: bool = True,
) -> list[RunSnapshot]:
    # #171: 조건을 안 주면 지금과 같다 (하위 호환). reports 는 목록에서만 뺀다.
    runs = store.list_recent(
        limit=limit, ticker=ticker, trade_date=trade_date, status=run_status
    )
    return [_snapshot(state, include_reports=include_reports) for state in runs]


@router.get("/{run_id}", response_model=RunSnapshot)
def get_run(run_id: str) -> RunSnapshot:
    state = store.get(run_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return _snapshot(state)


@router.get("/{run_id}/events")
async def stream_events(run_id: str) -> EventSourceResponse:
    state = store.get(run_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    queue = store.get_queue(run_id)
    if queue is None:
        raise HTTPException(status.HTTP_410_GONE, "run queue closed")

    async def generator() -> AsyncIterator[dict[str, str]]:
        # Each subscriber has its own cursor: replay and live delivery cannot
        # duplicate events or consume another subscriber's queue entries.
        cursor = 0
        while True:
            batch = state.events[cursor:]
            for event in batch:
                cursor += 1
                yield {"event": event.get("type", "message"), "data": json.dumps(event, ensure_ascii=False)}
                if event.get("type") in {"done", "error"}:
                    return
            await asyncio.sleep(0.1)

    # ping 은 프록시 타임아웃 방어용 주석 라인.
    return EventSourceResponse(generator(), ping=15)


__all__ = ["router"]


# 테스트에서만 참고. 직접 호출 금지.
_asyncio = asyncio  # 재export 로 lint 무시 억제가 아님, 실제 모듈 side effect 없음
