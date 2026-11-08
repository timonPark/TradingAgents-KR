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
    # #126: 지금 돌고 있는 agent/node 의 사용자 라벨. node_start 에서 세팅되고
    # node_complete/done/error 에서 해제. 폴링 응답 (``GET /api/runs/{id}``) 에
    # 포함되어 UI 가 "지금 어떤 호출을 기다리는지" 즉시 알 수 있게 한다.
    active_node: str | None = None
    active_node_started_at: datetime | None = None
    # #132: 노드별로 축적된 리포트 본문 (node_key → 마크다운). node_complete
    # 이벤트의 content 를 받아 쌓는다. 폴링이나 늦은 접속 시에도 지금까지의
    # 분석 결과를 전부 복구 가능.
    reports: dict[str, str] = field(default_factory=dict)
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

    def find_active(self, ticker: str, trade_date: str) -> RunState | None:
        """같은 종목·기준일의 ``pending``/``running`` 분석을 반환 (#172).

        상태 로그 경로가 종목·기준일 단위라서 분석 설정이 달라도 같은 키로 본다.
        여러 개면 가장 먼저 만들어진 것.
        """
        active = [
            s
            for s in self._states.values()
            if s.ticker == ticker
            and s.trade_date == trade_date
            and s.status in {"pending", "running"}
        ]
        return min(active, key=lambda s: s.created_at, default=None)

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
        elif event_type == "node_start":
            # #126: 지금 돌고 있는 노드/agent 를 state 에 반영.
            state.active_node = event.get("label") or event.get("node")
            started_at = event.get("started_at")
            if started_at:
                try:
                    state.active_node_started_at = datetime.fromisoformat(started_at)
                except (TypeError, ValueError):
                    state.active_node_started_at = None
        elif event_type == "node_complete":
            state.active_node = None
            state.active_node_started_at = None
            # #132: content 가 있으면 reports 에 축적 (라이브 결과 본문).
            node = event.get("node")
            content = event.get("content")
            if isinstance(node, str) and isinstance(content, str) and content.strip():
                state.reports[node] = content
        elif event_type == "done":
            state.status = "done"
            state.active_node = None
            state.active_node_started_at = None
            if "decision" in event:
                state.decision = event["decision"]
        elif event_type == "error":
            state.status = "error"
            state.active_node = None
            state.active_node_started_at = None
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
