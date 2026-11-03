"""KRX 종목명 → 종목코드 검색.

Task 14a (#106): CLI (``cli/prompts.py``) 와 웹 API (``api/routes/symbols.py``)
가 공유하는 KRX 상장 종목 검색 모듈. 사용자가 "삼성전자" 같은 종목명으로 검색
하면 매칭되는 6자리 종목코드를 돌려준다.

### 데이터 소스
``pykrx.stock.get_market_ticker_list`` + ``get_market_ticker_name``. KOSPI 와
KOSDAQ 전종목을 수집한다. 두 함수 모두 **keyless** — KRX 로그인 자격증명이
필요한 수급/시가총액 API 와 달리 공개 데이터이므로 ``.env`` 에 KRX_ID / KRX_PW
가 없어도 동작한다.

### 캐시
전종목 수집은 수초가 걸리므로 하루 단위 JSON 캐시를 사용한다.

- 경로: ``~/.tradingagents/cache/krx_tickers_YYYYMMDD.json``
- 캐시 키는 KRX 영업일 (``krx_calendar.current_trading_date()``)
- 환경변수 ``TRADINGAGENTS_CACHE_DIR`` 로 base 경로 override 가능
- 캐시 손상 (JSON 파싱 실패, 스키마 불일치) 시 재생성

### 공개 API
- ``search(query, limit, as_of)`` — 메인 검색 함수
- ``list_all(as_of)`` — 전종목 (디버그/디스플레이용)
- ``SymbolHit`` — 결과 데이터클래스
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Market = Literal["KOSPI", "KOSDAQ"]

_TICKER_PATTERN = re.compile(r"^\d{6}$")
_MARKETS: tuple[Market, ...] = ("KOSPI", "KOSDAQ")


@dataclass(frozen=True)
class SymbolHit:
    """단일 종목 검색 결과."""

    ticker: str
    name: str
    market: Market


def _cache_dir() -> Path:
    override = os.environ.get("TRADINGAGENTS_CACHE_DIR", "").strip()
    base = Path(override) if override else Path.home() / ".tradingagents" / "cache"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _cache_path(as_of: date) -> Path:
    return _cache_dir() / f"krx_tickers_{as_of.strftime('%Y%m%d')}.json"


def _load_cached(path: Path) -> list[SymbolHit] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("종목 캐시 손상, 재생성 (%s): %s", path, exc)
        return None
    try:
        return [
            SymbolHit(ticker=item["ticker"], name=item["name"], market=item["market"])
            for item in data
        ]
    except (TypeError, KeyError) as exc:
        logger.warning("종목 캐시 스키마 불일치, 재생성 (%s): %s", path, exc)
        return None


def _save_cache(path: Path, hits: list[SymbolHit]) -> None:
    payload = [{"ticker": h.ticker, "name": h.name, "market": h.market} for h in hits]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _fetch_from_pykrx(as_of: date) -> list[SymbolHit]:
    """pykrx 를 통해 KOSPI/KOSDAQ 전종목 수집."""
    from pykrx import stock

    date_str = as_of.strftime("%Y%m%d")
    hits: list[SymbolHit] = []
    for market in _MARKETS:
        tickers = stock.get_market_ticker_list(date=date_str, market=market)
        for raw_ticker in tickers:
            ticker = str(raw_ticker).zfill(6)
            name = stock.get_market_ticker_name(ticker)
            if not name:
                continue
            hits.append(SymbolHit(ticker=ticker, name=name, market=market))
    return hits


def _default_as_of() -> date:
    """가장 최근 KRX 영업일을 ``date`` 로."""
    from tradingagents.dataflows.krx_calendar import current_trading_date

    return date.fromisoformat(current_trading_date())


def _load_all(as_of: date | None = None) -> list[SymbolHit]:
    """캐시 우선, 미스 시 pykrx 호출 후 캐시 저장."""
    effective = as_of or _default_as_of()
    path = _cache_path(effective)
    cached = _load_cached(path)
    if cached is not None:
        return cached

    hits = _fetch_from_pykrx(effective)
    try:
        _save_cache(path, hits)
    except OSError as exc:
        # 캐시 저장 실패해도 검색은 계속.
        logger.warning("종목 캐시 저장 실패 (%s): %s", path, exc)
    return hits


def list_all(as_of: date | None = None) -> list[SymbolHit]:
    """KOSPI + KOSDAQ 전종목을 돌려준다 (정렬 없음)."""
    return _load_all(as_of)


def search(
    query: str,
    limit: int = 20,
    as_of: date | None = None,
) -> list[SymbolHit]:
    """종목명/종목코드로 KRX 상장 종목 검색.

    Args:
        query: 검색 문자열. 6자리 숫자면 정확 매칭, 그 외는 종목명 부분 매칭.
        limit: 반환 상한.
        as_of: 데이터 기준일 (기본: 최근 영업일).

    Returns:
        매칭된 ``SymbolHit`` 리스트. ``startswith`` 가 앞, ``contains`` 가 뒤.
    """
    q = query.strip()
    if not q or limit <= 0:
        return []

    hits = _load_all(as_of)

    if _TICKER_PATTERN.match(q):
        return [h for h in hits if h.ticker == q][:1]

    q_lower = q.lower()
    starts: list[SymbolHit] = []
    contains: list[SymbolHit] = []
    for hit in hits:
        name_lower = hit.name.lower()
        if name_lower.startswith(q_lower):
            starts.append(hit)
        elif q_lower in name_lower:
            contains.append(hit)

    starts.sort(key=lambda h: h.name)
    contains.sort(key=lambda h: h.name)
    return (starts + contains)[:limit]
