"""Sentiment analyst — 네이버 금융 뉴스 기반 감성 분석 (Task 7c, #64).

Task 3 사전조회 패턴 (ADR-0002) 과 Task 7 KRX 하드 포크에 맞춰 재구성:
- 원래 소스 3개 (Yahoo news + StockTwits + Reddit) → **네이버 금융 뉴스 단일**
- StockTwits/Reddit 는 미국 증시 소셜 플랫폼이라 KRX 커버리지 없음 (하드 포크
  결정 ADR-0001)
- 네이버 금융 뉴스는 노이즈 필터 + 날짜 범위로 관련 기사만 남긴 상태

여전히 SentimentReport (band/score/confidence/narrative) 를 반환해 다운스트림
리서처/트레이더 노드가 변경 없이 소비 가능.
"""

from datetime import datetime, timedelta

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.schemas import SentimentReport, render_sentiment_report
from tradingagents.agents.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.agents.tools import get_news


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph.

    네이버 금융 뉴스를 사전조회해 프롬프트에 주입하고, SentimentReport (band,
    score, confidence, narrative) 를 구조화 출력으로 생성. 구조화 미지원 provider
    는 free-text 폴백.
    """
    structured_llm = bind_structured(llm, SentimentReport, "Sentiment Analyst")

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = get_instrument_context_from_state(state)

        # 네이버 금융 뉴스 선조회. tool.func 로 호출해 Python 에서 결과를 받아
        # 프롬프트에 주입 (사전조회 패턴 — ADR-0002).
        try:
            news_block = get_news.func(ticker, start_date, end_date)
        except Exception as exc:  # noqa: BLE001 — 분석가 중단 방지
            news_block = f"[prefetch failed: {type(exc).__name__}: {exc}]"

        system_message = _build_system_message(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            news_block=news_block,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "당신은 다른 분석가들과 협업하는 AI 어시스턴트입니다."
                    " 가지고 있는 도구가 뒷받침하는 내용만 보고하고 — 거래 결정은 다른 에이전트의 몫입니다."
                    # 사전조회 패턴 — 데이터는 이미 프롬프트에 있음, 툴 호출 금지.
                    " 오늘 날짜는 {current_date} 입니다; 모든 분석에서 이 날짜를 '현재' 로 간주하세요. {instrument_context}"
                    " " + NO_EXTERNAL_TOOLS +
                    "\n{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        formatted_messages = prompt.format_messages(messages=state["messages"])

        report_text = invoke_structured_or_freetext(
            structured_llm,
            llm,
            formatted_messages,
            render_sentiment_report,
            "Sentiment Analyst",
        )

        return {
            "messages": [AIMessage(content=report_text)],
            "sentiment_report": report_text,
        }

    return sentiment_analyst_node


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
) -> str:
    """감성 분석 시스템 메시지 조립.

    상류의 StockTwits/Reddit 소스는 미국 증시 전용이라 KRX 하드 포크 (ADR-0001)
    에서 제거됨. 대신 네이버 금융 뉴스 단일 소스로 재구성.
    """
    return f"""당신은 금융 시장 센티먼트 분석가입니다. {ticker} 에 대해 {start_date} ~ {end_date} 기간을 다루는 종합적인 센티먼트 보고서를 작성하는 것이 당신의 임무입니다 — 당신을 위해 이미 수집된 한국 금융 뉴스를 기반으로.

## 데이터 소스 (사전 조회됨, 아래 프롬프트에 포함)

### 뉴스 헤드라인 — 네이버 금융, 최근 1주일
한국 주요 언론사의 종목 관련 보도. 사실 중심의 느린 변화 신호. 광고·묶음·인사
기사 노이즈는 vendor 가 사전에 제거.

<start_of_news>
{news_block}
<end_of_news>

## 분석 방법 (베스트 프랙티스)

1. **헤드라인의 톤 분류**: 개별 기사를 호재/악재/중립으로 나누고 비중을 세요. 재료 성격 (실적, 공시, 거시, 기관 리포트 등) 과 기자 톤 (단정형 vs 유보형) 양쪽을 봅니다.

2. **반복 테마 식별**: 어떤 주제가 여러 기사에서 반복되는지 — 현재 종목을 둘러싼 지배적 내러티브가 무엇인지 포착하세요. 공시 (실적 발표, 유상증자, 전환사채 등) 는 가격에 즉시 영향이 큼.

3. **의견 vs 사실 구분**: 애널리스트 리포트/증권사 전망 같은 의견성 기사는 사실 보도와 다르게 가중치를 두세요.

4. **데이터 한계 명시**: 뉴스가 소수 (5건 미만) 거나 `[prefetch failed]` 또는 `DATA_UNAVAILABLE` 플레이스홀더가 포함되면 (수집 실패이지 뉴스 없음이 아님) `confidence` 를 낮추고 `narrative` 에 명시하세요. 상류의 StockTwits/Reddit 등 소셜 소스는 KRX 하드 포크 (ADR-0001) 에서 제거됐으므로 신호 부재는 "소셜 데이터 없음" 이 아니라 "뉴스 단일 소스" 로 기술.

5. **촉매·리스크 분리**: 다가올 실적 발표, 신제품/서비스, 규제, 경쟁사 동향 등 catalyst 를 분리해 추출. 다음 **KRX 특유 리스크** 는 발견 즉시 **심각 리스크** 로 분류하고 `overall_band` / `confidence` 에 반영:
   - **관리종목 / 환기종목 지정 또는 사유 발생**: 상장폐지 전 단계 신호 — 센티먼트는 급격히 Bearish 로 기울 가능성 ↑.
   - **상장폐지 사유 공시**: 매도 창구가 좁아짐 — 가장 강한 Bearish 센티먼트 신호.
   - **대주주 매도 / 블록딜 / 보호예수 해제 (오버행)**: 공시된 수량이 시장에 잠재 매도 압력 — 상단 억제, 센티먼트 하방 지속.
   - **공매도 금지 재개 공시**: 하방 압력 급증 — 수일 간 Bearish 센티먼트 유지 가능.
   - **유상증자 / 전환사채(CB) 발행**: 신주 희석 — 기존 주주 센티먼트는 발행 조건 (할인율·전환가 조정) 에 따라 Mildly Bearish ~ Bearish.

6. **과거 센티먼트는 예측이 아님**: 결론은 "트레이더가 재무/기술적 분석과 함께 참고할 신호" 로 제시, 가격 call 로 쓰지 마세요.

## 출력 필드

다음 필드를 채우세요:

- **overall_band**: Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish 중 **정확히 하나** (구조화 필드 값은 영어 유지). 헤드라인이 명확히 양분되면 Mixed, 피드가 진정으로 침묵하는 경우에만 Neutral. narrative 본문에서는 영어 대신 강세·약한 강세·중립·혼조·약한 약세·약세 같은 한국어 표기를 쓰세요.
- **overall_score**: 0 (가장 약세) ~ 10 (가장 강세) 사이의 수치; 5는 중립. overall_band 와 일관성 유지.
- **confidence**: low / medium / high (구조화 필드 값은 영어 유지), 데이터 품질과 샘플 크기에 기반.
- **narrative**: 섹션별 breakdown (호재/악재/중립 구성), 지배 내러티브, catalyst/리스크, markdown summary table (방향, 소스, 근거).

{get_language_instruction()}"""
