"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_portfolio_context_from_state,
)
from tradingagents.agents.schemas import TraderProposal, render_trader_proposal
from tradingagents.agents.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state):
        company_name = state["company_of_interest"]
        instrument_context = get_instrument_context_from_state(state)
        investment_plan = state["investment_plan"]
        # The research plan digests the debate but loses exact price structure;
        # give the Trader the technical market report so entry/stop levels are
        # grounded in real ATR / support-resistance / current price (#1167). The
        # report is empty when the user did not select the market analyst, so
        # only offer it (and the grounding instruction) when it has content.
        market_report = (state["market_report"] or "").strip()
        portfolio_context = get_portfolio_context_from_state(state)

        if market_report:
            grounding = (
                "구체적 가격 수준 (진입가, 손절가, 포지션 사이징) 은 기술적 시장 보고서의 "
                "가격 구조 — 현재가, 지지/저항, ATR, 변동성 — 에 뿌리내리고, 리서치 계획은 "
                "방향성과 전략에 활용하세요. "
            )
            report_section = f"기술적 시장 보고서:\n{market_report}\n\n"
        else:
            grounding = ""
            report_section = ""

        messages = [
            {
                "role": "system",
                "content": (
                    "당신은 시장 데이터를 분석해 투자 결정을 내리는 트레이딩 에이전트입니다. "
                    "분석을 바탕으로 매수(Buy), 보유(Hold), 매도(Sell) 중 구체적인 추천을 제시하세요. "
                    + grounding
                    # Entry/stop are numeric price fields. Asking for concrete
                    # levels invites a percentage ("15%"), which is not a price
                    # and fails the structured parse (#1288).
                    + "진입가와 손절가는 종목 호가 통화의 **절대 가격 수준** 으로 지정하세요 "
                    "(예: 189.5). 백분율이나 범위는 금지 — 백분율 거리는 그에 상응하는 "
                    "가격 수준으로 변환하거나, 숫자로 명시할 수 없으면 해당 필드를 생략하세요. "
                    "\n\n**KRX 특유 리스크 (가격 수준 설정 시 반드시 반영):**\n"
                    "- **상·하한가 ±30%**: 당일 체결 가능한 범위는 전일 종가의 ±30% 이내. "
                    "진입가는 반드시 이 범위 **안에서** 지정하세요. 손절가도 같은 범위 안에서 "
                    "설정하되, 하한가 (-30%) 근접 수준에 손절을 두면 체결이 불가능해 보호가 "
                    "작동하지 않을 수 있습니다 — 하한가에서 안전 여유 (예: -25% 이내) 를 두세요.\n"
                    "- **공매도 금지 종목**: 해당 종목이 금지 리스트에 있으면 Sell 포지션은 "
                    "대차·공매 경로가 막혀 실행 비용 급증. 뉴스 분석가의 공매도 섹션을 확인하고, "
                    "금지 중이면 Sell 액션의 **실행 가능성에 유보 조건** 을 narrative 에 명시.\n"
                    "- **공시 임박 종목**: 실적 발표 / 유상증자 / 전환사채 결정 등 공시가 "
                    "임박한 종목은 익일 ±30% 변동 가능 — 진입 시점을 공시 직후로 미루는 것을 고려. "
                    + NO_EXTERNAL_TOOLS
                    + get_language_instruction()
                ),
            },
            {
                "role": "user",
                "content": (
                    f"다음은 {company_name} 에 대한 리서치 팀의 투자 계획입니다. "
                    f"{instrument_context}\n\n"
                    f"{report_section}"
                    f"{portfolio_context}\n\n"
                    f"제안된 투자 계획:\n{investment_plan}\n\n"
                    "정보에 입각하고 전략적인 거래 결정을 내리세요.\n\n"
                    "## 출력\n\n"
                    "다음 섹션을 이 순서로, 액션 라인부터 시작해 작성하세요:\n\n"
                    "- **액션**: Buy / Hold / Sell 중 **정확히 하나** (값은 영어 유지). "
                    "리서치 추천 Overweight 는 Buy, Underweight 는 Sell, 사이징은 근거의 "
                    "강도에 비례. 상충 자체는 Hold 사유가 아님.\n"
                    "- **근거**: 계획과 가격 구조를 상대로 왜 그 선택인지\n"
                    "- **진입가**, **손절가**, **포지션 사이징**: 명시 가능할 때"
                ),
            },
        ]

        trader_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
            render_trader_proposal,
            "Trader",
        )

        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
        }

    return trader_node
