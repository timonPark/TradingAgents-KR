"""Market analyst — 사전조회 패턴 (Task 3a #33, ADR-0002).

Python 이 분석가 노드 진입 시점에 OHLCV, 11개 보조지표, 검증 스냅샷을 미리
조회해 프롬프트에 주입합니다. LLM 은 사전조회된 데이터만 보고 보고서를 작성
합니다 — `bind_tools` 호출 없음, 분석가당 Claude Code 호출 1회.
"""

from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.analysts.invoke import invoke_once
from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.tools import (
    get_indicators,
    get_investor_net_purchases,
    get_stock_data,
    get_verified_market_snapshot,
)

# 모든 기술적 지표를 선계산 — Claude Code 가 지표를 선택할 수 없으니 Python 이
# 전량 계산해 프롬프트에 주입하고, LLM 은 보고서에서 어느 지표를 다룰지 선택.
_INDICATORS = (
    "close_50_sma", "close_200_sma", "close_10_ema",
    "macd", "macds", "macdh",
    "rsi",
    "boll", "boll_ub", "boll_lb", "atr",
)

# OHLCV 선조회 창 — 트렌드/장기 지표 (200 SMA) 가 안정화되려면 ~250 거래일 필요.
# 넉넉히 1년.
_OHLCV_WINDOW_DAYS = 365


def _ohlcv_start_date(trade_date: str) -> str:
    end = datetime.strptime(trade_date, "%Y-%m-%d").date()
    return (end - timedelta(days=_OHLCV_WINDOW_DAYS)).strftime("%Y-%m-%d")


def _prefetch_market_data(ticker: str, trade_date: str) -> dict[str, str]:
    """`get_stock_data`, `get_indicators`, `get_verified_market_snapshot`,
    `get_investor_net_purchases` 선조회.

    `@tool` 로 데코레이트된 함수를 `.invoke({...})` 로 직접 호출합니다 — Python
    에서 데이터를 받아 프롬프트에 주입하기 위함. 각 함수는 이미 포맷된 문자열을
    반환합니다 (CSV/Markdown 등).

    실패 시 각 섹션에 에러 메시지를 담아 반환 — 분석가 전체를 중단시키지 않고,
    LLM 이 "데이터 없음" 을 보고서에 명시할 수 있도록 합니다.

    Task 6c (#54): KRX 전용 투자자별 수급 (`get_investor_net_purchases`) 선조회
    추가. 외국인/기관/개인의 최근 5거래일 순매수는 KRX 가격 변동의 선행 지표.
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
    investor_flow = _safe(get_investor_net_purchases, {
        "ticker": ticker,
        "trade_date": trade_date,
        "look_back_days": 5,
    })
    return {
        "ohlcv": ohlcv,
        "indicators": indicators,
        "snapshot": snapshot,
        "investor_flow": investor_flow,
    }


def _render_prefetched(data: dict[str, str]) -> str:
    """선조회된 데이터를 프롬프트에 주입할 Markdown 블록으로 포맷."""
    return (
        "## 사전 조회된 시장 데이터\n\n"
        "### OHLCV (최근 약 1년)\n"
        f"{data['ohlcv']}\n\n"
        "### 기술적 지표 (12개 전체 사전 계산)\n"
        f"{data['indicators']}\n\n"
        "### 검증 시장 스냅샷 (정확한 값의 원천)\n"
        f"{data['snapshot']}\n\n"
        "### 투자자별 수급 (최근 5거래일 순매수 — KRX 전용 선행 지표)\n"
        f"{data['investor_flow']}\n"
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
            """당신은 금융 시장을 분석하는 시장 분석가입니다. 데이터는 이미 **사전 조회되어 프롬프트에 주입**되어 있습니다 — 최근 1년 OHLCV, 12개 기술적 지표 전체 사전 계산, 검증 시장 스냅샷. **툴을 호출하지 말고** 사전 계산된 지표 중 **가장 관련성 높은 지표 (최대 8개)** 를 선택해 논의하세요. 사용 가능한 지표:

이동평균 (Moving Averages):
- close_50_sma: 50 SMA — 중기 추세. 방향성과 동적 지지/저항 식별. 가격을 뒤따르므로 더 빠른 지표와 결합.
- close_200_sma: 200 SMA — 장기 추세 벤치마크. 골든/데드 크로스 세팅. 반응 느림.
- close_10_ema: 10 EMA — 단기 반응성 높은 평균. 빠른 모멘텀 변화 포착. 횡보장에서 노이즈 많음.

MACD 계열:
- macd: EMA 차이로 모멘텀 측정. 교차 / 다이버전스 → 추세 전환 신호.
- macds: MACD 신호선 — MACD 의 EMA 평활화. MACD 라인과의 교차로 활용.
- macdh: MACD 히스토그램 — MACD 와 신호선의 간격. 모멘텀 강도 시각화.

모멘텀:
- rsi: 70/30 임계값으로 과매수/과매도. 강한 추세에서는 극값 유지 가능.

변동성:
- boll: Bollinger 중심선 (20 SMA).
- boll_ub: Bollinger 상단 밴드 (중심선 위 2σ).
- boll_lb: Bollinger 하단 밴드 (중심선 아래 2σ).
- atr: Average True Range — 손절 / 포지션 사이징을 위한 변동성 측정.

거래량 기반:

KRX 투자자 수급:
- 투자자별 순매수 — 외국인·기관·개인의 최근 5거래일 순매수. KRX 가격 변동의 **선행 지표**. 외국인 매도 지속은 가격 하락을, 기관 매수 유입은 반등을 선행하는 경우가 많음. 수급 섹션을 추세·모멘텀 지표와 함께 해석하세요.

**KRX 특유 리스크 (가격 분석 시 반드시 고려):**
- **상·하한가 ±30% 제한**: KRX 종목은 전일 종가 대비 ±30% 를 넘지 못합니다. +30% 상한가·-30% 하한가는 추가 모멘텀이 익일로 이연된다는 뜻 — 당일 종가로는 모멘텀의 **진짜 강도**를 측정할 수 없습니다. 상한가/하한가 근접 바를 지지/저항 반등처럼 해석하지 말고, 다음 세션 갭·거래량 재개를 함께 보세요. ATR 과 Bollinger 밴드도 ±30% 벽에서는 포화되므로 극단값 해석에 주의.
- **공매도 금지 종목**: 금융위 공매도 금지 조치가 종목별/시장별로 수시 변경. 공매도 금지 중인 종목은 **하방 압력 완화** 로 평상시보다 저항선이 더 견고하게 보일 수 있습니다. 공매도 재개 공시가 나면 급락 리스크 — 뉴스 분석가의 공시 섹션과 교차 확인하세요.
- **외국인 수급 공백**: 외국인 순매수가 수일간 0 또는 음수로 수렴하면 유동성 공급자 이탈 신호 — 가격이 소폭 하락만 해도 변동성이 크게 증폭될 수 있습니다. 투자자별 수급 섹션에서 추세를 점검하세요.

다양하고 상호 보완적인 정보를 제공하는 지표를 선택하세요 (중복 회피 — rsi 와 유사한 모멘텀 오실레이터를 동시에 선택하지 말 것). 각 지표가 현재 시장 맥락에 왜 적합한지 간결히 설명하세요.

**검증 시장 스냅샷이 정확한 OHLCV / 가격 수준 / 지표 값 주장의 원천입니다.** 사전 조회된 다른 데이터가 이와 상충해 보이면 임의로 조정한 숫자를 만들어내지 말고 불일치를 지적하세요. 사전 조회된 데이터가 구체적인 날짜·가격으로 뒷받침하지 않는 역사적 검증, 지지/저항 반등, 정확한 변동률은 주장하지 마세요.

관찰한 추세에 대해 매우 상세하고 미묘한 보고서를 작성하세요. 트레이더가 정보에 입각한 결정을 내릴 수 있도록 근거를 뒷받침해 구체적이고 실행 가능한 인사이트를 제시하세요."""
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
            "market_report": report,
        }

    return market_analyst_node
