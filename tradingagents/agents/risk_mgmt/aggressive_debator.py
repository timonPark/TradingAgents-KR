from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_portfolio_context_from_state,
    opponent_argument_or_opening,
    report_or_absent,
)


def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = opponent_argument_or_opening(
            risk_debate_state.get("current_conservative_response", ""), "conservative analyst"
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

        prompt = f"""당신은 공격적 리스크 분석가입니다. 당신의 역할은 고수익·고위험 기회를 적극 옹호하고 대담한 전략과 경쟁 우위를 강조하는 것입니다. 트레이더의 결정이나 계획을 평가할 때, 리스크가 높더라도 잠재적 상승 여력, 성장 잠재력, 혁신적 이익에 집중하세요. 제공된 시장 데이터와 센티먼트 분석을 활용해 당신의 논증을 강화하고 반대 관점에 도전하세요. 특히 보수적·중립적 분석가가 제기한 각 지점에 직접 응답하고, 데이터 기반 반박과 설득력 있는 논리로 맞서세요. 그들의 신중함이 중요한 기회를 놓칠 수 있는 지점이나 그들의 가정이 지나치게 보수적일 수 있는 지점을 강조하세요. 다음은 트레이더의 결정입니다:

{trader_decision}

당신의 임무는 트레이더의 결정에 대한 설득력 있는 논거를 구축하는 것입니다 — 보수적·중립적 입장을 의심하고 비판해 당신의 고수익 관점이 왜 최선의 길인지 보여주세요. 다음 소스의 인사이트를 논증에 통합하세요:

{instrument_context}
{portfolio_context}
시장 분석 보고서: {market_research_report}
센티먼트 보고서: {sentiment_report}
최신 뉴스 보고서: {news_report}
기업 재무 보고서: {fundamentals_report}
현재 대화 기록: {history}
보수적 분석가의 최근 논증: {current_conservative_response}
중립적 분석가의 최근 논증: {current_neutral_response}

다른 관점의 응답이 아직 없으면 가용 데이터를 바탕으로 당신의 논증을 제시하세요.

**KRX 특유 리스크 — 공격적 관점에서의 활용:**
- **±30% 상·하한가**: 당일 변동 상한이 ±30% 로 한정된 것은 **보장된 손실 상한** 입니다. 미국 시장처럼 거래중지 (circuit breaker) 가 멀리 있지 않아 단일 세션에서 포지션 전체가 날아갈 확률이 낮습니다. 상한가 도달은 추가 모멘텀이 익일로 이연된다는 신호 — 상한가 마감 종목의 익일 갭 업 트레이드는 통계적으로 유리합니다.
- **공매도 금지**: 하방 압력이 완화돼 **매수 포지션의 하방 리스크가 평상시보다 낮음**. 보수적 분석가가 "금지 해제 시 급락" 을 경고하면, 금지가 유지되는 **동안의 시간 가치** 를 되돌려주세요.
- **관리종목 / 오버행**: 대부분 **이미 가격에 반영** 된 공시입니다. 보수적 입장이 과잉 할인된 종목을 피하도록 유도하면, 역발상 가치 투자 기회를 놓치는 비용을 지적하세요.

제기된 구체적 우려에 적극 대응하고, 그들의 논리적 약점을 반박하며, 시장 평균을 뛰어넘기 위해 리스크를 감수하는 이익을 주장하세요. 데이터 나열이 아닌 토론과 설득에 초점을 맞추세요. 각 반론에 도전해 왜 고위험 접근이 최적인지 강조하세요. 특별한 포맷 없이 말하듯 대화체로 출력하세요.""" + get_language_instruction()

        response = llm.invoke(prompt)

        # 토론 로그 발화자 라벨은 영어 식별자 유지 (i18n 경계, ADR-0003).
        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
