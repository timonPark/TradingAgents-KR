"""Task 14e (#110): `/api/runs` 라우트 테스트.

`TradingAgentsGraph` 를 교체해 실제 Claude Code 를 부르지 않는다. 이 테스트는
요청 스키마, 런 상태 전이, SSE 스트림의 start/완료 흐름만 검증한다.
"""

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


class _FakeGraph:
    """TradingAgentsGraph 대체. 짧은 진행 시퀀스를 progress_callback 으로 보낸다."""

    def __init__(self, *, progress_callback, **kwargs) -> None:
        self._cb = progress_callback

    def propagate(self, ticker: str, trade_date: str) -> tuple[dict, str]:
        self._cb({"type": "run_start", "ticker": ticker, "trade_date": trade_date})
        self._cb({"type": "node_complete", "node": "market_report", "label": "시장 분석가"})
        self._cb({"type": "node_complete", "node": "news_report", "label": "뉴스 분석가"})
        self._cb({"type": "done", "decision": "Buy"})
        return {"final_trade_decision": "Rating: Buy"}, "Buy"


class _FailingGraph:
    def __init__(self, *, progress_callback, **kwargs) -> None:
        self._cb = progress_callback

    def propagate(self, ticker: str, trade_date: str):
        self._cb({"type": "run_start", "ticker": ticker, "trade_date": trade_date})
        raise RuntimeError("boom")


def _wait_for(predicate, *, timeout: float = 2.0, interval: float = 0.02) -> None:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("predicate did not become true within timeout")


def test_post_run_returns_run_id_and_transitions_to_done(monkeypatch) -> None:
    import api.runner as runner_module

    monkeypatch.setattr(runner_module, "build_config", lambda req: {})
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.TradingAgentsGraph",
        _FakeGraph,
        raising=True,
    )

    client = TestClient(create_app())

    response = client.post(
        "/api/runs",
        json={
            "ticker": "005930",
            "trade_date": "2024-01-05",
            "analysts": ["market", "news"],
        },
    )
    assert response.status_code == 201, response.text
    run_id = response.json()["run_id"]

    _wait_for(lambda: (store.get(run_id).status if store.get(run_id) else None) == "done")

    snapshot = client.get(f"/api/runs/{run_id}").json()
    assert snapshot["status"] == "done"
    assert snapshot["decision"] == "Buy"


def test_post_run_rejects_invalid_ticker() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/runs",
        json={"ticker": "ABCDEF", "trade_date": "2024-01-05"},
    )
    assert response.status_code == 422


def test_post_run_rejects_bad_date() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/runs",
        json={"ticker": "005930", "trade_date": "20240105"},
    )
    assert response.status_code == 422


def test_get_unknown_run_returns_404() -> None:
    client = TestClient(create_app())
    assert client.get("/api/runs/does-not-exist").status_code == 404


def test_sse_stream_replays_history_and_closes_on_done(monkeypatch) -> None:
    import api.runner as runner_module

    monkeypatch.setattr(runner_module, "build_config", lambda req: {})
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.TradingAgentsGraph",
        _FakeGraph,
        raising=True,
    )

    client = TestClient(create_app())
    post = client.post(
        "/api/runs",
        json={"ticker": "005930", "trade_date": "2024-01-05"},
    )
    run_id = post.json()["run_id"]

    _wait_for(lambda: (store.get(run_id).status if store.get(run_id) else None) == "done")

    # done 이후 접속 — replay 로 전체 이벤트를 받고 스트림이 닫혀야 한다.
    with client.stream("GET", f"/api/runs/{run_id}/events") as resp:
        assert resp.status_code == 200
        body = b"".join(resp.iter_bytes())

    text = body.decode("utf-8")
    # SSE 포맷: "event: run_start\ndata: {...}\n\n"
    assert "event: run_start" in text
    assert "event: node_complete" in text
    assert "event: done" in text
    # 완료된 run 의 큐는 더 이상 열려있지 않아야 한다 — SENTINEL 로 종료.
    assert text.count("event: done") == 1


def test_error_run_records_status(monkeypatch) -> None:
    import api.runner as runner_module

    monkeypatch.setattr(runner_module, "build_config", lambda req: {})
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.TradingAgentsGraph",
        _FailingGraph,
        raising=True,
    )

    client = TestClient(create_app())
    run_id = client.post(
        "/api/runs",
        json={"ticker": "005930", "trade_date": "2024-01-05"},
    ).json()["run_id"]

    _wait_for(lambda: (store.get(run_id).status if store.get(run_id) else None) == "error")
    snap = client.get(f"/api/runs/{run_id}").json()
    assert snap["status"] == "error"
    assert "boom" in (snap["error"] or "")
