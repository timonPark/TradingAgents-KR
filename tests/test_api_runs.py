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

    def save_reports(self, final_state, ticker):  # #130
        return "/tmp/reports/005930_20240105_120000/complete_report.md"


class _FailingGraph:
    def __init__(self, *, progress_callback, **kwargs) -> None:
        self._cb = progress_callback

    def propagate(self, ticker: str, trade_date: str):
        self._cb({"type": "run_start", "ticker": ticker, "trade_date": trade_date})
        raise RuntimeError("boom")

    def save_reports(self, final_state, ticker):  # #130
        return "/tmp/reports/005930_20240105_120000/complete_report.md"


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
    assert text.index("event: report_saved") < text.index("event: done")
    assert text.count("event: run_start") == 1
    assert '"report_id": "005930_20240105_120000"' in text
    assert "event: done" in text
    # 완료된 run 의 큐는 더 이상 열려있지 않아야 한다 — SENTINEL 로 종료.
    assert text.count("event: done") == 1


def test_snapshot_exposes_active_node_during_run(monkeypatch) -> None:
    """#126: node_start → snapshot.active_node 세팅, node_complete → 해제."""
    import threading
    release = threading.Event()
    import api.runner as runner_module

    class _GraphWithActive:
        def __init__(self, *, progress_callback, **kwargs) -> None:
            self._cb = progress_callback

        def propagate(self, ticker: str, trade_date: str):
            self._cb({"type": "run_start", "ticker": ticker, "trade_date": trade_date})
            self._cb({
                "type": "node_start",
                "node": "Bear Researcher",
                "label": "약세 리서처",
                "started_at": "2024-01-05T00:00:00+00:00",
            })
            release.wait(timeout=5)
            return {"final_trade_decision": "Rating: Hold"}, "Hold"

        def save_reports(self, final_state, ticker):  # #130
            return "/tmp/reports/005930_20240105_120000/complete_report.md"

    monkeypatch.setattr(runner_module, "build_config", lambda req: {})
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.TradingAgentsGraph",
        _GraphWithActive,
        raising=True,
    )

    with TestClient(create_app()) as client:
        run_id = client.post(
            "/api/runs",
            json={"ticker": "005930", "trade_date": "2024-01-05"},
        ).json()["run_id"]

        _wait_for(
            lambda: (store.get(run_id).active_node if store.get(run_id) else None)
            == "약세 리서처"
        )
        snap = client.get(f"/api/runs/{run_id}").json()
        assert snap["active_node"] == "약세 리서처"
        assert snap["active_node_started_at"] is not None
        release.set()
        _wait_for(lambda: store.get(run_id).status == "done")


def test_runner_calls_save_reports_on_success(monkeypatch, tmp_path) -> None:
    """#130: 완료된 run 은 디스크에 리포트 트리가 쌓여야 한다.

    CLI 는 ``save_reports`` 를 직접 호출하지만 API 러너가 누락하고 있어
    웹에서 실행된 run 의 리포트가 사라졌던 버그의 리그레션 가드.
    """
    import api.runner as runner_module

    saved: dict[str, object] = {}

    class _CapturingGraph:
        def __init__(self, *, progress_callback, **kwargs) -> None:
            self._cb = progress_callback

        def propagate(self, ticker: str, trade_date: str):
            self._cb({"type": "run_start", "ticker": ticker, "trade_date": trade_date})
            self._cb({"type": "done", "decision": "Buy"})
            return {"final_trade_decision": "Rating: Buy"}, "Buy"

        def save_reports(self, final_state, ticker):
            saved["final_state"] = final_state
            saved["ticker"] = ticker
            path = tmp_path / f"{ticker}.md"
            path.write_text("stub", encoding="utf-8")
            return path

    monkeypatch.setattr(runner_module, "build_config", lambda req: {})
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.TradingAgentsGraph",
        _CapturingGraph,
        raising=True,
    )

    client = TestClient(create_app())
    run_id = client.post(
        "/api/runs",
        json={"ticker": "005930", "trade_date": "2024-01-05"},
    ).json()["run_id"]

    _wait_for(
        lambda: (store.get(run_id).status if store.get(run_id) else None) == "done"
    )

    assert saved.get("ticker") == "005930"
    assert isinstance(saved.get("final_state"), dict)


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


def test_save_failure_is_error_not_done(monkeypatch):
    class SaveFailure(_FakeGraph):
        def save_reports(self, final_state, ticker):
            raise OSError("저장 실패")
    monkeypatch.setattr("tradingagents.graph.trading_graph.TradingAgentsGraph", SaveFailure)
    with TestClient(create_app()) as client:
        run_id = client.post("/api/runs", json={"ticker": "005930", "trade_date": "2024-01-05"}).json()["run_id"]
        _wait_for(lambda: store.get(run_id).status == "error")
        events = store.get(run_id).events
        assert not any(e["type"] == "done" for e in events)
        assert events[-1]["message"] == "저장 실패"


def test_live_sse_subscribers_receive_each_event_once():
    import asyncio
    import json

    from api.routes.runs import stream_events

    async def check():
        run = store.create("005930", "2024-01-05")
        first = {"type": "run_start"}
        second = {"type": "node_complete", "node": "Market Analyst", "content": "본문"}
        store.record(run.run_id, first)
        stream1 = (await stream_events(run.run_id)).body_iterator
        assert json.loads((await anext(stream1))["data"]) == first
        store.record(run.run_id, second)
        assert json.loads((await anext(stream1))["data"]) == second
        stream2 = (await stream_events(run.run_id)).body_iterator
        assert json.loads((await anext(stream2))["data"]) == first
        assert json.loads((await anext(stream2))["data"]) == second
        store.record(run.run_id, {"type": "done"})
        for stream in (stream1, stream2):
            assert json.loads((await anext(stream))["data"])["type"] == "done"
            with pytest.raises(StopAsyncIteration):
                await anext(stream)
    asyncio.run(check())


def test_runner_publishes_real_report_directory_id(monkeypatch, tmp_path):
    from tradingagents.reporting import write_report_tree
    class RealReportGraph(_FakeGraph):
        def save_reports(self, final_state, ticker):
            return write_report_tree(final_state, ticker, tmp_path / "005930_20240105_120000")
    monkeypatch.setattr("tradingagents.graph.trading_graph.TradingAgentsGraph", RealReportGraph)
    with TestClient(create_app()) as client:
        run_id = client.post("/api/runs", json={"ticker": "005930", "trade_date": "2024-01-05"}).json()["run_id"]
        _wait_for(lambda: store.get(run_id).status == "done")
        events = store.get(run_id).events
        assert events[-2] == {"type": "report_saved", "report_id": "005930_20240105_120000"}
        assert (tmp_path / events[-2]["report_id"] / "complete_report.md").is_file()


# --- #172: 같은 종목·기준일 분석이 돌고 있으면 새로 시작하지 않는다 ---------


def _install_blocking_graph(monkeypatch, release, started):
    """propagate 가 release 될 때까지 멈춰 있는 그래프. 시작 횟수를 ``started`` 에 쌓는다."""
    import api.runner as runner_module

    class _BlockingGraph:
        def __init__(self, *, progress_callback, **kwargs) -> None:
            self._cb = progress_callback

        def propagate(self, ticker: str, trade_date: str):
            started.append((ticker, trade_date))
            self._cb({"type": "run_start", "ticker": ticker, "trade_date": trade_date})
            release.wait(timeout=5)
            self._cb({"type": "done", "decision": "Buy"})
            return {"final_trade_decision": "Rating: Buy"}, "Buy"

        def save_reports(self, final_state, ticker):
            return "/tmp/reports/005930_20240105_120000/complete_report.md"

    monkeypatch.setattr(runner_module, "build_config", lambda req: {})
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.TradingAgentsGraph",
        _BlockingGraph,
        raising=True,
    )


def test_duplicate_post_returns_existing_run_without_starting_another(monkeypatch) -> None:
    import threading

    release = threading.Event()
    started: list[tuple[str, str]] = []
    _install_blocking_graph(monkeypatch, release, started)
    body = {"ticker": "005930", "trade_date": "2024-01-05"}

    with TestClient(create_app()) as client:
        first = client.post("/api/runs", json=body)
        assert first.status_code == 201, first.text
        assert first.json()["already_running"] is False
        run_id = first.json()["run_id"]
        _wait_for(lambda: store.get(run_id).status == "running")

        second = client.post("/api/runs", json=body)
        assert second.status_code == 200, second.text
        assert second.json() == {"run_id": run_id, "already_running": True}

        release.set()
        _wait_for(lambda: store.get(run_id).status == "done")

    assert started == [("005930", "2024-01-05")]
    assert len(store.list_recent(limit=10)) == 1


def test_duplicate_post_while_pending_returns_existing_run(monkeypatch) -> None:
    """아직 시작 전(pending)이어도 중복으로 본다 — 태스크가 막 만들어진 직후."""
    import threading

    release = threading.Event()
    _install_blocking_graph(monkeypatch, release, [])
    state = store.create("005930", "2024-01-05")
    assert state.status == "pending"

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/runs", json={"ticker": "005930", "trade_date": "2024-01-05"}
        )

    release.set()
    assert response.status_code == 200
    assert response.json() == {"run_id": state.run_id, "already_running": True}


def test_duplicate_ignores_analysis_settings(monkeypatch) -> None:
    """분석 설정(effort/analysts)이 달라도 같은 종목·기준일이면 중복이다.

    상태 로그(full_states_log_{기준일}.json)가 종목·기준일 단위 경로라서 설정이
    달라도 동시에 돌리면 서로 덮어쓴다.
    """
    import threading

    release = threading.Event()
    started: list[tuple[str, str]] = []
    _install_blocking_graph(monkeypatch, release, started)

    with TestClient(create_app()) as client:
        first = client.post(
            "/api/runs",
            json={"ticker": "005930", "trade_date": "2024-01-05", "effort": "low"},
        ).json()["run_id"]
        _wait_for(lambda: store.get(first).status == "running")

        second = client.post(
            "/api/runs",
            json={
                "ticker": "005930",
                "trade_date": "2024-01-05",
                "effort": "high",
                "analysts": ["news"],
            },
        )
        release.set()
        _wait_for(lambda: store.get(first).status == "done")

    assert second.status_code == 200
    assert second.json()["run_id"] == first
    assert len(started) == 1


@pytest.mark.parametrize(
    "other",
    [
        {"ticker": "000660", "trade_date": "2024-01-05"},  # 다른 종목
        {"ticker": "005930", "trade_date": "2024-01-04"},  # 다른 기준일
    ],
)
def test_different_ticker_or_date_starts_new_run(monkeypatch, other) -> None:
    import threading

    release = threading.Event()
    started: list[tuple[str, str]] = []
    _install_blocking_graph(monkeypatch, release, started)

    with TestClient(create_app()) as client:
        first = client.post(
            "/api/runs", json={"ticker": "005930", "trade_date": "2024-01-05"}
        ).json()["run_id"]
        _wait_for(lambda: store.get(first).status == "running")

        second = client.post("/api/runs", json=other)
        assert second.status_code == 201
        assert second.json()["already_running"] is False
        assert second.json()["run_id"] != first
        release.set()
        _wait_for(lambda: store.get(second.json()["run_id"]).status == "done")


@pytest.mark.parametrize("final_status", ["done", "error"])
def test_finished_run_does_not_block_new_run(final_status) -> None:
    """끝난(done/error) 분석은 중복이 아니다 — 같은 종목·기준일 재분석을 막지 않는다."""
    state = store.create("005930", "2024-01-05")
    state.status = final_status

    assert store.find_active("005930", "2024-01-05") is None


# --- #171: GET /api/runs 필터와 reports 제외 옵션 ---------------------------


def _seed_runs() -> dict[str, str]:
    """상태·종목·기준일이 다른 run 을 만든다. 생성 순서대로 a → e."""
    specs = {
        "a": ("005930", "2024-01-05", "done"),
        "b": ("005930", "2024-01-05", "error"),
        "c": ("005930", "2024-01-04", "running"),
        "d": ("000660", "2024-01-05", "running"),
        "e": ("000660", "2024-01-05", "pending"),
    }
    from datetime import UTC, datetime, timedelta

    base = datetime(2024, 1, 5, tzinfo=UTC)
    ids: dict[str, str] = {}
    for i, (key, (ticker, trade_date, status_)) in enumerate(specs.items()):
        state = store.create(ticker, trade_date)
        state.created_at = base + timedelta(seconds=i)  # 시계 해상도와 무관하게 순서 고정
        state.status = status_
        state.reports = {"market_report": f"본문-{key}"}
        ids[key] = state.run_id
    return ids


def _listed_ids(client: TestClient, query: str = "") -> set[str]:
    response = client.get(f"/api/runs{query}")
    assert response.status_code == 200, response.text
    return {item["run_id"] for item in response.json()}


def test_list_runs_without_filters_is_unchanged() -> None:
    ids = _seed_runs()
    client = TestClient(create_app())

    response = client.get("/api/runs")

    assert {item["run_id"] for item in response.json()} == set(ids.values())
    assert all(item["reports"] for item in response.json())  # 기본은 본문 포함


def test_list_runs_filters_by_ticker_date_and_status() -> None:
    ids = _seed_runs()
    client = TestClient(create_app())

    assert _listed_ids(client, "?ticker=005930") == {ids["a"], ids["b"], ids["c"]}
    assert _listed_ids(client, "?trade_date=2024-01-05") == {
        ids["a"], ids["b"], ids["d"], ids["e"],
    }
    assert _listed_ids(client, "?status=running") == {ids["c"], ids["d"]}
    # 조건은 AND 로 합쳐진다.
    assert _listed_ids(
        client, "?ticker=005930&trade_date=2024-01-05&status=done"
    ) == {ids["a"]}
    assert _listed_ids(client, "?ticker=999999") == set()


def test_list_runs_rejects_unknown_status() -> None:
    client = TestClient(create_app())

    assert client.get("/api/runs?status=bogus").status_code == 422


def test_list_runs_applies_limit_after_filtering() -> None:
    """최근 limit 개 밖의 오래된 분석도 조건으로 찾을 수 있어야 한다."""
    ids = _seed_runs()
    client = TestClient(create_app())

    # a 는 가장 오래됐다. limit=1 이어도 조건에 맞으면 a 가 나와야 한다.
    assert _listed_ids(client, "?ticker=005930&status=done&limit=1") == {ids["a"]}
    # 조건에 맞는 것이 여러 개면 최신순 limit 개.
    assert _listed_ids(client, "?ticker=005930&limit=2") == {ids["b"], ids["c"]}


def test_list_runs_can_exclude_reports() -> None:
    ids = _seed_runs()
    client = TestClient(create_app())

    items = client.get("/api/runs?include_reports=false").json()

    assert {item["run_id"] for item in items} == set(ids.values())
    assert all(item["reports"] == {} for item in items)
    # 본문 외 필드는 그대로다.
    assert {item["status"] for item in items} == {"done", "error", "running", "pending"}
    # 같은 run 의 단건 조회에는 본문이 남아 있다 (목록에서만 뺀다).
    assert client.get(f"/api/runs/{ids['a']}").json()["reports"] == {"market_report": "본문-a"}
