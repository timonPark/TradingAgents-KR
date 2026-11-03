from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
    report_or_absent,
)


def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = opponent_argument_or_opening(
            investment_debate_state.get("current_response", ""), "bull analyst"
        )
        market_research_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")
        fundamentals_report = report_or_absent(state["fundamentals_report"], "fundamentals")
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        target_label = "종목" if asset_type == "stock" else "자산"
        fundamentals_label = (
            "기업 재무 보고서"
            if asset_type == "stock"
            else "자산 재무 보고서 (암호자산의 경우 미제공 가능)"
        )

        prompt = f"""당신은 해당 {target_label} 에 대한 투자에 반대하는 약세(Bear) 리서처입니다. 리스크, 도전 과제, 부정적 지표를 강조하는 잘 논증된 논증을 제시하는 것이 당신의 목표입니다. 제공된 리서치와 데이터를 활용해 잠재적 하방을 부각하고 강세 논증에 효과적으로 반박하세요.

핵심 포인트:

- **리스크와 도전 과제**: 시장 포화, 재무 불안정성, 성과를 저해할 거시경제 위협 등 요소를 강조.
- **경쟁 열위**: 약한 시장 포지션, 혁신 둔화, 경쟁사 위협 등 취약점을 강조.
- **부정적 지표**: 재무 데이터, 시장 트렌드, 최근 부정 뉴스를 근거로 입장을 뒷받침.
- **강세 반박**: 강세 논증을 구체적 데이터와 탄탄한 논리로 비판적으로 분석. 약점이나 지나친 낙관을 드러내세요.
- **대화형 참여**: 데이터 나열이 아닌 대화체로 강세 리서처의 지점에 직접 응답하며 효과적으로 토론하세요.

제공 자원:

{instrument_context}
시장 분석 보고서: {market_research_report}
센티먼트 보고서: {sentiment_report}
최신 뉴스: {news_report}
{fundamentals_label}: {fundamentals_report}
토론 대화 기록: {history}
강세 리서처의 최근 논증: {current_response}

이 정보를 활용해 설득력 있는 약세 논증을 전달하고, 강세의 주장을 반박하며, 해당 {target_label} 투자의 리스크와 약점을 보여주는 역동적인 토론에 참여하세요.
""" + get_language_instruction()

        response = llm.invoke(prompt)

        # 토론 로그의 발화자 라벨은 **영어 식별자 유지** (i18n 경계, ADR-0003).
        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
