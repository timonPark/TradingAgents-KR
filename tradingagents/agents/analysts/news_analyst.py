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

    return {
        "ticker_news": ticker_news,
        "global_news": global_news,
        "macro": macro,
    }


def _render_prefetched(data: dict[str, str], asset_label: str) -> str:
    """선조회된 데이터를 프롬프트에 주입할 Markdown 블록으로 포맷."""
    return (
        "## 사전 조회된 뉴스·거시 데이터\n\n"
        f"### 종목 뉴스 ({asset_label}, 최근 1주일)\n"
        f"{data['ticker_news']}\n\n"
        "### 글로벌 / 거시경제 뉴스\n"
        f"{data['global_news']}\n\n"
        "### 한국 거시경제 지표 (한국은행 ECOS)\n"
        f"{data['macro']}\n"
    )


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "stock")
        asset_label = "기업" if asset_type == "stock" else "자산"
        instrument_context = get_instrument_context_from_state(state)
        ticker = state["company_of_interest"]

        # Task 3c (#35): LLM 호출 전에 Python 이 뉴스/거시/예측시장 데이터를 선조회.
        prefetched = _prefetch_news_data(ticker, current_date)
        prefetched_block = _render_prefetched(prefetched, asset_label)

        system_message = (
            f"당신은 지난 1주일간의 최근 뉴스와 트렌드를 분석하는 뉴스 분석가입니다. "
            f"데이터는 이미 **사전 조회되어 프롬프트에 주입**되어 있습니다 — 분석 대상 {asset_label} "
            "의 최근 뉴스, 글로벌 / 거시경제 뉴스, 그리고 한국은행 ECOS 의 핵심 한국 거시 지표 "
            "(기준금리, 소비자물가지수, 실업률, 국고채 10년, 원/달러 환율, 소비자심리지수). "
            "**툴을 호출하지 말고** 사전 조회된 데이터를 기반으로 트레이딩과 거시경제에 관련된 "
            "현재 세계 상황의 종합적인 보고서를 작성하세요. 트레이더가 정보에 입각한 결정을 "
            "내릴 수 있도록 근거를 뒷받침해 구체적이고 실행 가능한 인사이트를 제시하세요."
            "\n\n**KRX 특유 리스크 뉴스 (발견 시 즉시 심각 리스크로 분류):**\n"
            "- **관리종목 / 환기종목 지정 또는 사유 발생**: 재무 요건 미달·감사의견 거절 등으로 거래소가 투자자 보호 조치를 발동. 상장폐지 전 단계 신호로 당일/익일 급락이 흔함.\n"
            "- **상장폐지 사유 발생 공시**: 가장 심각한 리스크 — 매도 창구가 좁아지므로 보유 포지션 즉시 재검토.\n"
            "- **대주주 매도 / 블록딜 / 보호예수 해제 공시 (오버행)**: 공시된 수량만큼 시장에 잠재 매도 압력. 가격 상단을 수개월 이상 억제할 수 있음.\n"
            "- **공매도 금지 재개 공시**: 공매도 금지가 해제되는 종목은 통상 수일간 하방 압력 급증. 당일 종가 대비 10% 전후 하락 전례 있음.\n"
            "- **유상증자 / 전환사채(CB) 발행 공시**: 신주 희석 효과로 EPS/주당 가치 하락. 발행가 할인율과 전환가 조정 조건을 확인하세요."
            + """ 보고서 말미에 핵심 포인트를 정리한 Markdown 표를 반드시 첨부해 가독성을 높이세요."""
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "당신은 다른 분석가들과 협업하는 AI 어시스턴트입니다."
                    " 필요한 데이터는 이미 아래에 사전 조회되어 있으므로 툴을 호출하지 마세요."
                    " 사전 조회된 데이터가 뒷받침하는 내용만 보고하고 — 거래 결정은 다른 에이전트의 몫입니다."
                    " 오늘 날짜는 {current_date} 입니다; 모든 분석에서 이 날짜를 '현재' 로 간주하세요. {instrument_context}\n"
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
