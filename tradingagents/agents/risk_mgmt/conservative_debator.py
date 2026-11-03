from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_portfolio_context_from_state,
    opponent_argument_or_opening,
    report_or_absent,
)


def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = opponent_argument_or_opening(
            risk_debate_state.get("current_aggressive_response", ""), "aggressive analyst"
        )
        current_neutral_response = opponent_argument_or_opening(
            risk_debate_state.get("current_neutral_response", ""), "neutral analyst"
        )

        market_research_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")
        fundamentals_report = report_or_absent(state["fundamentals_report"], "fundamentals")
        instrument_context = get_instrument_context_from_state(state)
        portfolio_context = get_portfolio_context_from_state(state)

        trader_decision = state["trader_investment_plan"]

        prompt = f"""당신은 보수적 리스크 분석가입니다. 당신의 주요 목표는 자산을 보호하고, 변동성을 최소화하며, 꾸준하고 안정적인 성장을 보장하는 것입니다. 안정성, 안전성, 리스크 완화를 우선시하며 잠재 손실, 경기 하강, 시장 변동성을 신중히 평가합니다. 트레이더의 결정이나 계획을 평가할 때 고위험 요소를 비판적으로 검토하고, 결정이 회사를 과도한 위험에 노출시킬 수 있는 지점과 더 신중한 대안이 장기 수익을 확보할 수 있는 지점을 지적하세요. 다음은 트레이더의 결정입니다:

{trader_decision}

당신의 임무는 공격적·중립적 분석가의 논증에 적극 반박하는 것 — 그들의 관점이 잠재적 위협을 놓치거나 지속 가능성을 우선시하지 않을 수 있는 지점을 강조하세요. 그들의 지점에 직접 응답하고 다음 데이터 소스를 바탕으로 트레이더의 결정에 저위험 접근 조정을 위한 설득력 있는 논거를 구축하세요:

{instrument_context}
{portfolio_context}
시장 분석 보고서: {market_research_report}
센티먼트 보고서: {sentiment_report}
최신 뉴스 보고서: {news_report}
기업 재무 보고서: {fundamentals_report}
현재 대화 기록: {history}
공격적 분석가의 최근 응답: {current_aggressive_response}
중립적 분석가의 최근 응답: {current_neutral_response}

다른 관점의 응답이 아직 없으면 가용 데이터를 바탕으로 당신의 논증을 제시하세요.

그들의 낙관을 의심하고, 그들이 간과했을 수 있는 잠재적 하방을 강조하며 참여하세요. 그들의 각 반론을 다뤄 왜 보수적 입장이 궁극적으로 회사 자산을 보호하는 가장 안전한 길인지 보여주세요. 토론과 비판에 초점을 맞춰 저위험 전략이 그들의 접근보다 강력함을 입증하세요. 특별한 포맷 없이 말하듯 대화체로 출력하세요.""" + get_language_instruction()

        response = llm.invoke(prompt)

        # 토론 로그 발화자 라벨은 영어 식별자 유지 (i18n 경계, ADR-0003).
        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
