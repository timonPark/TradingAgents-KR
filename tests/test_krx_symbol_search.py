"""Task 14a (#106): KRX 종목 검색 모듈 유닛 테스트.

실제 pykrx 네트워크 호출을 피하기 위해 ``_fetch_from_pykrx`` 를 몽키패치한다.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from tradingagents.dataflows import krx_symbol_search as kss
from tradingagents.dataflows.krx_symbol_search import SymbolHit

FIXTURE: list[SymbolHit] = [
    SymbolHit(ticker="005930", name="삼성전자", market="KOSPI"),
    SymbolHit(ticker="006400", name="삼성SDI", market="KOSPI"),
    SymbolHit(ticker="028260", name="삼성물산", market="KOSPI"),
    SymbolHit(ticker="032830", name="삼성생명", market="KOSPI"),
    SymbolHit(ticker="000660", name="SK하이닉스", market="KOSPI"),
    SymbolHit(ticker="035720", name="카카오", market="KOSPI"),
    SymbolHit(ticker="035420", name="NAVER", market="KOSPI"),
    SymbolHit(ticker="069500", name="KODEX 200", market="KOSPI"),
    SymbolHit(ticker="251340", name="KODEX 코스닥150선물인버스", market="KOSPI"),
    SymbolHit(ticker="247540", name="에코프로비엠", market="KOSDAQ"),
    SymbolHit(ticker="086520", name="에코프로", market="KOSDAQ"),
]


@pytest.fixture
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """TRADINGAGENTS_CACHE_DIR 를 tmp_path 로 가둬 테스트 간 격리."""
    monkeypatch.setenv("TRADINGAGENTS_CACHE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def fixed_as_of() -> date:
    return date(2026, 11, 3)


@pytest.fixture
def patched_fetch(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """pykrx 호출을 FIXTURE 로 대체. 호출 횟수를 리스트로 반환."""
    call_count = [0]

    def fake_fetch(_as_of: date) -> list[SymbolHit]:
        call_count[0] += 1
        return FIXTURE

    monkeypatch.setattr(kss, "_fetch_from_pykrx", fake_fetch)
    return call_count


# ---------------------------------------------------------------------------
# search(): 기본 매칭
# ---------------------------------------------------------------------------


def test_search_by_ticker_returns_single_exact_match(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    hits = kss.search("005930", as_of=fixed_as_of)
    assert len(hits) == 1
    assert hits[0].ticker == "005930"
    assert hits[0].name == "삼성전자"


def test_search_by_ticker_unknown_returns_empty(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    assert kss.search("999999", as_of=fixed_as_of) == []


def test_search_by_korean_name_partial_matches_multiple(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    hits = kss.search("삼성", as_of=fixed_as_of)
    tickers = [h.ticker for h in hits]
    # '삼성' 으로 시작하는 4개 (startswith 그룹) 가 전부 포함되어야 함.
    assert set(tickers) == {"005930", "006400", "028260", "032830"}


def test_search_by_english_name_case_insensitive(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    hits = kss.search("kodex", as_of=fixed_as_of)
    assert {h.ticker for h in hits} == {"069500", "251340"}


def test_search_by_english_startswith(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    hits = kss.search("NAV", as_of=fixed_as_of)
    assert len(hits) == 1
    assert hits[0].ticker == "035420"


def test_search_contains_group_follows_starts_group(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    hits = kss.search("에코프로", as_of=fixed_as_of)
    # 둘 다 "에코프로" 로 시작 → 사전순 정렬
    assert [h.ticker for h in hits] == ["086520", "247540"]


def test_search_empty_query_returns_empty(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    assert kss.search("", as_of=fixed_as_of) == []
    assert kss.search("   ", as_of=fixed_as_of) == []


def test_search_zero_limit_returns_empty(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    assert kss.search("삼성", limit=0, as_of=fixed_as_of) == []


def test_search_respects_limit(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    hits = kss.search("삼성", limit=2, as_of=fixed_as_of)
    assert len(hits) == 2


def test_search_no_match_returns_empty(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    assert kss.search("존재하지않는종목명", as_of=fixed_as_of) == []


# ---------------------------------------------------------------------------
# 캐시 동작
# ---------------------------------------------------------------------------


def test_first_search_hits_pykrx_and_writes_cache(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    kss.search("삼성", as_of=fixed_as_of)
    assert patched_fetch[0] == 1
    cache_file = isolated_cache / "krx_tickers_20261103.json"
    assert cache_file.exists()
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    assert {d["ticker"] for d in data} >= {"005930", "006400"}


def test_second_search_hits_cache_not_pykrx(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    kss.search("삼성", as_of=fixed_as_of)
    kss.search("카카오", as_of=fixed_as_of)
    assert patched_fetch[0] == 1  # 두 번째 호출은 캐시 히트


def test_corrupt_cache_triggers_regeneration(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    cache_file = isolated_cache / "krx_tickers_20261103.json"
    cache_file.write_text("{{broken json", encoding="utf-8")

    hits = kss.search("삼성", as_of=fixed_as_of)
    assert len(hits) >= 1
    assert patched_fetch[0] == 1  # 손상 캐시 재생성


def test_cache_schema_mismatch_triggers_regeneration(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    cache_file = isolated_cache / "krx_tickers_20261103.json"
    cache_file.write_text(
        json.dumps([{"wrong_key": "005930"}], ensure_ascii=False), encoding="utf-8"
    )

    hits = kss.search("삼성", as_of=fixed_as_of)
    assert len(hits) >= 1
    assert patched_fetch[0] == 1


def test_cache_write_failure_does_not_break_search(
    isolated_cache: Path,
    fixed_as_of: date,
    patched_fetch: list[int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raising_save(_path: Path, _hits: list[SymbolHit]) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(kss, "_save_cache", raising_save)

    hits = kss.search("삼성", as_of=fixed_as_of)
    assert len(hits) >= 1  # 저장 실패해도 결과는 돌려줘야 함


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------


def test_list_all_returns_full_fixture(
    isolated_cache: Path, fixed_as_of: date, patched_fetch: list[int]
) -> None:
    hits = kss.list_all(as_of=fixed_as_of)
    assert len(hits) == len(FIXTURE)
    assert {h.ticker for h in hits} == {h.ticker for h in FIXTURE}


# ---------------------------------------------------------------------------
# default as_of (krx_calendar 통합)
# ---------------------------------------------------------------------------


def test_default_as_of_uses_current_trading_date(
    isolated_cache: Path,
    patched_fetch: list[int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tradingagents.dataflows.krx_calendar as cal

    monkeypatch.setattr(cal, "current_trading_date", lambda: "2026-10-30")
    hits = kss.search("삼성")
    assert len(hits) >= 1
    assert (isolated_cache / "krx_tickers_20261030.json").exists()
