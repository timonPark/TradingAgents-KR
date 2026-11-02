"""The caller's book, as the decision agents see it.

Optional input to a run: what is held, at what average price, and how much cash
is free. Without it the agents cannot tell adding to a full position from
opening a new one. Three states are distinct and must stay so: a position, a
flat book, and no context at all, since treating "not provided" as "flat" would
invent a fact about the caller's account.

Broker-neutral by construction: quantities are generic units and the currency is
whatever label the caller passes, so nothing here implies a venue or an
execution path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError


def _canonical(ticker: str) -> str:
    """포트폴리오 비교용 캐노니컬 티커. KRX 6자리 코드는 단순 strip + upper 로
    충분합니다 (Task 4a #42). 대소문자 무시로 ``aapl`` ↔ ``AAPL`` 같은 레거시
    유연성은 유지하지만 상류의 broker-alias 매핑 (BTCUSDT → BTC-USD, 700.HK →
    0700.HK 등) 은 제거되었습니다."""
    return (ticker or "").strip().upper()


class Position(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    ticker: str = Field(description="Instrument symbol, e.g. AAPL")
    quantity: float = Field(description="Signed units held; negative is short")
    average_price: float | None = Field(default=None, description="Average entry price per unit")


class PortfolioContext(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    cash: float | None = Field(default=None, description="Free cash available")
    currency: str | None = Field(default=None, description="Currency label for cash and prices")
    positions: list[Position] = Field(default_factory=list)

    def positions_in(self, ticker: str) -> list[Position]:
        """The holdings of the instrument the run prices for ``ticker``.

        Task 4a (#42): KRX 종목코드 체계는 보통주/우선주/ETF/ETN 모두 6자리 숫자
        로 통일되어 있어 상류의 broker-spelling 정규화가 불필요. 단순 strip 비교.
        """
        symbol = _canonical(ticker)
        return [p for p in self.positions if _canonical(p.ticker) == symbol]

    def position_in(self, ticker: str) -> Position | None:
        held = self.positions_in(ticker)
        return held[0] if held else None

    def render(self, ticker: str) -> str:
        """The portfolio block for the decision agents, led by the analyzed instrument."""
        symbol = _canonical(ticker)
        held = self.positions_in(symbol)
        lines = []
        for position in held:
            price = f", average price {position.average_price:,.2f}" if position.average_price is not None else ""
            spelled = position.ticker.strip().upper()
            listed = f" (listed as {position.ticker})" if spelled != symbol else ""
            lines.append(f"- Current position in {symbol}: {position.quantity:,.4g} units{price}{listed}")
        if not held:
            lines.append(f"- No current position in {symbol}")
        if self.cash is not None:
            lines.append(f"- Cash available: {self.cash:,.2f}{' ' + self.currency if self.currency else ''}")
        others = [p for p in self.positions if all(p is not h for h in held)]
        if others:
            lines.append("- Other positions: " + ", ".join(f"{p.ticker.upper()} {p.quantity:,.4g}" for p in others))
        return "Portfolio at the analysis date:\n" + "\n".join(lines)

    def fingerprint(self) -> str:
        """Stable digest of the book, so a changed one cannot resume a stale run."""
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:12]


def load_portfolio(path: str | Path) -> PortfolioContext:
    """Read a portfolio JSON file, failing before the run rather than mid-graph."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return PortfolioContext.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"portfolio file {path} is not usable: {exc}") from exc
