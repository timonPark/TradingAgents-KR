"""#163: 재무 분석가 — 회사 개요(사업보고서 발췌)를 근거 자료로 주입하고 상태에 보존한다."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.agents.analysts import fundamentals_analyst as fa

_BUSINESS = json.dumps({
    "company_name": "(주)알테오젠", "report": "사업보고서 (2025.12)", "rcept_no": "20260323001596",
    "overview": "당사는 바이오기업입니다.",
}, ensure_ascii=False)


def _data(business):
    return {"business_overview": business, "financial_accounts": "{}", "fundamentals": "f",
            "balance_sheet": "b", "cashflow": "c", "income_statement": "i",
            "insider_transactions": "t", "convertible_bonds": "cb"}


@pytest.mark.unit
def test_overview_is_rendered_with_its_source():
    out = fa._render_business_overview(_BUSINESS)
    assert out.startswith("당사는 바이오기업입니다.")
    assert "출처: DART 사업보고서 (2025.12) (접수번호 20260323001596)" in out


@pytest.mark.unit
@pytest.mark.parametrize("text", ["조회된 정기보고서가 없습니다.", "[DART 조회 실패: no key]", "", "not json"])
def test_unreadable_overview_is_stated_not_invented(text):
    out = fa._render_business_overview(text)
    assert out.startswith("(회사 개요를 가져오지 못했습니다")


@pytest.mark.unit
def test_prefetched_block_puts_the_overview_before_the_statements():
    block = fa._render_prefetched(_data(_BUSINESS))
    assert block.index("### 회사 개요") < block.index("### 기업 개황") < block.index("### 재무상태표")
    assert "당사는 바이오기업입니다." in block


@pytest.mark.unit
def test_node_keeps_the_overview_in_state_and_forbids_filling_gaps_from_memory():
    captured = {}

    def fake_invoke(prompt, llm, messages):
        captured["system"] = prompt.format_messages(messages=[])[0].content
        return MagicMock(), "리포트"

    with patch.object(fa, "_prefetch_fundamentals_data", return_value=_data(_BUSINESS)), \
            patch.object(fa, "invoke_once", side_effect=fake_invoke):
        out = fa.create_fundamentals_analyst(MagicMock())(
            {"trade_date": "2026-11-05", "company_of_interest": "196170", "messages": []})

    assert out["fundamentals_data"] == {"accounts": "{}", "business": _BUSINESS}
    assert "공시 발췌에 근거해" in captured["system"] and "학습 지식으로 채우지 말고" in captured["system"]
    assert "당사는 바이오기업입니다." in captured["system"]
