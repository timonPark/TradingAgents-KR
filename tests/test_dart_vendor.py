"""Task 5a (#47): DART vendor 유닛 테스트.

실제 OpenDartReader / Open DART API 는 호출하지 않고 전부 모킹. 통합 테스트
(실제 ``DART_API_KEY`` + 네트워크) 는 Task 11 로 분산.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows.vendors import dart


@pytest.fixture(autouse=True)
def _fresh_dart(monkeypatch):
    """각 테스트가 lazy singleton 영향을 받지 않도록 초기화 + 더미 API 키 세팅."""
    monkeypatch.setenv("DART_API_KEY", "test-key")
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
    with patch("opendartreader.OpenDartReader") as mock_cls:
        mock_cls.return_value = MagicMock()
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
    with patch("opendartreader.OpenDartReader", return_value=fake):
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
    with patch("opendartreader.OpenDartReader", return_value=fake):
        result = dart.get_fundamentals("005930", "2026-11-03")

    assert "조회된 공시가 없습니다" in result or "최근 재무제표: 조회된 공시가 없습니다" in result


@pytest.mark.unit
def test_get_fundamentals_absorbs_vendor_exceptions():
    """``company()`` 가 예외를 던지면 섹션 단위로 수용하고 분석가 run 은 유지."""
    fake = MagicMock()
    fake.company.side_effect = RuntimeError("boom")
    fake.finstate_all.return_value = _finstate_df()
    with patch("opendartreader.OpenDartReader", return_value=fake):
        result = dart.get_fundamentals("005930", "2026-11-03")

    assert "조회 실패" in result or "boom" in result
    assert "최근 재무제표" in result  # 재무 섹션은 계속 포함


@pytest.mark.unit
def test_get_balance_sheet_formats_bs_section():
    fake = MagicMock()
    fake.finstate_all.return_value = _finstate_df()
    with patch("opendartreader.OpenDartReader", return_value=fake):
        result = dart.get_balance_sheet("005930", freq="quarterly", curr_date="2026-11-03")

    assert "재무상태표" in result
    assert "자산총계" in result
    assert "부채총계" in result


@pytest.mark.unit
def test_get_cashflow_formats_cf_section():
    fake = MagicMock()
    fake.finstate_all.return_value = _finstate_df()
    with patch("opendartreader.OpenDartReader", return_value=fake):
        result = dart.get_cashflow("005930", freq="quarterly", curr_date="2026-11-03")

    assert "현금흐름표" in result
    assert "영업활동현금흐름" in result


@pytest.mark.unit
def test_get_income_statement_falls_back_to_is_when_cis_absent():
    """포괄손익(CIS) 섹션이 없으면 손익계산서(IS) 를 반환."""
    df = _finstate_df()  # has IS but no CIS
    fake = MagicMock()
    fake.finstate_all.return_value = df
    with patch("opendartreader.OpenDartReader", return_value=fake):
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
    with patch("opendartreader.OpenDartReader", return_value=fake):
        result = dart.get_insider_transactions("005930")

    assert "이재용" in result
    assert "홍라희" in result


@pytest.mark.unit
def test_get_insider_transactions_handles_empty():
    fake = MagicMock()
    fake.major_shareholders_exec.return_value = pd.DataFrame()
    with patch("opendartreader.OpenDartReader", return_value=fake):
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
    with patch("opendartreader.OpenDartReader", return_value=fake):
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
    with patch("opendartreader.OpenDartReader", return_value=fake):
        result = dart.get_convertible_bonds("005930")

    assert "전환사채" in result and "없습니다" in result


@pytest.mark.unit
def test_balance_sheet_and_cashflow_error_messages_when_no_data():
    fake = MagicMock()
    fake.finstate_all.return_value = pd.DataFrame()  # empty
    with patch("opendartreader.OpenDartReader", return_value=fake):
        bs = dart.get_balance_sheet("005930", freq="quarterly", curr_date="2026-11-03")
        cf = dart.get_cashflow("005930", freq="quarterly", curr_date="2026-11-03")

    assert "없습니다" in bs
    assert "없습니다" in cf
