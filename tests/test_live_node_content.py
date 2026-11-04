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


def test_render_report_content_string_passthrough() -> None:
    from tradingagents.graph.trading_graph import _render_report_content

    assert _render_report_content("# 시장 분석\n\n본문") == "# 시장 분석\n\n본문"


def test_render_report_content_dict_flatten_known_fields() -> None:
    from tradingagents.graph.trading_graph import _render_report_content

    out = _render_report_content({
        "bull_history": "강세 주장",
        "bear_history": "약세 주장",
        "count": 2,  # 숫자 메타 — 노출 안 됨
        "latest_speaker": "Bear",
    })
    assert "강세 논증" in out and "강세 주장" in out
    assert "약세 논증" in out and "약세 주장" in out
    assert "최근 발언자" in out


def test_render_report_content_unknown_type_returns_empty() -> None:
    from tradingagents.graph.trading_graph import _render_report_content

    assert _render_report_content(42) == ""
    assert _render_report_content(None) == ""


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
            "kind": "state_update",
            "state": {"market_report": "## 기술적 분석\n\nRSI 과열"},
        }
        yield {
            "kind": "state_update",
            "state": {"final_trade_decision": "Rating: Buy\n\n삼성전자 매수 추천"},
        }

    graph._iter_graph_events = fake_iter
    graph._run_graph("005930", "2024-01-05")

    completes = [e for e in events if e["type"] == "node_complete"]
    market = next(e for e in completes if e["node"] == "market_report")
    assert "RSI 과열" in market["content"]
    final = next(e for e in completes if e["node"] == "final_trade_decision")
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
            return None

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
