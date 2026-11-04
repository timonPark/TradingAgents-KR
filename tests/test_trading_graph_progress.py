"""Task 14e (#110): `progress_callback` 훅 단위 테스트.

실제 LangGraph 실행은 모킹하고, `_run_graph` 가 run_start → node_complete → done
이벤트를 올바른 순서로 emit 하는지, 콜백 예외는 삼켜지는지 검증한다.
"""

from __future__ import annotations

import logging

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph


def _bare_graph(tmp_path):
    """``__init__`` 을 우회한 최소 더블. 필요한 속성만 수동 주입."""
    from tradingagents.graph.propagation import Propagator
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
    return graph


@pytest.mark.unit
def test_progress_callback_receives_run_start_and_done(tmp_path) -> None:
    graph = _bare_graph(tmp_path)
    graph.debug = False
    graph.progress_callback = lambda event: events.append(event)
    graph.propagator.get_graph_args = lambda callbacks=None: {}
    graph.graph = type(
        "G",
        (),
        {"invoke": lambda self, i, **k: {"final_trade_decision": "Rating: Hold\n\nx"}},
    )()
    events: list[dict] = []

    graph._run_graph("005930", "2024-01-05")

    types = [e["type"] for e in events]
    assert types[0] == "run_start"
    assert events[0]["ticker"] == "005930"
    assert events[0]["trade_date"] == "2024-01-05"
    assert types[-1] == "done"
    assert "decision" in events[-1]


@pytest.mark.unit
def test_progress_callback_fires_node_complete_in_debug_mode(tmp_path) -> None:
    """실제 task 순서로 본문을 보내고 state 갱신과 내부 노드는 중복 표시하지 않는다."""
    graph = _bare_graph(tmp_path)
    graph.debug = True
    events: list[dict] = []
    graph.progress_callback = events.append
    graph.propagator.get_graph_args = lambda callbacks=None: {}

    def fake_iter(input_state, **kwargs):
        for name, key, content in [
            ("Market Analyst", "market_report", "시장 본문"),
            ("News Analyst", "news_report", "뉴스 본문"),
            ("Trader", "trader_investment_plan", "계획"),
            ("Portfolio Manager", "final_trade_decision", "Rating: Buy"),
        ]:
            result = {key: content}
            yield {"kind": "task_complete", "name": name, "result": result}
            yield {"kind": "state_update", "state": result}
        yield {"kind": "task_complete", "name": "agent", "result": {}}
        yield {"kind": "task_start", "name": "Memory Log"}

    graph._iter_graph_events = fake_iter

    graph._run_graph("005930", "2024-01-05")

    node_events = [e for e in events if e["type"] == "node_complete"]
    labels = [e["label"] for e in node_events]
    assert labels == ["시장 분석가", "뉴스 분석가", "트레이더", "포트폴리오 매니저"]
    assert all(e["content"] for e in node_events)


@pytest.mark.unit
def test_task_start_and_complete_events_in_debug_mode(tmp_path) -> None:
    """#126: subgraph task 시작/완료가 node_start / node_complete 로 emit 되는지."""
    graph = _bare_graph(tmp_path)
    graph.debug = True
    events: list[dict] = []
    graph.progress_callback = events.append
    graph.propagator.get_graph_args = lambda callbacks=None: {}

    def fake_iter(input_state, **kwargs):
        yield {
            "kind": "task_start",
            "name": "Bear Researcher",
            "started_at": "2024-01-05T00:00:00+00:00",
        }
        yield {
            "kind": "task_complete",
            "name": "Bear Researcher",
            "elapsed_ms": 1234,
        }

    graph._iter_graph_events = fake_iter

    graph._run_graph("005930", "2024-01-05")

    starts = [e for e in events if e["type"] == "node_start"]
    completes = [e for e in events if e["type"] == "node_complete"]
    assert len(starts) == 1
    assert starts[0]["node"] == "Bear Researcher"
    assert starts[0]["label"] == "약세 리서처"
    assert "started_at" in starts[0]
    assert any(e.get("node") == "Bear Researcher" for e in completes)
    bear_complete = next(e for e in completes if e.get("node") == "Bear Researcher")
    assert bear_complete["label"] == "약세 리서처"
    assert bear_complete["elapsed_ms"] == 1234


@pytest.mark.unit
def test_progress_callback_exceptions_are_swallowed(tmp_path, caplog) -> None:
    graph = _bare_graph(tmp_path)
    graph.debug = False

    def raising_callback(event):
        raise RuntimeError("UI died")

    graph.progress_callback = raising_callback
    graph.propagator.get_graph_args = lambda callbacks=None: {}
    graph.graph = type(
        "G",
        (),
        {"invoke": lambda self, i, **k: {"final_trade_decision": "Rating: Hold\n\n..."}},
    )()

    with caplog.at_level(logging.WARNING, logger="tradingagents.graph.trading_graph"):
        # 분석 파이프라인이 콜백 예외로 크래시하면 안 됨.
        graph._run_graph("005930", "2024-01-05")

    assert any("progress_callback raised" in rec.message for rec in caplog.records)


@pytest.mark.unit
def test_missing_progress_callback_attribute_is_safe(tmp_path) -> None:
    """``object.__new__`` 로 생성된 더블에 ``progress_callback`` 이 없어도 안전."""
    graph = _bare_graph(tmp_path)
    graph.debug = False
    # progress_callback 을 아예 설정하지 않음.
    graph.propagator.get_graph_args = lambda callbacks=None: {}
    graph.graph = type(
        "G",
        (),
        {"invoke": lambda self, i, **k: {"final_trade_decision": "Rating: Hold\n\n..."}},
    )()

    # AttributeError 없이 돌면 성공.
    graph._run_graph("005930", "2024-01-05")


@pytest.mark.unit
def test_non_callable_progress_callback_is_ignored(tmp_path) -> None:
    """MagicMock-style auto-attribute 같은 비-callable 은 무시된다."""
    graph = _bare_graph(tmp_path)
    graph.debug = False
    graph.progress_callback = "not a function"  # 의도적 잘못된 값
    graph.propagator.get_graph_args = lambda callbacks=None: {}
    graph.graph = type(
        "G",
        (),
        {"invoke": lambda self, i, **k: {"final_trade_decision": "Rating: Hold\n\n..."}},
    )()

    # 예외 없이 완료.
    graph._run_graph("005930", "2024-01-05")
