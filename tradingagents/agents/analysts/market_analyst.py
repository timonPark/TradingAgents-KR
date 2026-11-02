"""Market analyst — 사전조회 패턴 (Task 3a #33, ADR-0002).

Python 이 분석가 노드 진입 시점에 OHLCV, 11개 보조지표, 검증 스냅샷을 미리
조회해 프롬프트에 주입합니다. LLM 은 사전조회된 데이터만 보고 보고서를 작성
합니다 — `bind_tools` 호출 없음, 분석가당 Claude Code 호출 1회.
"""

from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.analysts.invoke import invoke_once
from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.tools import get_indicators, get_stock_data, get_verified_market_snapshot

# 모든 기술적 지표를 선계산 — Claude Code 가 지표를 선택할 수 없으니 Python 이
# 전량 계산해 프롬프트에 주입하고, LLM 은 보고서에서 어느 지표를 다룰지 선택.
_INDICATORS = (
    "close_50_sma", "close_200_sma", "close_10_ema",
    "macd", "macds", "macdh",
    "rsi",
    "boll", "boll_ub", "boll_lb", "atr",
    "vwma",
)

# OHLCV 선조회 창 — 트렌드/장기 지표 (200 SMA) 가 안정화되려면 ~250 거래일 필요.
# 넉넉히 1년.
_OHLCV_WINDOW_DAYS = 365


def _ohlcv_start_date(trade_date: str) -> str:
    end = datetime.strptime(trade_date, "%Y-%m-%d").date()
    return (end - timedelta(days=_OHLCV_WINDOW_DAYS)).strftime("%Y-%m-%d")


def _prefetch_market_data(ticker: str, trade_date: str) -> dict[str, str]:
    """`get_stock_data`, `get_indicators`, `get_verified_market_snapshot` 선조회.

    `@tool` 로 데코레이트된 함수를 `.invoke({...})` 로 직접 호출합니다 — Python
    에서 데이터를 받아 프롬프트에 주입하기 위함. 각 함수는 이미 포맷된 문자열을
    반환합니다 (CSV/Markdown 등).

    실패 시 각 섹션에 에러 메시지를 담아 반환 — 분석가 전체를 중단시키지 않고,
    LLM 이 "데이터 없음" 을 보고서에 명시할 수 있도록 합니다.
    """
    start_date = _ohlcv_start_date(trade_date)

    def _safe(fn, payload: dict) -> str:
        try:
            return fn.invoke(payload)
        except Exception as exc:  # noqa: BLE001 — 분석가 중단 방지
            return f"[prefetch failed: {type(exc).__name__}: {exc}]"

    ohlcv = _safe(get_stock_data, {
        "symbol": ticker,
        "start_date": start_date,
        "end_date": trade_date,
        "trade_date": trade_date,
    })
    indicators = _safe(get_indicators, {
        "symbol": ticker,
        "indicator": ",".join(_INDICATORS),
        "curr_date": trade_date,
        "look_back_days": 30,
        "trade_date": trade_date,
    })
    snapshot = _safe(get_verified_market_snapshot, {
        "symbol": ticker,
        "curr_date": trade_date,
        "look_back_days": 30,
        "trade_date": trade_date,
    })
    return {"ohlcv": ohlcv, "indicators": indicators, "snapshot": snapshot}


def _render_prefetched(data: dict[str, str]) -> str:
    """선조회된 데이터를 프롬프트에 주입할 Markdown 블록으로 포맷."""
    return (
        "## Pre-fetched Market Data\n\n"
        "### OHLCV (last ~1 year)\n"
        f"{data['ohlcv']}\n\n"
        "### Technical Indicators (all 12 pre-computed)\n"
        f"{data['indicators']}\n\n"
        "### Verified Market Snapshot (source of truth for exact values)\n"
        f"{data['snapshot']}\n"
    )


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        ticker = state["company_of_interest"]

        # Task 3a (#33): LLM 호출 전에 모든 데이터를 Python 이 선조회.
        prefetched = _prefetch_market_data(ticker, current_date)
        prefetched_block = _render_prefetched(prefetched)

        system_message = (
            """You are a trading assistant tasked with analyzing financial markets. The data has been **pre-fetched for you** — OHLCV for the last year, all 12 technical indicators pre-computed, and a verified market snapshot. You will **not** call tools; instead, pick the **most relevant indicators** (up to 8) from those pre-computed and discuss them. The indicators available in the pre-fetched block:

Moving Averages:
- close_50_sma: 50 SMA — medium-term trend. Identify trend direction and dynamic support/resistance. Lags price; combine with faster indicators.
- close_200_sma: 200 SMA — long-term trend benchmark. Golden/death cross setups. Reacts slowly.
- close_10_ema: 10 EMA — responsive short-term average. Quick momentum shifts. Noisy in choppy markets.

MACD Related:
- macd: Momentum via EMA differences. Crossovers and divergence as trend-change signals.
- macds: MACD Signal line — EMA smoothing of MACD. Use crossovers with MACD line.
- macdh: MACD Histogram — gap between MACD and signal. Visualizes momentum strength.

Momentum:
- rsi: 70/30 thresholds for overbought/oversold. In strong trends may remain extreme.

Volatility:
- boll: Bollinger Middle (20 SMA).
- boll_ub: Bollinger Upper Band (2σ above middle).
- boll_lb: Bollinger Lower Band (2σ below middle).
- atr: Average True Range — volatility measure for stop-loss / position sizing.

Volume-Based:
- vwma: Volume-Weighted Moving Average.

Select indicators that provide diverse, complementary information (avoid redundancy — do not pick both rsi and a similar momentum oscillator). Briefly explain why each is suitable for the current market context.

**Verified Market Snapshot is the source of truth** for any exact OHLCV, price-level, or indicator-value claim. If other data in the pre-fetched block seems to conflict with it, flag the discrepancy rather than inventing a reconciled number. Do not claim historical validation, support/resistance bounces, or exact percentage moves unless they are directly supported by the pre-fetched data with concrete dates and prices.

Write a very detailed and nuanced report of the trends you observe. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points, organized and easy to read."""
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " The data you need has been pre-fetched below; do not call tools."
                    " Report what the pre-fetched data supports; another agent decides the trade."
                    " Today's date is {current_date}; treat it as 'now' for all analysis. {instrument_context}\n"
                    "{system_message}\n\n"
                    "{prefetched}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(prefetched=prefetched_block)

        result, report = invoke_once(prompt, llm, state["messages"])

        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
