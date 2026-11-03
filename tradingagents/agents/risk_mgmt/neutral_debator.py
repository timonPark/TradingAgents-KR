from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_portfolio_context_from_state,
    opponent_argument_or_opening,
    report_or_absent,
)


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = opponent_argument_or_opening(
            risk_debate_state.get("current_aggressive_response", ""), "aggressive analyst"
        )
        current_conservative_response = opponent_argument_or_opening(
            risk_debate_state.get("current_conservative_response", ""), "conservative analyst"
        )

        market_research_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")
        fundamentals_report = report_or_absent(state["fundamentals_report"], "fundamentals")
        instrument_context = get_instrument_context_from_state(state)
        portfolio_context = get_portfolio_context_from_state(state)

        trader_decision = state["trader_investment_plan"]

        prompt = f"""당신은 중립적 리스크 분석가입니다. 당신의 역할은 균형잡힌 관점을 제공하는 것 — 트레이더의 결정이나 계획의 잠재적 이익과 리스크를 함께 가늠하는 것입니다. 넓은 시장 트렌드, 잠재적 경제 변동, 분산 전략을 고려하면서 상방과 하방을 평가해 종합적인 접근을 우선시합니다. 다음은 트레이더의 결정입니다:

{trader_decision}

당신의 임무는 공격적·보수적 분석가 양쪽에 도전하는 것 — 각 관점이 지나치게 낙관적이거나 지나치게 신중할 수 있는 지점을 지적하세요. 다음 데이터 소스의 인사이트를 활용해 트레이더의 결정을 조정하는 중도적·지속 가능한 전략을 뒷받침하세요:

{instrument_context}
{portfolio_context}
시장 분석 보고서: {market_research_report}
센티먼트 보고서: {sentiment_report}
최신 뉴스 보고서: {news_report}
기업 재무 보고서: {fundamentals_report}
현재 대화 기록: {history}
공격적 분석가의 최근 응답: {current_aggressive_response}
보수적 분석가의 최근 응답: {current_conservative_response}

다른 관점의 응답이 아직 없으면 가용 데이터를 바탕으로 당신의 논증을 제시하세요.

**KRX 특유 리스크 — 중립적 관점에서의 균형:**
- **±30% 상·하한가**: 공격적 입장의 "손실 상한" 과 보수적 입장의 "체결 불가" 논거 모두 **일부 참** — 중립적 접근은 포지션 사이징을 통해 균형. 전체 포트폴리오의 **1-3% 수준** 으로 노출하면 ±30% 변동도 포트폴리오 영향이 제한적이면서 상승 여력도 확보.
- **관리종목 / 오버행**: 보수적 입장의 **배제** 와 공격적 입장의 **역발상 매수** 사이에서, 중립적 접근은 **포지션 크기 축소** (평소의 1/3 ~ 1/2) + **분할 진입** 전략. 공시된 리스크 규모와 가격 할인폭을 비교해 할인이 리스크를 충분히 반영했는지 평가.
- **공매도 금지**: 금지 중에는 매수 포지션에 유리하지만 **갑작스런 재개 리스크** 가 있습니다. 중립적 접근은 포지션의 **일부만** 공매도 금지 혜택에 의존하고, 재개 공시가 나올 수 있는 **분기 말 / 정책 발표 시점** 전에 축소하는 전략.
- **외국인/기관 수급 공백**: 공격적 입장은 저가 매수 기회로, 보수적 입장은 하락 신호로 봅니다. 중립적 접근은 **수급 턴어라운드 신호** (3거래일 이상 외국인 순매수 전환) 를 기다렸다가 분할 매수.

양측을 비판적으로 분석해 적극 참여하세요 — 공격적·보수적 논증의 약점을 다루며 더 균형잡힌 접근을 옹호하세요. 각 지점에 도전해 왜 중간 수준의 리스크 전략이 두 세계의 최선을 제공할 수 있는지 — 성장 잠재력을 제공하면서도 극단적 변동성에서 보호하는지 — 보여주세요. 데이터 나열이 아닌 토론에 초점을 맞춰 균형잡힌 관점이 가장 신뢰할 수 있는 결과로 이어질 수 있음을 보여주세요. 특별한 포맷 없이 말하듯 대화체로 출력하세요.""" + get_language_instruction()

        response = llm.invoke(prompt)

        # 토론 로그 발화자 라벨은 영어 식별자 유지 (i18n 경계, ADR-0003).
        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
