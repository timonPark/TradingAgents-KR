"""API wire schemas (Pydantic).

내부 도메인 타입 (예: ``tradingagents.dataflows.krx_symbol_search.SymbolHit``
는 frozen dataclass) 과 분리해 HTTP 직렬화가 내부 타입을 끌지 않도록 한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SymbolHit(BaseModel):
    """종목 검색 결과 단일 항목."""

    ticker: str = Field(description="KRX 종목코드 (대문자 영숫자 6자)")
    name: str = Field(description="종목명")
    market: str = Field(description="시장 구분 (KOSPI/KOSDAQ)")


class SymbolSearchResponse(BaseModel):
    """``GET /api/symbols/search`` 응답."""

    hits: list[SymbolHit] = Field(default_factory=list)
