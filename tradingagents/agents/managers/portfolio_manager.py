"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call. Its rating is the run's
``final_rating``, and the decision is rendered to markdown as
``final_trade_decision`` for the memory log, CLI display and saved reports.
When a provider does not expose structured output, the agent falls back to
free-text generation and the rating is read from that text.
"""

from __future__ import annotations

from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_portfolio_context_from_state,
)
from tradingagents.agents.rating import parse_rating
from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.structured import NO_EXTERNAL_TOOLS, bind_structured, invoke_structured


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        portfolio_context = get_portfolio_context_from_state(state)

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- 과거 결정과 결과로부터의 교훈:\n{past_context}\n"
            if past_context
            else ""
        )

        prompt = f"""포트폴리오 매니저로서, 리스크 분석가들의 토론을 종합하고 최종 거래 결정을 전달하세요.

{instrument_context}

{portfolio_context}

---

**등급 체계** (정확히 하나 사용 — 구조화 필드 값은 영어 enum 그대로, 본문 서술은 한국어 표기):
- **Buy**: 신규 매수 또는 비중 확대에 강한 확신
- **Overweight**: 긍정적 전망, 점진적 노출 확대
- **Hold**: 현재 포지션 유지, 조치 없음
- **Underweight**: 노출 축소, 일부 차익 실현
- **Sell**: 청산 또는 진입 회피

**컨텍스트:**
- 리서치 매니저의 투자 계획: **{research_plan}**
- 트레이더의 거래 제안: **{trader_plan}**
{lessons_line}
**리스크 분석가 토론 기록:**
{history}

---

모든 결론을 분석가들의 구체적 증거에 뿌리내리세요. 리스크 토론에는 항상 상충하는 입장이 포함되며, 어느 쪽이 더 강력한지 결정하는 것이 당신의 임무입니다. 따라서 상충 자체는 Hold 사유가 아닙니다. 더 설득력 있는 쪽에 결단을 내리고 승리의 정도에 비례해 사이징하세요. 그러한 가늠 후에도 증거가 균형잡혀 있거나 판정하기에 너무 얇을 때에만 Hold 를 선택하세요; 결단력 있어 보이려고 방향을 강제하지 마세요. 발언 순서와 무관하게 분석가들을 가치만으로 평가하세요.

## 출력

다음 섹션을 이 순서로, 등급 라인부터 시작해 작성하세요:

- **등급**: Buy / Overweight / Hold / Underweight / Sell 중 **정확히 하나** (구조화 필드 값은 영어 유지). 요약 전략·투자 논리 등 본문 서술에서는 영어 등급명 대신 한국어 표기 (매수·비중 확대·보유·비중 축소·매도) 를 쓰세요.
- **요약 전략**: 결정과 실행 방법
- **투자 논리**: 결정의 근거와 뒤집힐 수 있는 조건

{NO_EXTERNAL_TOOLS}{get_language_instruction()}"""

        # The typed rating is the decision; the rendered text only carries it.
        # Read back from text, a rating the thesis quotes could replace it.
        decision = invoke_structured(structured_llm, prompt, "Portfolio Manager")
        if decision is not None:
            final_trade_decision = render_pm_decision(decision)
            final_rating = decision.rating.value
        else:
            final_trade_decision = llm.invoke(prompt).content
            final_rating = parse_rating(final_trade_decision)

        new_risk_debate_state = {
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
            "final_rating": final_rating,
        }

    return portfolio_manager_node
