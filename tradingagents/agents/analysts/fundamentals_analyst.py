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
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
)


def _prefetch_fundamentals_data(ticker: str, trade_date: str) -> dict[str, str]:
    """재무/공시 데이터를 전부 선조회.

    분기별 (`freq="quarterly"`) 재무제표를 선조회 — 분기 리포팅이 최신 트렌드를
    더 잘 반영하고 LLM 이 선호하는 세분화 수준. 실패 시 각 섹션에 에러 메시지만
    담아 반환 — 분석가 전체 중단 방지 (market_analyst 와 동일 fail-safe 패턴).
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
    return {
        "fundamentals": fundamentals,
        "balance_sheet": balance_sheet,
        "cashflow": cashflow,
        "income_statement": income_statement,
        "insider_transactions": insider_transactions,
    }


def _render_prefetched(data: dict[str, str]) -> str:
    """선조회된 데이터를 프롬프트에 주입할 Markdown 블록으로 포맷."""
    return (
        "## Pre-fetched Fundamentals Data\n\n"
        "### Company Fundamentals (overview)\n"
        f"{data['fundamentals']}\n\n"
        "### Balance Sheet (quarterly)\n"
        f"{data['balance_sheet']}\n\n"
        "### Cash Flow Statement (quarterly)\n"
        f"{data['cashflow']}\n\n"
        "### Income Statement (quarterly)\n"
        f"{data['income_statement']}\n\n"
        "### Insider Transactions (recent)\n"
        f"{data['insider_transactions']}\n"
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
            "You are a researcher tasked with analyzing fundamental information about a company. "
            "The data has been **pre-fetched for you** — company fundamentals overview, quarterly "
            "balance sheet / cash flow / income statement, and recent insider transactions. You "
            "will **not** call tools; write a comprehensive report of the company's fundamentals "
            "grounded in the pre-fetched data below. Include financial-document highlights, company "
            "profile, basic financials, and historical trends to inform traders. Provide specific, "
            "actionable insights with supporting evidence."
            " Make sure to append a Markdown table at the end of the report to organize key points, "
            "organized and easy to read."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " The data you need has been pre-fetched below; do not call tools."
                    " Report what the pre-fetched data supports; another agent decides the trade."
                    " Today's date is {current_date}; treat it as 'now' for all analysis. {instrument_context}\n"
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
