"""종목 검색 엔드포인트.

14a (#106) 의 ``krx_symbol_search.search()`` 를 얇게 감싸 JSON 응답으로 변환.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.models import SymbolHit, SymbolSearchResponse
from tradingagents.dataflows import krx_symbol_search as kss

router = APIRouter()


@router.get("/search", response_model=SymbolSearchResponse)
def search_symbols(
    q: str = Query("", description="종목명 (한글/영문) 또는 6자리 종목코드"),
    limit: int = Query(20, ge=0, le=50),
) -> SymbolSearchResponse:
    """`q` 로 KRX 종목 검색. 6자리 숫자는 정확 매칭, 그 외는 부분 매칭."""
    hits = kss.search(q, limit=limit)
    return SymbolSearchResponse(
        hits=[
            SymbolHit(ticker=h.ticker, name=h.name, market=h.market) for h in hits
        ]
    )
