"""한 실행(run) 안에서 같은 데이터 조회를 한 번만 하기 (#210).

뉴스 분석가와 감성 분석가는 같은 종목·같은 기간의 종목뉴스를 각자 조회한다.
종목뉴스는 기간 전체를 읽느라 네이버 API 를 최대 100쪽 부르므로(#195), 실행 범위
(``config.run_config`` / ``run_config_context``) 안에서 첫 결과를 재사용한다.

- 실행이 다르면 공유하지 않는다. 실행 범위 밖에서는 캐시 없이 매번 조회한다.
- 분석가는 병렬로 돌므로, 같은 키를 동시에 조회하면 나중 호출이 먼저 호출의 결과를 기다린다.
- ``keep`` 이 거짓인 결과(조회 실패)와 예외는 저장하지 않아 다음 호출이 다시 조회한다.
"""

import threading
from collections.abc import Callable, Hashable
from contextlib import contextmanager
from contextvars import ContextVar

_scope: ContextVar[dict | None] = ContextVar("tradingagents_run_cache", default=None)
_slots_lock = threading.Lock()


def new_scope() -> None:
    """현재 context 에 빈 캐시를 연다. ``Context.run`` 안에서 부르는 용도."""
    _scope.set({})


@contextmanager
def scope():
    """블록 동안 빈 캐시를 연다."""
    token = _scope.set({})
    try:
        yield
    finally:
        _scope.reset(token)


def cached(key: Hashable, fetch: Callable[[], str], keep: Callable[[str], bool] = lambda _: True) -> str:
    """실행 범위 안에서 ``key`` 의 첫 결과를 재사용한다. 범위 밖이면 ``fetch()`` 그대로."""
    store = _scope.get()
    if store is None:
        return fetch()
    with _slots_lock:
        slot = store.setdefault(key, {"lock": threading.Lock()})
    with slot["lock"]:
        if "value" in slot:
            return slot["value"]
        value = fetch()
        if keep(value):
            slot["value"] = value
        return value
