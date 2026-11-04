"""Task 14e (#110): 분석 run 의 인메모리 상태 저장소.

로컬 전용 범위이므로 DB/영속화 없이 프로세스 수명 동안만 유지한다. 각 run 은
``asyncio.Queue`` 에 이벤트를 흘려 넣고 SSE 라우트가 그걸 읽어 스트림한다.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# SSE 큐에 들어오는 이벤트 shape — ``type`` 키는 필수. 나머지는 자유.
Event = dict[str, Any]

# 각 run 의 종착 신호. 큐에 들어오면 SSE 라우트가 스트림을 닫는다.
SENTINEL: Event = {"type": "__end__"}


@dataclass
class RunState:
    """단일 분석 run 의 상태 스냅샷."""

    run_id: str
    ticker: str
    trade_date: str
    status: str = "pending"  # pending | running | done | error
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    decision: str | None = None
    error: str | None = None
    # 완료된 이벤트들의 순서가 유지된 히스토리. 늦게 붙는 SSE 클라이언트가
    # 처음부터 replay 할 수 있도록 보관.
    events: list[Event] = field(default_factory=list)


class RunStore:
    """run_id 별 상태 + 이벤트 큐 관리.

    thread-safe 하지 않음 (asyncio 단일 루프 가정). 분석 실행은 별도 스레드
    (``run_in_executor``) 에서 돌지만 큐 push 는 ``asyncio.run_coroutine_threadsafe``
    로 루프에 넘겨서 처리한다.
    """

    def __init__(self) -> None:
        self._states: dict[str, RunState] = {}
        self._queues: dict[str, asyncio.Queue[Event]] = {}

    def create(self, ticker: str, trade_date: str) -> RunState:
        run_id = uuid.uuid4().hex[:12]
        state = RunState(run_id=run_id, ticker=ticker, trade_date=trade_date)
        self._states[run_id] = state
        self._queues[run_id] = asyncio.Queue()
        return state

    def get(self, run_id: str) -> RunState | None:
        return self._states.get(run_id)

    def get_queue(self, run_id: str) -> asyncio.Queue[Event] | None:
        return self._queues.get(run_id)

    def record(self, run_id: str, event: Event) -> None:
        """상태를 이벤트로 업데이트하고 큐에 push.

        ``type`` 별 상태 전이:
        - ``run_start`` → ``status = "running"``
        - ``done``       → ``status = "done"`` + ``decision`` 반영 → SENTINEL push
        - ``error``      → ``status = "error"`` + ``error`` 반영 → SENTINEL push
        """
        state = self._states.get(run_id)
        if state is None:
            logger.warning("record() called for unknown run_id=%s", run_id)
            return

        state.updated_at = datetime.now(UTC)
        state.events.append(event)

        event_type = event.get("type")
        if event_type == "run_start":
            state.status = "running"
        elif event_type == "done":
            state.status = "done"
            if "decision" in event:
                state.decision = event["decision"]
        elif event_type == "error":
            state.status = "error"
            state.error = event.get("message")

        queue = self._queues.get(run_id)
        if queue is None:
            return
        queue.put_nowait(event)
        if event_type in {"done", "error"}:
            queue.put_nowait(SENTINEL)

    def list_recent(self, limit: int = 20) -> list[RunState]:
        """최근 생성 순으로 ``limit`` 개 반환. 리포트 사이드바에서 사용."""
        return sorted(
            self._states.values(), key=lambda s: s.created_at, reverse=True
        )[:limit]

    def reset(self) -> None:
        """테스트 격리용. 프로덕션에서는 호출하지 않는다."""
        self._states.clear()
        self._queues.clear()


# 프로세스 단일 인스턴스. FastAPI 라우트/의존성이 이것을 바라본다.
store = RunStore()
