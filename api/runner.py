"""Task 14e (#110): 분석 실행을 백그라운드 스레드에서 돌리는 러너.

``TradingAgentsGraph.propagate()`` 는 동기 함수이므로 ``asyncio.run_in_executor``
로 별도 스레드에 던지고, 그 안에서 ``progress_callback`` 으로 받은 이벤트를
``asyncio.run_coroutine_threadsafe`` 로 메인 루프의 큐에 push 한다.

로컬 전용 구현이라 동시 실행 수 제한, 작업 큐, 재시도 등은 두지 않는다.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api.run_store import RunStore

logger = logging.getLogger(__name__)


@dataclass
class RunRequest:
    ticker: str
    trade_date: str
    analysts: tuple[str, ...]
    deep_think_llm: str
    quick_think_llm: str
    effort: str


def build_config(request: RunRequest) -> dict[str, Any]:
    """CLI 가 쓰는 DEFAULT_CONFIG 에 사용자 선택을 덮어씌워 반환."""
    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()
    config["deep_think_llm"] = request.deep_think_llm
    config["quick_think_llm"] = request.quick_think_llm
    config["effort"] = request.effort
    config["quick_effort"] = request.effort
    return config


async def launch_run(request: RunRequest, store: RunStore) -> str:
    """새 run 을 등록하고 백그라운드 태스크를 시작, ``run_id`` 반환."""
    state = store.create(request.ticker, request.trade_date)
    asyncio.create_task(_run_in_background(state.run_id, request, store))
    return state.run_id


async def _run_in_background(run_id: str, request: RunRequest, store: RunStore) -> None:
    loop = asyncio.get_running_loop()

    def emit(event: dict[str, Any]) -> None:
        # 분석 스레드 → 이벤트 루프로 안전 전달.
        loop.call_soon_threadsafe(store.record, run_id, event)

    def graph_progress(event: dict[str, Any]) -> None:
        # The API finishes only after reports are durably available to download.
        if event.get("type") != "done":
            emit(event)

    def work() -> None:
        try:
            from tradingagents.graph.trading_graph import TradingAgentsGraph

            graph = TradingAgentsGraph(
                selected_analysts=request.analysts,
                debug=True,  # Task 14e: node_complete 이벤트를 받기 위함
                config=build_config(request),
                progress_callback=graph_progress,
            )
            final_state, rating = graph.propagate(
                request.ticker, request.trade_date
            )
            # #130: CLI 는 save_reports 를 직접 호출하지만 API 러너는 이걸 누락
            # 하고 있어 웹에서 돌린 run 은 디스크에 리포트가 쌓이지 않았다.
            # Task 14f 리포트 뷰어와 14f 다운로드 (#128) 가 디스크를 소스 오브
            # 트루스로 삼으므로 여기서 CLI 와 동등하게 저장.
            report_path = graph.save_reports(final_state, request.ticker)
            emit({"type": "report_saved", "report_id": Path(report_path).parent.name})
            emit({"type": "done", "decision": rating})
        except Exception as exc:  # noqa: BLE001 — 예외 유형 상관없이 UI 에 알림
            logger.exception("run %s failed", run_id)
            emit({
                "type": "error",
                "message": str(exc),
                "traceback": traceback.format_exc(),
            })

    await loop.run_in_executor(None, work)
