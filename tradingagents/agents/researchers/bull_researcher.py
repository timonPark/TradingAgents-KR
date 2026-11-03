from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
    report_or_absent,
)


def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = opponent_argument_or_opening(
            investment_debate_state.get("current_response", ""), "bear analyst"
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

        prompt = f"""당신은 해당 {target_label} 에 대한 투자를 옹호하는 강세(Bull) 리서처입니다. 당신의 임무는 성장 잠재력, 경쟁 우위, 긍정적 시장 지표를 강조하는 근거 기반의 강력한 논증을 구축하는 것입니다. 제공된 리서치와 데이터를 활용해 우려사항을 다루고 약세 논증에 효과적으로 반박하세요.

핵심 포인트:
- **성장 잠재력**: 기업의 시장 기회, 매출 전망, 확장성을 강조.
- **경쟁 우위**: 독특한 제품, 강력한 브랜딩, 지배적 시장 포지션 등 요소를 강조.
- **긍정 지표**: 재무 건전성, 산업 트렌드, 최근 긍정 뉴스를 근거로 활용.
- **약세 반박**: 약세 논증을 구체적 데이터와 탄탄한 논리로 비판적으로 분석. 우려사항을 철저히 다루고 왜 강세 관점이 더 설득력 있는지 보여주세요.
- **대화형 참여**: 데이터 나열이 아닌 대화체로 약세 리서처의 지점에 직접 응답하며 효과적으로 토론하세요.

제공 자원:
{instrument_context}
시장 분석 보고서: {market_research_report}
센티먼트 보고서: {sentiment_report}
최신 뉴스: {news_report}
{fundamentals_label}: {fundamentals_report}
토론 대화 기록: {history}
약세 리서처의 최근 논증: {current_response}

이 정보를 활용해 설득력 있는 강세 논증을 전달하고, 약세의 우려를 반박하며, 강세 입장의 강점을 보여주는 역동적인 토론에 참여하세요.
""" + get_language_instruction()

        response = llm.invoke(prompt)

        # 토론 로그의 발화자 라벨은 **영어 식별자 유지** — 다운스트림 (research_manager
        # 가 history 를 읽어 bull/bear 흐름을 추적) 와 테스트에서 "Bull Analyst:" /
        # "Bear Analyst:" 로 분기하기 때문. i18n 경계 (ADR-0003).
        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
