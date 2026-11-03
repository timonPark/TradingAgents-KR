"""News analyst — 사전조회 패턴 (Task 3c #35, ADR-0002).

Python 이 분석가 노드 진입 시점에 종목 뉴스, 글로벌 뉴스, 거시 지표, 예측 시장
데이터를 미리 조회해 프롬프트에 주입합니다. LLM 은 사전조회된 데이터만 보고
보고서를 작성 — `bind_tools` 호출 없음, 분석가당 Claude Code 호출 1회.
"""

from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.analysts.invoke import invoke_once
from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.tools import (
    get_global_news,
    get_macro_indicators,
    get_news,
    get_prediction_markets,
)

# 뉴스 선조회 창 — 최근 1주일.
_NEWS_WINDOW_DAYS = 7

# 사전조회할 거시 지표. 한국 거시 환경에 맞춘 핵심 지표를 전부 선조회해 LLM 이
# 보고서에서 어느 것을 다룰지 선택. Task 7d (#65): FRED alias → ECOS alias.
_MACRO_INDICATORS = (
    "base_rate",        # 한국은행 기준금리
    "cpi",              # 소비자물가지수
    "unemployment_rate",  # 실업률
    "treasury_10y",     # 국고채 10년 금리
    "usd_krw",          # 원/달러 환율
    "consumer_sentiment",  # 소비자심리지수 (CSI)
)

# 사전조회할 예측 시장 토픽. LLM 이 자유 입력 topic 을 선택할 수 없으니 공통
# 매크로 이벤트들을 선조회해 "live market-implied probabilities" 섹션을 채움.
_PREDICTION_TOPICS = (
    "Fed rate cut",
    "recession 2026",
)


def _news_window(trade_date: str) -> tuple[str, str]:
    """최근 1주일 뉴스 창 — (start_date, end_date) 반환."""
    end = datetime.strptime(trade_date, "%Y-%m-%d").date()
    start = end - timedelta(days=_NEWS_WINDOW_DAYS)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _prefetch_news_data(ticker: str, trade_date: str) -> dict[str, str]:
    """뉴스/거시/예측시장 데이터를 전부 선조회.

    각 함수 실패 시 섹션에 에러 메시지만 담아 반환 (분석가 중단 방지 — 다른
    분석가들과 동일 fail-safe 패턴).
    """
    start_date, end_date = _news_window(trade_date)

    def _safe(fn, payload: dict) -> str:
        try:
            return fn.invoke(payload)
        except Exception as exc:  # noqa: BLE001 — 분석가 중단 방지
            return f"[prefetch failed: {type(exc).__name__}: {exc}]"

    ticker_news = _safe(get_news, {
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "trade_date": trade_date,
    })
    global_news = _safe(get_global_news, {
        "curr_date": trade_date,
        "trade_date": trade_date,
    })

    # 거시 지표 — 각 지표를 별도 호출해 결과를 모음.
    macro_sections = []
    for indicator in _MACRO_INDICATORS:
        section = _safe(get_macro_indicators, {
            "indicator": indicator,
            "curr_date": trade_date,
            "trade_date": trade_date,
        })
        macro_sections.append(f"**{indicator}**\n{section}")
    macro = "\n\n".join(macro_sections)

    # 예측 시장 — 주요 매크로 이벤트들을 모아서 호출.
    prediction_sections = []
    for topic in _PREDICTION_TOPICS:
        section = _safe(get_prediction_markets, {
            "topic": topic,
            "trade_date": trade_date,
        })
        prediction_sections.append(f"**{topic}**\n{section}")
    prediction_markets = "\n\n".join(prediction_sections)

    return {
        "ticker_news": ticker_news,
        "global_news": global_news,
        "macro": macro,
        "prediction_markets": prediction_markets,
    }


def _render_prefetched(data: dict[str, str], asset_label: str) -> str:
    """선조회된 데이터를 프롬프트에 주입할 Markdown 블록으로 포맷."""
    return (
        "## Pre-fetched News Data\n\n"
        f"### Ticker-specific News ({asset_label}, last week)\n"
        f"{data['ticker_news']}\n\n"
        "### Global / Macroeconomic News\n"
        f"{data['global_news']}\n\n"
        "### Korean Macroeconomic Indicators (한국은행 ECOS, by series)\n"
        f"{data['macro']}\n\n"
        "### Prediction Markets (live market-implied probabilities)\n"
        f"{data['prediction_markets']}\n"
    )


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "stock")
        asset_label = "company" if asset_type == "stock" else "asset"
        instrument_context = get_instrument_context_from_state(state)
        ticker = state["company_of_interest"]

        # Task 3c (#35): LLM 호출 전에 Python 이 뉴스/거시/예측시장 데이터를 선조회.
        prefetched = _prefetch_news_data(ticker, current_date)
        prefetched_block = _render_prefetched(prefetched, asset_label)

        system_message = (
            f"You are a news researcher tasked with analyzing recent news and trends over the past "
            f"week. The data has been **pre-fetched for you** — recent news about the {asset_label} "
            "under analysis, broader global / macroeconomic news, core Korean macro indicators from "
            "한국은행 ECOS (기준금리, 소비자물가지수, 실업률, 국고채 10년, 원/달러 환율, 소비자심리지수), "
            "and live prediction-market probabilities for common macro events (Fed rate cuts, 2026 "
            "recession). You will **not** call tools; write a comprehensive report of the current "
            "state of the world relevant for trading and macroeconomics grounded in the pre-fetched "
            "data below. Provide specific, actionable insights with supporting evidence to help "
            "traders make informed decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
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
            "news_report": report,
        }

    return news_analyst_node
