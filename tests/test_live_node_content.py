"""#132: node_complete 이벤트에 content 포함 + RunState.reports 축적."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from api.main import create_app  # noqa: E402
from api.run_store import store  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    store.reset()
    yield
    store.reset()


@pytest.mark.parametrize(("node", "result", "expected"), [
    ("Market Analyst", {"market_report": "시장 본문"}, "시장 본문"),
    ("Bull Researcher", {"investment_debate_state": {"history": "과거", "current_response": "새 발언"}}, "새 발언"),
    ("Bear Researcher", {"investment_debate_state": {"current_response": "약세"}}, "약세"),
    ("Research Manager", {"investment_plan": "계획"}, "계획"),
    ("Trader", {"trader_investment_plan": "거래"}, "거래"),
    ("Aggressive Analyst", {"risk_debate_state": {"current_aggressive_response": "공격"}}, "공격"),
    ("Conservative Analyst", {"risk_debate_state": {"current_conservative_response": "보수"}}, "보수"),
    ("Neutral Analyst", {"risk_debate_state": {"current_neutral_response": "중립"}}, "중립"),
    ("Portfolio Manager", {"final_trade_decision": "결정"}, "결정"),
    ("Market Analyst", None, ""),
])
def test_render_only_current_node_output(node, result, expected):
    from tradingagents.graph.trading_graph import _render_report_content
    assert _render_report_content(result, node) == expected


def test_node_complete_event_carries_content_in_debug_mode(tmp_path) -> None:
    from tradingagents.graph.propagation import Propagator
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.memory import TradingMemoryLog

    graph = object.__new__(TradingAgentsGraph)
    graph.config = {
        "memory_log_path": str(tmp_path / "mem.md"),
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "results_dir": str(tmp_path),
    }
    graph.memory_log = TradingMemoryLog(graph.config)
    graph.propagator = Propagator()
    graph.selected_analysts = ["market"]
    graph.settle_pending = lambda t: None
    graph.resolve_instrument_context = lambda t, a="stock", d=None: ""
    graph._memory_as_of = lambda d: None
    graph._log_state = lambda *a, **k: None
    graph.clear_checkpoint_on_success = lambda *a, **k: None
    graph._resuming = False
    graph.debug = True
    events: list[dict] = []
    graph.progress_callback = events.append
    graph.propagator.get_graph_args = lambda callbacks=None: {}

    def fake_iter(input_state, **kwargs):
        yield {
            "kind": "task_complete", "name": "Market Analyst",
            "result": {"market_report": "## 기술적 분석\n\nRSI 과열"},
        }
        yield {
            "kind": "task_complete", "name": "Portfolio Manager",
            "result": {"final_trade_decision": "Rating: Buy\n\n삼성전자 매수 추천"},
        }

    graph._iter_graph_events = fake_iter
    graph._run_graph("005930", "2024-01-05")

    completes = [e for e in events if e["type"] == "node_complete"]
    market = next(e for e in completes if e["node"] == "Market Analyst")
    assert "RSI 과열" in market["content"]
    final = next(e for e in completes if e["node"] == "Portfolio Manager")
    assert "삼성전자 매수 추천" in final["content"]


def test_snapshot_exposes_reports_dict(monkeypatch) -> None:
    import api.runner as runner_module

    class _GraphWithReports:
        def __init__(self, *, progress_callback, **kwargs) -> None:
            self._cb = progress_callback

        def propagate(self, ticker: str, trade_date: str):
            self._cb({"type": "run_start", "ticker": ticker, "trade_date": trade_date})
            self._cb({
                "type": "node_complete",
                "node": "market_report",
                "label": "시장 분석가",
                "content": "## 기술적\n\nRSI 과열",
            })
            self._cb({
                "type": "node_complete",
                "node": "news_report",
                "label": "뉴스 분석가",
                "content": "## 뉴스\n\n신약 임상 성공",
            })
            self._cb({"type": "done", "decision": "Buy"})
            return {"final_trade_decision": "Rating: Buy"}, "Buy"

        def save_reports(self, final_state, ticker):
            return "/tmp/reports/005930_20240105_120000/complete_report.md"

    monkeypatch.setattr(runner_module, "build_config", lambda req: {})
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.TradingAgentsGraph",
        _GraphWithReports,
        raising=True,
    )

    client = TestClient(create_app())
    run_id = client.post(
        "/api/runs",
        json={"ticker": "005930", "trade_date": "2024-01-05"},
    ).json()["run_id"]

    import time

    deadline = time.time() + 2.0
    while time.time() < deadline:
        st = store.get(run_id)
        if st and st.status == "done":
            break
        time.sleep(0.02)

    snap = client.get(f"/api/runs/{run_id}").json()
    assert "market_report" in snap["reports"]
    assert "RSI 과열" in snap["reports"]["market_report"]
    assert "신약 임상 성공" in snap["reports"]["news_report"]
