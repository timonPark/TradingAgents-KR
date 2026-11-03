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
