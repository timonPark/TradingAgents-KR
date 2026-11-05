"""Task 5a (#47): DART vendor 유닛 테스트.

실제 OpenDartReader / Open DART API 는 호출하지 않고 전부 모킹. 통합 테스트
(실제 ``DART_API_KEY`` + 네트워크) 는 Task 11 로 분산.
"""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows.vendors import dart

_REAL_KEY = os.environ.get("DART_API_KEY", "").strip()   # import 시점 — 더미 키로 덮이기 전


@pytest.fixture(autouse=True)
def _fresh_dart(monkeypatch, request):
    """각 테스트가 lazy singleton 영향을 받지 않도록 초기화 + 더미 API 키 세팅.

    실호출(integration) 테스트는 진짜 키를 써야 하므로 더미 키로 덮지 않는다.
    """
    live = request.node.get_closest_marker("integration") and _REAL_KEY
    monkeypatch.setenv("DART_API_KEY", _REAL_KEY if live else "test-key")
    dart._reset_for_tests()
    yield
    dart._reset_for_tests()


def _finstate_df():
    """``finstate_all`` 이 반환하는 전형적 DataFrame mock."""
    return pd.DataFrame({
        "sj_div": ["IS", "IS", "BS", "BS", "CF"],
        "account_nm": ["매출액", "영업이익", "자산총계", "부채총계", "영업활동현금흐름"],
        "thstrm_amount": ["1,000,000", "150,000", "5,000,000", "2,000,000", "200,000"],
        "frmtrm_amount": ["900,000", "130,000", "4,800,000", "1,900,000", "180,000"],
        "bfefrmtrm_amount": ["850,000", "120,000", "4,500,000", "1,800,000", "170,000"],
    })


@pytest.mark.unit
def test_dart_init_requires_api_key(monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    dart._reset_for_tests()
    result = dart.get_fundamentals("005930", "2026-11-03")
    assert "DART_API_KEY" in result
    assert "DART 조회 실패" in result


@pytest.mark.unit
def test_dart_init_caches_instance():
    """``_dart()`` 가 lazy singleton 으로 OpenDartReader 를 한 번만 생성."""
    with patch.object(dart, "_resolve_opendartreader_class") as mock_resolve:
        instance = MagicMock()
        mock_cls = MagicMock(return_value=instance)
        mock_resolve.return_value = mock_cls
        a = dart._dart()
        b = dart._dart()
        assert a is b
        mock_cls.assert_called_once_with("test-key")


@pytest.mark.unit
def test_get_fundamentals_renders_overview_and_recent_statements():
    fake = MagicMock()
    fake.company.return_value = {
        "corp_name": "삼성전자",
        "corp_name_eng": "Samsung Electronics",
        "ceo_nm": "한종희, 노태문",
        "corp_cls": "유가증권",
        "est_dt": "19690113",
    }
    fake.finstate_all.return_value = _finstate_df()
    with patch.object(dart, "_resolve_opendartreader_class", return_value=lambda _k: fake):
        result = dart.get_fundamentals("005930", "2026-11-03")

    assert "기업 개황" in result
    assert "삼성전자" in result
    assert "한종희" in result
    assert "최근 재무제표" in result
    assert "매출액" in result  # 손익계산서 섹션
    assert "자산총계" in result  # 재무상태표 섹션


@pytest.mark.unit
def test_get_fundamentals_handles_missing_statement_gracefully():
    """``finstate_all`` 이 모든 연도/보고서에서 None 반환 → 섹션 메시지."""
    fake = MagicMock()
    fake.company.return_value = {"corp_name": "삼성전자"}
    fake.finstate_all.return_value = pd.DataFrame()  # empty
    with patch.object(dart, "_resolve_opendartreader_class", return_value=lambda _k: fake):
        result = dart.get_fundamentals("005930", "2026-11-03")

    assert "조회된 공시가 없습니다" in result or "최근 재무제표: 조회된 공시가 없습니다" in result


@pytest.mark.unit
def test_get_fundamentals_absorbs_vendor_exceptions():
    """``company()`` 가 예외를 던지면 섹션 단위로 수용하고 분석가 run 은 유지."""
    fake = MagicMock()
    fake.company.side_effect = RuntimeError("boom")
    fake.finstate_all.return_value = _finstate_df()
    with patch.object(dart, "_resolve_opendartreader_class", return_value=lambda _k: fake):
        result = dart.get_fundamentals("005930", "2026-11-03")

    assert "조회 실패" in result or "boom" in result
    assert "최근 재무제표" in result  # 재무 섹션은 계속 포함


@pytest.mark.unit
def test_get_balance_sheet_formats_bs_section():
    fake = MagicMock()
    fake.finstate_all.return_value = _finstate_df()
    with patch.object(dart, "_resolve_opendartreader_class", return_value=lambda _k: fake):
        result = dart.get_balance_sheet("005930", freq="quarterly", curr_date="2026-11-03")

    assert "재무상태표" in result
    assert "자산총계" in result
    assert "부채총계" in result


@pytest.mark.unit
def test_get_cashflow_formats_cf_section():
    fake = MagicMock()
    fake.finstate_all.return_value = _finstate_df()
    with patch.object(dart, "_resolve_opendartreader_class", return_value=lambda _k: fake):
        result = dart.get_cashflow("005930", freq="quarterly", curr_date="2026-11-03")

    assert "현금흐름표" in result
    assert "영업활동현금흐름" in result


@pytest.mark.unit
def test_get_income_statement_falls_back_to_is_when_cis_absent():
    """포괄손익(CIS) 섹션이 없으면 손익계산서(IS) 를 반환."""
    df = _finstate_df()  # has IS but no CIS
    fake = MagicMock()
    fake.finstate_all.return_value = df
    with patch.object(dart, "_resolve_opendartreader_class", return_value=lambda _k: fake):
        result = dart.get_income_statement("005930", freq="quarterly", curr_date="2026-11-03")

    assert "매출액" in result
    assert "영업이익" in result


@pytest.mark.unit
def test_get_insider_transactions_formats_shareholder_rows():
    fake = MagicMock()
    fake.major_shareholders_exec.return_value = pd.DataFrame({
        "repror": ["이재용", "홍라희"],
        "isu_exctv_rgist_at": ["대표이사", "주요주주"],
        "sp_stock_lmp_cnt": ["97,414,196", "11,739,000"],
        "trde_dt": ["20250115", "20250220"],
    })
    with patch.object(dart, "_resolve_opendartreader_class", return_value=lambda _k: fake):
        result = dart.get_insider_transactions("005930")

    assert "이재용" in result
    assert "홍라희" in result


@pytest.mark.unit
def test_get_insider_transactions_handles_empty():
    fake = MagicMock()
    fake.major_shareholders_exec.return_value = pd.DataFrame()
    with patch.object(dart, "_resolve_opendartreader_class", return_value=lambda _k: fake):
        result = dart.get_insider_transactions("005930")

    assert "지분변동" in result or "없습니다" in result


@pytest.mark.unit
def test_get_convertible_bonds_filters_report_names():
    """``report_nm`` 에 "전환사채" 가 들어간 공시만 추려서 반환."""
    fake = MagicMock()
    fake.list.return_value = pd.DataFrame({
        "rcept_dt": ["20250110", "20250305", "20250420"],
        "report_nm": [
            "주요사항보고서(전환사채권발행결정)",
            "분기보고서",
            "주요사항보고서(전환사채권발행결정)",
        ],
        "flr_nm": ["이사회", "회사", "이사회"],
    })
    with patch.object(dart, "_resolve_opendartreader_class", return_value=lambda _k: fake):
        result = dart.get_convertible_bonds("005930")

    assert "전환사채" in result
    assert "20250110" in result
    assert "20250420" in result
    assert "분기보고서" not in result  # non-CB 는 제외


@pytest.mark.unit
def test_get_convertible_bonds_handles_no_cb():
    """최근 1년간 CB 공시가 하나도 없는 경우 명시적 안내."""
    fake = MagicMock()
    fake.list.return_value = pd.DataFrame({
        "rcept_dt": ["20250110"],
        "report_nm": ["분기보고서"],
        "flr_nm": ["회사"],
    })
    with patch.object(dart, "_resolve_opendartreader_class", return_value=lambda _k: fake):
        result = dart.get_convertible_bonds("005930")

    assert "전환사채" in result and "없습니다" in result


@pytest.mark.unit
def test_balance_sheet_and_cashflow_error_messages_when_no_data():
    fake = MagicMock()
    fake.finstate_all.return_value = pd.DataFrame()  # empty
    with patch.object(dart, "_resolve_opendartreader_class", return_value=lambda _k: fake):
        bs = dart.get_balance_sheet("005930", freq="quarterly", curr_date="2026-11-03")
        cf = dart.get_cashflow("005930", freq="quarterly", curr_date="2026-11-03")

    assert "없습니다" in bs
    assert "없습니다" in cf


# ============================================================================
# Integration tests (Task 11b, #93) — 실제 Open DART API 호출. CI 는 skip.
#   로컬 실행: ``DART_API_KEY=... pytest tests/test_dart_vendor.py -m integration``
# ============================================================================


@pytest.mark.integration
def test_live_dart_fundamentals_for_005930(dart_api_key):
    """DART 에서 삼성전자 기업 개황 + 최근 재무제표 조회."""
    out = dart.get_fundamentals("005930", "2026-11-03")
    # 기업 개황 섹션 (성공 또는 vendor 에러 메시지)
    assert "기업 개황" in out or "DART 조회 실패" in out
    if "DART 조회 실패" not in out:
        assert "삼성전자" in out


@pytest.mark.integration
def test_live_dart_company_profile_for_005930(dart_api_key):
    """get_company_profile 이 KOSPI 분류를 돌려줌."""
    profile = dart.get_company_profile("005930")
    assert isinstance(profile, dict)
    # 성공 시 longName + exchange, 실패 시 빈 dict
    if profile:
        assert profile.get("exchange") in ("KOSPI", "KOSDAQ", "KONEX", "기타")
        assert profile.get("longName")


# ============================================================================
# #149: 핵심 계정 구조화 — 표준 계정 ID 로 식별
# ============================================================================

NAN = float("nan")


def _rows(*rows):
    """(sj_div, account_id, account_nm, 당기, 누적, detail) → finstate_all 형태 DataFrame."""
    return pd.DataFrame([
        {"sj_div": sj, "account_id": aid, "account_nm": nm, "thstrm_amount": cur,
         "thstrm_add_amount": add, "account_detail": detail}
        for sj, aid, nm, cur, add, detail in rows
    ])


def _doosan_like():
    """IS + CIS + CF 가 모두 있는 회사 (반기). IS 의 ``당기`` 는 2분기 3개월치, 누적은 6개월."""
    return _rows(
        ("IS", "ifrs-full_Revenue", "매출액", "4,724,808", "8,985,938", "-"),
        ("IS", "ifrs-full_CostOfSales", "매출원가", "3,838,343", "7,355,331", "-"),
        ("IS", "ifrs-full_GrossProfit", "매출총이익", "886,465", "1,630,607", "-"),
        ("IS", "dart_OperatingIncomeLoss", "영업이익", "314,260", "547,774", "-"),
        ("IS", "ifrs-full_ProfitLoss", "반기순이익", "226,368", "286,594", "-"),
        ("CIS", "ifrs-full_ProfitLoss", "반기순이익", "1", "1", "-"),          # IS 가 우선
        ("CF", "ifrs-full_ProfitLoss", "반기순이익", "999", NAN, "-"),         # 현금흐름표의 같은 ID
        ("CF", "dart_CashAndCashEquivalentsAtBeginningOfPeriodCf", "기초 현금및현금성자산", "3,080,997", NAN, "-"),
        ("CF", "dart_CashAndCashEquivalentsAtEndOfPeriodCf", "반기말 현금및현금성자산", "2,541,888", NAN, "-"),
        ("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동으로 인한 현금흐름", "-886,652", NAN, "-"),
        ("CF", "ifrs-full_CashFlowsFromUsedInInvestingActivities", "투자활동으로 인한 현금흐름", "-519,859", NAN, "-"),
        ("CF", "ifrs-full_CashFlowsFromUsedInFinancingActivities", "재무활동으로 인한 현금흐름", "742,781", NAN, "-"),
        ("CF", "ifrs-full_EffectOfExchangeRateChangesOnCashAndCashEquivalents", "환율변동 효과", "124,621", NAN, "-"),
    )


def _kumho_like():
    """손익계산서(IS)가 없고 포괄손익계산서(CIS) 하나에 손익이 있는 회사. 계정명이 다르다."""
    return _rows(
        ("CIS", "ifrs-full_Revenue", "수익", "7,881,579", "18,687,443", "-"),
        ("CIS", "dart_OperatingIncomeLoss", "영업이익(손실)", "-1,027,629", "-986,018", "-"),
        ("CIS", "ifrs-full_ProfitLoss", "당기순이익(손실)", "-787,109", "1,922,976", "-"),
        ("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", "-4,713,250", NAN, "-"),
    )


@pytest.mark.unit
def test_income_items_use_cumulative_amount_not_the_quarter_only_current_amount():
    out = dart.extract_key_accounts(_doosan_like(), 2026, "11012")
    assert out["accounts"]["revenue"]["value"] == 8_985_938.0      # 누적 (당기 4,724,808 은 2분기만)
    assert out["accounts"]["operating_income"]["value"] == 547_774.0
    assert out["period"] == "반기 누적 (1~6월)" and out["report"] == "반기보고서"
    assert out["basis"] == "연결" and out["unit"] == "원" and out["year"] == 2026


@pytest.mark.unit
def test_cash_flow_items_use_the_current_amount_which_is_already_cumulative():
    accounts = dart.extract_key_accounts(_doosan_like(), 2026, "11012")["accounts"]
    assert accounts["cfo"]["value"] == -886_652.0
    assert accounts["cash_begin"]["value"] == 3_080_997.0 and accounts["cash_end"]["value"] == 2_541_888.0


@pytest.mark.unit
def test_net_income_is_not_read_from_the_cash_flow_statement():
    accounts = dart.extract_key_accounts(_doosan_like(), 2026, "11012")["accounts"]
    assert accounts["net_income"]["value"] == 286_594.0           # IS 누적. CF(999)·CIS(1) 아님


@pytest.mark.unit
def test_company_without_income_statement_is_read_from_the_comprehensive_one():
    accounts = dart.extract_key_accounts(_kumho_like(), 2026, "11012")["accounts"]
    assert accounts["revenue"] == {"name": "수익", "value": 18_687_443.0}       # 계정명이 달라도 같은 ID
    assert accounts["operating_income"]["value"] == -986_018.0                   # 음수(손실) 보존
    assert accounts["net_income"]["value"] == 1_922_976.0


@pytest.mark.unit
@pytest.mark.parametrize(("code", "period"), [
    ("11013", "1분기 누적 (1~3월)"), ("11014", "3분기 누적 (1~9월)"), ("11011", "연간"),
])
def test_report_without_cumulative_amount_falls_back_to_current_amount(code, period):
    df = _rows(("IS", "ifrs-full_Revenue", "매출액", "1,000", NAN, "-"))
    out = dart.extract_key_accounts(df, 2026, code)
    assert out["accounts"]["revenue"]["value"] == 1000.0 and out["period"] == period


@pytest.mark.unit
def test_empty_or_nan_amounts_are_left_out_not_filled_with_zero():
    df = _rows(
        ("IS", "ifrs-full_Revenue", "매출액", "", "", "-"),
        ("IS", "ifrs-full_ProfitLoss", "순이익", NAN, NAN, "-"),
        ("IS", "dart_OperatingIncomeLoss", "영업이익", "-", "-", "-"),
    )
    assert dart.extract_key_accounts(df, 2026, "11012")["accounts"] == {}


@pytest.mark.unit
def test_segment_detail_rows_do_not_replace_the_main_statement_row():
    df = _rows(
        ("IS", "ifrs-full_Revenue", "매출액", "50", "50", "부문A"),
        ("IS", "ifrs-full_Revenue", "매출액", "100", "100", "-"),
    )
    assert dart.extract_key_accounts(df, 2026, "11012")["accounts"]["revenue"]["value"] == 100.0


@pytest.mark.unit
def test_dataframe_without_account_id_yields_no_accounts():
    df = pd.DataFrame({"sj_div": ["IS"], "account_nm": ["매출액"], "thstrm_amount": ["1"]})
    assert dart.extract_key_accounts(df, 2026, "11012")["accounts"] == {}
    assert dart.extract_key_accounts(None, 2026, "11012")["accounts"] == {}


@pytest.mark.unit
def test_get_financial_accounts_returns_json_text():
    import json

    with patch.object(dart, "_dart", return_value=MagicMock()), \
         patch.object(dart, "_latest_finstate", return_value=(2026, "11012", _doosan_like())):
        out = dart.get_financial_accounts("034020", "2026-11-05")
    data = json.loads(out)
    assert data["accounts"]["revenue"]["value"] == 8_985_938.0 and data["year"] == 2026


@pytest.mark.unit
def test_get_financial_accounts_failures_are_readable_text_not_json():
    with patch.object(dart, "_dart", return_value=MagicMock()), \
         patch.object(dart, "_latest_finstate", return_value=(None, None, None)):
        assert dart.get_financial_accounts("034020", "2026-11-05") == "조회된 재무제표가 없습니다."
    dart._reset_for_tests()
    import os
    with patch.dict(os.environ, {"DART_API_KEY": ""}):
        assert dart.get_financial_accounts("034020", "2026-11-05").startswith("[DART 조회 실패")


# ---- 실호출(integration): 업종이 다른 회사 3곳에서 핵심 계정이 표준 계정 ID 로 식별되는지 ----

@pytest.mark.integration
@pytest.mark.parametrize("ticker", ["005930", "034020", "001210"])   # 삼성전자·두산에너빌리티·금호전기
def test_live_key_accounts_are_identified_by_standard_account_id(ticker, dart_api_key):
    import json

    data = json.loads(dart.get_financial_accounts(ticker, datetime.now().strftime("%Y-%m-%d")))
    accounts = data["accounts"]
    for key in ("revenue", "operating_income", "net_income", "cfo", "cfi", "cff", "cash_begin", "cash_end"):
        assert key in accounts, f"{ticker}: {key} 계정을 표준 계정 ID 로 찾지 못함 ({sorted(accounts)})"
    assert data["basis"] == "연결" and data["unit"] == "원"
    # 현금 브리지가 맞아떨어지는지 (환율·기타 차이는 기말 현금의 몇 % 이내)
    other = accounts["cash_end"]["value"] - sum(accounts[k]["value"] for k in ("cash_begin", "cfo", "cfi", "cff"))
    assert abs(other) <= abs(accounts["cash_end"]["value"]) * 0.2


# ---- #154: 프롬프트용 표 — 손익은 누적 열을 보이고 기간을 명시한다 ----

def _statement(*rows, extra=None):
    """(sj_div, account_id, account_nm, 당기, 누적, 전년동기누적) → ``finstate_all`` 형태."""
    df = pd.DataFrame([
        {"sj_div": sj, "account_id": aid, "account_nm": nm, "thstrm_amount": cur,
         "thstrm_add_amount": add, "frmtrm_add_amount": prev,
         "frmtrm_amount": NAN, "bfefrmtrm_amount": NAN}
        for sj, aid, nm, cur, add, prev in rows
    ])
    return df


def _table_row(text, name):
    return next(line for line in text.splitlines() if line.startswith(f"| {name}"))


@pytest.mark.unit
def test_half_year_income_table_shows_quarter_cumulative_and_prior_year_columns():
    df = _statement(
        ("IS", "ifrs-full_Revenue", "매출액", "4,724,808", "8,985,938", "8,317,595"),
        ("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", "-886,652", NAN, NAN),
    )
    out = dart._format_statement(df, "IS", "11012")
    assert "당기(분기 3개월)" in out and "누적" in out and "전년 동기 누적" in out
    row = _table_row(out, "매출액")
    assert "4,724,808" in row and "8,985,938" in row and "8,317,595" in row
    assert "반기보고서" in out and "현금흐름표" in out   # 어떤 열을 현금흐름표와 비교할지 안내


@pytest.mark.unit
def test_annual_income_table_keeps_current_prior_columns_and_says_it_is_cumulative():
    df = pd.DataFrame([{
        "sj_div": "IS", "account_id": "ifrs-full_Revenue", "account_nm": "매출액",
        "thstrm_amount": "300", "frmtrm_amount": "280", "bfefrmtrm_amount": "250",
        "thstrm_add_amount": NAN,
    }])
    out = dart._format_statement(df, "IS", "11011")
    assert "전전기" in out and "누적" not in out.split("\n\n")[1]   # 표에는 누적 열 없음
    assert "사업보고서" in out and "연초부터" in out


@pytest.mark.unit
def test_cash_flow_table_note_says_current_is_cumulative():
    df = _statement(("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동", "-5", NAN, NAN))
    assert "누적" in dart._format_statement(df, "CF", "11012").split("\n\n")[0]


@pytest.mark.unit
def test_key_accounts_come_first_even_when_the_response_lists_them_last():
    filler = [("IS", f"x_{i}", f"기타{i}", "1", "1", "1") for i in range(40)]
    key = [
        ("IS", "ifrs-full_Revenue", "매출액", "5", "9", "8"),
        ("IS", "dart_OperatingIncomeLoss", "영업이익", "3", "5", "4"),
        ("IS", "ifrs-full_ProfitLoss", "반기순이익", "2", "2", "1"),
    ]
    out = dart._format_statement(_statement(*filler, *key), "IS", "11012")
    body = [ln for ln in out.splitlines() if ln.startswith("|")][2:]   # 머리글·구분선 제외
    assert len(body) == dart._STATEMENT_ROWS
    assert [ln.split("|")[1].strip() for ln in body[:3]] == ["매출액", "영업이익", "반기순이익"]


@pytest.mark.unit
def test_cash_flow_key_accounts_are_also_ordered_first():
    filler = [("CF", f"x_{i}", f"기타{i}", "1", NAN, NAN) for i in range(40)]
    key = [("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동", "-5", NAN, NAN)]
    out = dart._format_statement(_statement(*filler, *key), "CF", "11012")
    assert [ln for ln in out.splitlines() if ln.startswith("|")][2].split("|")[1].strip() == "영업활동"


@pytest.mark.unit
def test_amounts_have_thousand_separators_and_missing_values_are_dashes_not_nan():
    df = _statement(("IS", "ifrs-full_Revenue", "매출액", "51349000000", "8985938000000", NAN))
    out = dart._format_statement(df, "IS", "11012")
    assert "51,349,000,000" in out and "8,985,938,000,000" in out
    assert "nan" not in out and "e+" not in out
    assert _table_row(out, "매출액").split("|")[-2].strip() == "-"   # 전년 동기 누적 없음


@pytest.mark.unit
def test_income_statement_prefers_is_over_cis_when_both_exist():
    """IS·CIS 가 따로 있는 회사의 CIS 는 기타포괄손익뿐이라 매출·영업이익이 없다."""
    df = pd.concat([
        _statement(("IS", "ifrs-full_Revenue", "매출액", "4", "9", "8")),
        _statement(("CIS", "ifrs-full_OtherComprehensiveIncome", "기타포괄손익", "1", "1", "1")),
    ], ignore_index=True)
    fake = MagicMock()
    fake.finstate_all.return_value = df
    with patch.object(dart, "_resolve_opendartreader_class", return_value=lambda _k: fake):
        out = dart.get_income_statement("034020", freq="quarterly", curr_date="2026-11-03")
    assert "매출액" in out and "기타포괄손익" not in out


@pytest.mark.unit
def test_income_statement_uses_cis_when_company_has_no_is():
    df = _statement(("CIS", "ifrs-full_Revenue", "수익", "4", "9", "8"))
    fake = MagicMock()
    fake.finstate_all.return_value = df
    with patch.object(dart, "_resolve_opendartreader_class", return_value=lambda _k: fake):
        out = dart.get_income_statement("001210", freq="quarterly", curr_date="2026-11-03")
    assert "수익" in out and "누적" in out


@pytest.mark.unit
def test_prompt_table_and_chart_data_agree_on_the_cumulative_revenue():
    """프롬프트 표의 '누적' 값 = 차트가 쓰는 값 — 같은 기준."""
    df = _statement(("IS", "ifrs-full_Revenue", "매출액", "4,724,808", "8,985,938", "8,317,595"))
    assert "8,985,938" in _table_row(dart._format_statement(df, "IS", "11012"), "매출액")
    assert dart.extract_key_accounts(df, 2026, "11012")["accounts"]["revenue"]["value"] == 8_985_938.0


@pytest.mark.integration
@pytest.mark.parametrize("ticker", ["034020", "001210"])   # 두산에너빌리티·금호전기
def test_live_income_table_shows_cumulative_and_key_accounts_first(ticker, dart_api_key):
    out = dart.get_income_statement(ticker, "quarterly", datetime.now().strftime("%Y-%m-%d"))
    assert "누적" in out and "전년 동기 누적" in out
    first_rows = [ln.split("|")[1].strip() for ln in out.splitlines() if ln.startswith("|")][2:5]
    assert any(name.startswith(("매출", "수익")) for name in first_rows), first_rows


# ---- #149 유동성: 재무상태표 단기 차입·현금 계정은 회사마다 표준 ID 가 다르다 ----

def _bs(*rows):
    """(account_id, account_nm, 당기말 잔액) → BS 행만 가진 DataFrame."""
    return pd.DataFrame([
        {"sj_div": "BS", "account_id": aid, "account_nm": nm, "thstrm_amount": amt,
         "thstrm_add_amount": NAN, "account_detail": "-"}
        for aid, nm, amt in rows
    ])


@pytest.mark.unit
def test_balance_sheet_cash_and_short_debt_use_ids_of_a_manufacturer_like_doosan():
    out = dart.extract_key_accounts(_bs(
        ("ifrs-full_CashAndCashEquivalents", "현금및현금성자산", "2,541,888"),
        ("ifrs-full_ShorttermDepositsNotClassifiedAsCashEquivalents", "단기금융상품", "276,246"),
        ("ifrs-full_ShorttermBorrowings", "단기차입금", "2,916,241"),
        ("ifrs-full_CurrentPortionOfLongtermBorrowings", "유동성장기부채", "1,578,345"),
    ), 2026, "11012")["accounts"]
    assert out["cash"]["value"] == 2_541_888 and out["short_term_deposits"]["value"] == 276_246
    assert out["short_borrowings"]["value"] == 2_916_241
    assert out["current_long_term_debt"]["value"] == 1_578_345
    assert "current_convertible_bonds" not in out      # 없는 계정은 0 으로 채우지 않는다


@pytest.mark.unit
def test_short_borrowings_found_by_the_samsung_style_id():
    out = dart.extract_key_accounts(_bs(
        ("dart_CurrentLoansReceived", "단기차입금", "13,710,121"),
    ), 2026, "11012")["accounts"]
    assert out["short_borrowings"]["value"] == 13_710_121


@pytest.mark.unit
def test_convertible_bond_current_portion_is_a_separate_account():
    out = dart.extract_key_accounts(_bs(
        ("ifrs-full_ShorttermBorrowings", "유동 차입금(사채 포함)", "1,357,209"),
        ("dart_CurrentPortionOfConvertibleBonds", "유동성전환사채", "2,948,032"),
    ), 2026, "11012")["accounts"]
    assert out["short_borrowings"]["value"] == 1_357_209
    assert out["current_convertible_bonds"]["value"] == 2_948_032


@pytest.mark.unit
def test_same_key_with_two_standard_ids_takes_the_first_not_the_sum():
    out = dart.extract_key_accounts(_bs(
        ("dart_CurrentLoansReceived", "단기차입금(다른 ID)", "999"),
        ("ifrs-full_ShorttermBorrowings", "단기차입금", "100"),
    ), 2026, "11012")["accounts"]
    assert out["short_borrowings"]["value"] == 100


@pytest.mark.unit
def test_balance_sheet_key_accounts_come_first_in_the_prompt_table():
    filler = [(f"x_{i}", f"기타{i}", "1") for i in range(40)]
    key = [("ifrs-full_CashAndCashEquivalents", "현금및현금성자산", "5")]
    out = dart._format_statement(_bs(*filler, *key), "BS", "11012")
    assert [ln for ln in out.splitlines() if ln.startswith("|")][2].split("|")[1].strip() == "현금및현금성자산"


@pytest.mark.integration
@pytest.mark.parametrize("ticker", ["005930", "034020", "001210"])
def test_live_balance_sheet_cash_and_short_debt_are_identified(ticker, dart_api_key):
    import json

    accounts = json.loads(dart.get_financial_accounts(ticker, datetime.now().strftime("%Y-%m-%d")))["accounts"]
    assert accounts["cash"]["value"] > 0
    debt = [k for k in ("short_borrowings", "current_long_term_debt", "current_convertible_bonds") if k in accounts]
    assert debt, f"{ticker}: 단기 차입 계정을 표준 계정 ID 로 찾지 못함 ({sorted(accounts)})"
