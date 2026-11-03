"""Fundamentals analyst — 사전조회 패턴 (Task 3b #34, ADR-0002).

Python 이 분석가 노드 진입 시점에 재무 데이터 (fundamentals/balance sheet/
cashflow/income statement/insider transactions) 를 미리 조회해 프롬프트에
주입합니다. LLM 은 사전조회된 데이터만 보고 보고서를 작성 — `bind_tools` 호출
없음, 분석가당 Claude Code 호출 1회.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.analysts.invoke import invoke_once
from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.tools import (
    get_balance_sheet,
    get_cashflow,
    get_convertible_bonds,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
)


def _prefetch_fundamentals_data(ticker: str, trade_date: str) -> dict[str, str]:
    """재무/공시 데이터를 전부 선조회.

    분기별 (`freq="quarterly"`) 재무제표를 선조회 — 분기 리포팅이 최신 트렌드를
    더 잘 반영하고 LLM 이 선호하는 세분화 수준. 실패 시 각 섹션에 에러 메시지만
    담아 반환 — 분석가 전체 중단 방지 (market_analyst 와 동일 fail-safe 패턴).

    Task 5b (#48): KRX 전용 `get_convertible_bonds` (CB 발행 공시) 선조회 추가.
    CB 는 희석 리스크 지표라 분석가가 투자 판단에 반영해야 함.
    """
    def _safe(fn, payload: dict) -> str:
        try:
            return fn.invoke(payload)
        except Exception as exc:  # noqa: BLE001 — 분석가 중단 방지
            return f"[prefetch failed: {type(exc).__name__}: {exc}]"

    fundamentals = _safe(get_fundamentals, {
        "ticker": ticker,
        "curr_date": trade_date,
        "trade_date": trade_date,
    })
    balance_sheet = _safe(get_balance_sheet, {
        "ticker": ticker,
        "freq": "quarterly",
        "curr_date": trade_date,
        "trade_date": trade_date,
    })
    cashflow = _safe(get_cashflow, {
        "ticker": ticker,
        "freq": "quarterly",
        "curr_date": trade_date,
        "trade_date": trade_date,
    })
    income_statement = _safe(get_income_statement, {
        "ticker": ticker,
        "freq": "quarterly",
        "curr_date": trade_date,
        "trade_date": trade_date,
    })
    insider_transactions = _safe(get_insider_transactions, {
        "ticker": ticker,
        "trade_date": trade_date,
    })
    convertible_bonds = _safe(get_convertible_bonds, {
        "ticker": ticker,
        "trade_date": trade_date,
    })
    return {
        "fundamentals": fundamentals,
        "balance_sheet": balance_sheet,
        "cashflow": cashflow,
        "income_statement": income_statement,
        "insider_transactions": insider_transactions,
        "convertible_bonds": convertible_bonds,
    }


def _render_prefetched(data: dict[str, str]) -> str:
    """선조회된 데이터를 프롬프트에 주입할 Markdown 블록으로 포맷."""
    return (
        "## 사전 조회된 재무 데이터\n\n"
        "### 기업 개황\n"
        f"{data['fundamentals']}\n\n"
        "### 재무상태표 (분기)\n"
        f"{data['balance_sheet']}\n\n"
        "### 현금흐름표 (분기)\n"
        f"{data['cashflow']}\n\n"
        "### 손익계산서 (분기)\n"
        f"{data['income_statement']}\n\n"
        "### 임원·주요주주 지분변동 (최근)\n"
        f"{data['insider_transactions']}\n\n"
        "### 전환사채(CB) 발행 공시 (최근 1년)\n"
        f"{data['convertible_bonds']}\n"
    )


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        ticker = state["company_of_interest"]

        # Task 3b (#34): LLM 호출 전에 Python 이 재무 데이터 전부 선조회.
        prefetched = _prefetch_fundamentals_data(ticker, current_date)
        prefetched_block = _render_prefetched(prefetched)

        system_message = (
            "당신은 기업의 기본 정보를 분석하는 재무 분석가입니다. "
            "데이터는 이미 **사전 조회되어 프롬프트에 주입**되어 있습니다 — 기업 개황, "
            "분기별 재무상태표 / 현금흐름표 / 손익계산서, 최근 임원·주요주주 지분변동, "
            "그리고 KRX 전용 전환사채(CB) 공시. **툴을 호출하지 말고** 주어진 데이터를 "
            "기반으로 종합적인 재무 분석 보고서를 작성하세요. 공시 하이라이트, 기업 프로필, "
            "핵심 재무지표, 시계열 트렌드를 포함해 트레이더가 판단할 수 있는 구체적이고 "
            "실행 가능한 인사이트를 근거와 함께 제시하세요."
            " 보고서 말미에 핵심 포인트를 정리한 Markdown 표를 반드시 첨부해 가독성을 높이세요."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "당신은 다른 분석가들과 협업하는 AI 어시스턴트입니다."
                    " 필요한 데이터는 이미 아래에 사전 조회되어 있으므로 툴을 호출하지 마세요."
                    " 사전 조회된 데이터가 뒷받침하는 내용만 보고하고 — 거래 결정은 다른 에이전트의 몫입니다."
                    " 오늘 날짜는 {current_date} 입니다; 모든 분석에서 이 날짜를 '현재' 로 간주하세요. {instrument_context}\n"
                    "{system_message}\n\n"
                    "{prefetched}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(prefetched=prefetched_block)

        result, report = invoke_once(prompt, llm, state["messages"])

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
