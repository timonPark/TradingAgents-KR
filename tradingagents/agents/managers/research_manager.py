"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        history = state["investment_debate_state"].get("history", "")

        investment_debate_state = state["investment_debate_state"]

        prompt = f"""리서치 매니저이자 토론 조정자로서, 당신의 역할은 이번 라운드의 토론을 비판적으로 평가하고 트레이더에게 명확하고 실행 가능한 투자 계획을 전달하는 것입니다.

{instrument_context}

---

**등급 체계** (정확히 하나 사용 — 구조화 필드 값은 영어 enum 그대로, 본문 서술은 한국어 표기):
- **Buy**: 강세 논증에 강한 확신; 신규 매수 또는 비중 확대 권고
- **Overweight**: 긍정적 관점; 점진적 노출 확대 권고
- **Hold**: 균형 관점; 현재 포지션 유지 권고
- **Underweight**: 신중한 관점; 노출 축소 권고
- **Sell**: 약세 논증에 강한 확신; 청산 또는 회피 권고

토론에는 항상 상충하는 논증이 포함되며, 어느 쪽이 더 강력한지 결정하는 것이 당신의 임무입니다. 따라서 상충 자체는 Hold 사유가 아닙니다. 더 설득력 있는 쪽에 결단을 내리고 승리의 정도에 비례해 사이징하세요. 그러한 가늠 후에도 증거가 균형잡혀 있거나 판정하기에 너무 얇을 때에만 Hold 를 선택하세요; 결단력 있어 보이려고 방향을 조작하지 마세요. 어느 쪽이 먼저 또는 나중에 말했는지와 무관하게 강세와 약세 논거의 가치만으로 평가하세요.

---

**토론 기록:**
{history}

## 출력

다음 섹션을 이 순서로, 추천 라인부터 시작해 작성하세요:

- **추천**: Buy / Overweight / Hold / Underweight / Sell 중 **정확히 하나** (구조화 필드 값은 영어 유지). 근거 등 본문 서술에서는 영어 등급명 대신 한국어 표기 (매수·비중 확대·보유·비중 축소·매도) 를 쓰세요.
- **근거**: 어떤 논증이 결정했는지
- **전략적 조치**: 트레이더를 위한 구체적 단계, 표준 할당 대비 사이징

{NO_EXTERNAL_TOOLS}""" + get_language_instruction()

        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_research_plan,
            "Research Manager",
        )

        new_investment_debate_state = {
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node
