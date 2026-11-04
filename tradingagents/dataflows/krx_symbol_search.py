"""KRX 종목명 → 종목코드 검색.

Task 14a (#106): CLI (``cli/prompts.py``) 와 웹 API (``api/routes/symbols.py``)
가 공유하는 KRX 상장 종목 검색 모듈. 사용자가 "삼성전자" 같은 종목명으로 검색
하면 매칭되는 6자리 종목코드를 돌려준다.

### 데이터 소스
``FinanceDataReader`` (``fdr.StockListing('KRX')``). KOSPI + KOSDAQ 전종목
(2876건) 을 ``Code`` / ``Name`` / ``Market`` 컬럼으로 반환한다. keyless 공개
데이터. **#124 핫픽스**: 원래 pykrx 의 ``get_market_ticker_list`` /
``get_market_ticker_name`` 을 썼지만 KRX 사이트 변경으로 두 함수가 빈 응답
또는 ``Empty DataFrame`` 을 반환해 교체.

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


def _fetch_tickers(as_of: date) -> list[SymbolHit]:
    """FinanceDataReader 로 KOSPI/KOSDAQ 전종목 수집.

    ``as_of`` 는 API 호환성 유지용 (FDR 은 당일 리스팅만 지원). 원래 pykrx
    경로가 날짜별 종목을 가져왔던 자리를 그대로 유지.
    """
    import FinanceDataReader as fdr

    listing = fdr.StockListing("KRX")
    if listing is None or listing.empty:
        return []

    # Market 컬럼이 없는 FDR 버전 방어 — 비정상 응답은 빈 리스트로 간주.
    if "Market" not in listing.columns or "Code" not in listing.columns:
        logger.warning("FDR StockListing 응답에 Market/Code 컬럼 없음, 빈 결과 반환")
        return []

    hits: list[SymbolHit] = []
    valid_markets = set(_MARKETS)
    for _, row in listing.iterrows():
        market = row["Market"]
        if market not in valid_markets:
            continue
        code = str(row["Code"]).zfill(6)
        name = row.get("Name")
        if not isinstance(name, str) or not name.strip():
            continue
        hits.append(SymbolHit(ticker=code, name=name.strip(), market=market))
    return hits


def _default_as_of() -> date:
    """가장 최근 KRX 영업일을 ``date`` 로. 캘린더 실패 시 KST 오늘로 폴백.

    #136: ``exchange_calendars`` 의 KRX 캘린더 생성이 pandas 3.x 와 호환 문제
    (KoreanHoliday rule 의 Series set-item 이 길이 불일치 ValueError 를 터뜨림)
    로 터질 수 있다. 종목 **검색** 용도는 영업일 정확도가 필요 없으므로
    (FDR 은 요청 날짜 상관없이 당일 리스팅을 돌려줌) 캘린더 생성이 터지면
    KST 기준 오늘로 폴백해서 서비스가 죽지 않게 한다.
    """
    try:
        from tradingagents.dataflows.krx_calendar import current_trading_date

        return date.fromisoformat(current_trading_date())
    except Exception as exc:  # noqa: BLE001 — 외부 패키지 호환성 깨짐 방어
        from tradingagents.dataflows.date_window import get_current_date

        logger.warning(
            "krx_calendar 사용 불가, KST 오늘로 폴백 (%s): %s",
            type(exc).__name__, exc,
        )
        return date.fromisoformat(get_current_date())


def _load_all(as_of: date | None = None) -> list[SymbolHit]:
    """캐시 우선, 미스 시 FDR 호출 후 캐시 저장.

    #124: 빈 결과는 **캐시에 저장하지 않는다**. 과거 pykrx 가 빈 리스트를
    반환하던 상황에서 ``[]`` 가 하루 동안 캐시돼 다음 fetch 를 막던 문제를
    차단.
    """
    effective = as_of or _default_as_of()
    path = _cache_path(effective)
    cached = _load_cached(path)
    if cached:
        return cached

    hits = _fetch_tickers(effective)
    if not hits:
        logger.warning(
            "종목 리스트 fetch 결과 0건 — 캐시에 저장하지 않음 (다음 호출에서 재시도)"
        )
        return hits

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
