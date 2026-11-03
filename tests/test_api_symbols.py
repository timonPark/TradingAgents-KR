"""`/api/symbols/search` 테스트 (Task 14b #107).

14a (#106) 의 ``krx_symbol_search`` 모듈은 모킹한다 — 이 테스트는 **라우터가
입력을 모듈로 올바로 넘기고 출력을 Pydantic 스키마로 직렬화하는지** 만 검증.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from api.main import create_app  # noqa: E402
from tradingagents.dataflows.krx_symbol_search import SymbolHit  # noqa: E402

FIXTURE = [
    SymbolHit(ticker="005930", name="삼성전자", market="KOSPI"),
    SymbolHit(ticker="035720", name="카카오", market="KOSPI"),
    SymbolHit(ticker="247540", name="에코프로비엠", market="KOSDAQ"),
]


def test_search_returns_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.routes import symbols as symbols_route

    monkeypatch.setattr(symbols_route.kss, "search", lambda q, limit: FIXTURE)
    client = TestClient(create_app())

    response = client.get("/api/symbols/search?q=카카오&limit=5")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "hits": [
            {"ticker": "005930", "name": "삼성전자", "market": "KOSPI"},
            {"ticker": "035720", "name": "카카오", "market": "KOSPI"},
            {"ticker": "247540", "name": "에코프로비엠", "market": "KOSDAQ"},
        ]
    }


def test_search_forwards_query_and_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_search(q: str, limit: int) -> list[SymbolHit]:
        captured["q"] = q
        captured["limit"] = limit
        return []

    from api.routes import symbols as symbols_route

    monkeypatch.setattr(symbols_route.kss, "search", fake_search)
    client = TestClient(create_app())

    client.get("/api/symbols/search?q=삼성&limit=7")
    assert captured == {"q": "삼성", "limit": 7}


def test_search_empty_query_returns_empty_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.routes import symbols as symbols_route

    monkeypatch.setattr(symbols_route.kss, "search", lambda q, limit: [])
    client = TestClient(create_app())

    response = client.get("/api/symbols/search?q=")
    assert response.status_code == 200
    assert response.json() == {"hits": []}


def test_search_rejects_out_of_range_limit() -> None:
    client = TestClient(create_app())
    assert client.get("/api/symbols/search?q=x&limit=51").status_code == 422
    assert client.get("/api/symbols/search?q=x&limit=-1").status_code == 422
