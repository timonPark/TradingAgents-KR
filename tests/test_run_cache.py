"""한 실행 안의 데이터 조회 재사용 (#210)."""

import threading
import time

import pytest

from tradingagents.agents.tools import get_news
from tradingagents.dataflows import router, run_cache
from tradingagents.dataflows.config import run_config, run_config_context


def _counting(result="뉴스"):
    calls = []

    def fetch():
        calls.append(1)
        return result
    return fetch, calls


@pytest.mark.unit
def test_outside_a_run_every_call_fetches():
    fetch, calls = _counting()

    run_cache.cached("k", fetch)
    run_cache.cached("k", fetch)

    assert len(calls) == 2


@pytest.mark.unit
def test_inside_a_run_the_first_result_is_reused():
    fetch, calls = _counting()

    with run_config({}):
        assert run_cache.cached("k", fetch) == run_cache.cached("k", fetch) == "뉴스"

    assert len(calls) == 1


@pytest.mark.unit
def test_different_keys_fetch_separately():
    fetch, calls = _counting()

    with run_config({}):
        run_cache.cached("a", fetch)
        run_cache.cached("b", fetch)

    assert len(calls) == 2


@pytest.mark.unit
def test_two_runs_do_not_share():
    fetch, calls = _counting()

    with run_config({}):
        run_cache.cached("k", fetch)
    with run_config({}):
        run_cache.cached("k", fetch)
    context_a, context_b = run_config_context({}), run_config_context({})
    context_a.run(run_cache.cached, "k", fetch)
    context_b.run(run_cache.cached, "k", fetch)

    assert len(calls) == 4


@pytest.mark.unit
def test_a_failed_result_is_not_kept():
    fetch, calls = _counting("DATA_UNAVAILABLE: 장애")

    with run_config({}):
        for _ in range(2):
            run_cache.cached("k", fetch, keep=lambda r: not r.startswith("DATA_UNAVAILABLE"))

    assert len(calls) == 2


@pytest.mark.unit
def test_an_exception_is_not_kept():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("일시 장애")
        return "뉴스"

    with run_config({}):
        with pytest.raises(RuntimeError):
            run_cache.cached("k", flaky)
        assert run_cache.cached("k", flaky) == "뉴스"

    assert len(calls) == 2


@pytest.mark.unit
def test_parallel_callers_wait_for_one_fetch():
    """분석가는 병렬로 돈다. 동시에 같은 키를 조회해도 vendor 는 한 번만 부른다."""
    calls = []

    def slow():
        calls.append(1)
        time.sleep(0.05)
        return "뉴스"

    results = []
    context = run_config_context({})

    def worker():
        results.append(run_cache.cached("k", slow))

    # LangGraph 처럼 실행 context 의 복사본을 스레드마다 쓴다.
    threads = [threading.Thread(target=context.copy().run, args=(worker,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1 and results == ["뉴스"] * 4


@pytest.mark.unit
def test_get_news_tool_reuses_the_same_window_within_a_run(monkeypatch):
    """뉴스 분석가(trade_date 주입)와 감성 분석가(.func 직접 호출)는 같은 기간을 조회한다."""
    asked = []
    monkeypatch.setattr("tradingagents.agents.tools.route_to_vendor",
                        lambda method, *args: asked.append(args) or "## 뉴스")

    with run_config({}):
        news = get_news.invoke({"ticker": "005930", "start_date": "2026-11-19",
                                "end_date": "2026-11-26", "trade_date": "2026-11-26"})
        sentiment = get_news.func("005930", "2026-11-19", "2026-11-26")
        other = get_news.func("000660", "2026-11-19", "2026-11-26")

    assert news == sentiment == "## 뉴스" and other == "## 뉴스"
    assert asked == [("005930", "2026-11-19", "2026-11-26"), ("000660", "2026-11-19", "2026-11-26")]


@pytest.mark.unit
def test_get_news_does_not_keep_data_unavailable(monkeypatch):
    results = iter([router.vendor_unavailable("get_news", RuntimeError("502")), "## 뉴스"])
    monkeypatch.setattr("tradingagents.agents.tools.route_to_vendor", lambda *a: next(results))

    with run_config({}):
        first = get_news.func("005930", "2026-11-19", "2026-11-26")
        second = get_news.func("005930", "2026-11-19", "2026-11-26")

    assert first.startswith("DATA_UNAVAILABLE") and second == "## 뉴스"
