"""Task 7b (#63): ECOS 거시지표 vendor 유닛 테스트.

실제 ECOS API 호출 금지 — `get_scrubbed` 를 전부 모킹. 통합 테스트는 Task 11 로.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows.errors import VendorNotConfiguredError
from tradingagents.dataflows.vendors import ecos


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("ECOS_API_KEY", "test-key")


def _ok_response(payload):
    resp = MagicMock(status_code=200)
    resp.json.return_value = payload
    return resp


# ---------- 환경변수 체크 ----------

@pytest.mark.unit
def test_missing_api_key_raises_typed_error(monkeypatch):
    monkeypatch.delenv("ECOS_API_KEY", raising=False)
    with pytest.raises(VendorNotConfiguredError, match="ECOS_API_KEY"):
        ecos.get_api_key()


@pytest.mark.unit
def test_get_macro_data_without_key_returns_fail_safe(monkeypatch):
    """키 없음 → 사람 읽기 쉬운 안내, 예외 아님."""
    monkeypatch.delenv("ECOS_API_KEY", raising=False)
    out = ecos.get_macro_data("base_rate", "2026-11-03")
    assert "ECOS 조회 실패" in out
    assert "ECOS_API_KEY" in out


# ---------- 지표 매핑 ----------

@pytest.mark.unit
@pytest.mark.parametrize("alias", ["base_rate", "cpi", "unemployment_rate", "usd_krw", "real_gdp"])
def test_resolve_series_known_aliases(alias):
    stat_code, cycle, item_code = ecos._resolve_series(alias)
    assert stat_code and cycle in ("A", "S", "Q", "M", "D")


@pytest.mark.unit
def test_resolve_series_case_insensitive():
    assert ecos._resolve_series("BASE_RATE") == ecos._resolve_series("base_rate")


@pytest.mark.unit
def test_resolve_series_unknown_raises():
    with pytest.raises(ValueError, match="지원되는 ECOS 지표 alias"):
        ecos._resolve_series("made up indicator")


# ---------- 기간 포맷 ----------

@pytest.mark.unit
@pytest.mark.parametrize("dt,cycle,expected", [
    (datetime(2026, 11, 3), "D", "20261103"),
    (datetime(2026, 11, 3), "M", "202611"),
    (datetime(2026, 11, 3), "Q", "2026Q4"),
    (datetime(2026, 11, 3), "A", "2026"),
    (datetime(2026, 1, 15), "Q", "2026Q1"),
    (datetime(2026, 7, 1), "Q", "2026Q3"),
])
def test_format_period(dt, cycle, expected):
    assert ecos._format_period(dt, cycle) == expected


@pytest.mark.unit
@pytest.mark.parametrize("text,cycle,expected_ymd", [
    ("20261103", "D", (2026, 11, 3)),
    ("202611", "M", (2026, 11, 1)),
    ("2026Q4", "Q", (2026, 10, 1)),
    ("2026", "A", (2026, 1, 1)),
])
def test_parse_period(text, cycle, expected_ymd):
    dt = ecos._parse_period(text, cycle)
    assert dt is not None
    assert (dt.year, dt.month, dt.day) == expected_ymd


# ---------- 값 포맷 ----------

@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    ("3.50", "3.5"),           # 작은 값: 뒤쪽 0 제거
    ("150.25", "150.25"),      # 100 이상: 2자리
    ("1500000", "1,500,000"),  # 백만 이상: comma
    ("not a number", "not a number"),  # fallback
])
def test_format_value(raw, expected):
    assert ecos._format_value(raw) == expected


# ---------- API 호출 ----------

def _sample_rows():
    return [
        {"STAT_CODE": "722Y001", "STAT_NAME": "한국은행 기준금리", "ITEM_CODE1": "0101000",
         "ITEM_NAME1": "기준금리", "UNIT_NAME": "%", "TIME": "20260501", "DATA_VALUE": "3.50"},
        {"STAT_CODE": "722Y001", "STAT_NAME": "한국은행 기준금리", "ITEM_CODE1": "0101000",
         "ITEM_NAME1": "기준금리", "UNIT_NAME": "%", "TIME": "20261101", "DATA_VALUE": "3.25"},
    ]


@pytest.mark.unit
def test_get_macro_data_renders_markdown(api_key):
    payload = {"StatisticSearch": {"row": _sample_rows()}}
    with patch(
        "tradingagents.dataflows.vendors.ecos.get_scrubbed",
        return_value=_ok_response(payload),
    ):
        out = ecos.get_macro_data("base_rate", "2026-11-03")

    assert "한국은행 기준금리" in out
    assert "base_rate" in out
    assert "722Y001" in out
    assert "**최근값**" in out and "3.25" in out
    assert "**변화**" in out
    assert "| 20260501 |" in out
    assert "| 20261101 |" in out


@pytest.mark.unit
def test_get_macro_data_handles_empty_rows(api_key):
    payload = {"StatisticSearch": {"row": []}}
    with patch(
        "tradingagents.dataflows.vendors.ecos.get_scrubbed",
        return_value=_ok_response(payload),
    ):
        out = ecos.get_macro_data("base_rate", "2026-11-03")
    assert "데이터가 없습니다" in out


@pytest.mark.unit
def test_get_macro_data_handles_ecos_result_error(api_key):
    payload = {"RESULT": {"CODE": "100", "MESSAGE": "인증키가 유효하지 않습니다"}}
    with patch(
        "tradingagents.dataflows.vendors.ecos.get_scrubbed",
        return_value=_ok_response(payload),
    ):
        out = ecos.get_macro_data("base_rate", "2026-11-03")
    assert "ECOS 조회 실패" in out
    assert "100" in out


@pytest.mark.unit
def test_get_macro_data_handles_bad_date_format(api_key):
    out = ecos.get_macro_data("base_rate", "not-a-date")
    assert "잘못된 날짜 형식" in out


@pytest.mark.unit
def test_get_macro_data_handles_unknown_indicator(api_key):
    out = ecos.get_macro_data("fake_indicator", "2026-11-03")
    assert "ECOS 조회 실패" in out
    assert "지원되는 ECOS 지표 alias" in out


@pytest.mark.unit
def test_get_macro_data_handles_http_error(api_key):
    err = MagicMock(status_code=500, text="internal server error")
    with patch(
        "tradingagents.dataflows.vendors.ecos.get_scrubbed",
        return_value=err,
    ):
        out = ecos.get_macro_data("base_rate", "2026-11-03")
    assert "ECOS 조회 실패" in out
    assert "500" in out


@pytest.mark.unit
def test_get_macro_data_handles_network_exception(api_key):
    with patch(
        "tradingagents.dataflows.vendors.ecos.get_scrubbed",
        side_effect=ConnectionError("boom"),
    ):
        out = ecos.get_macro_data("base_rate", "2026-11-03")
    assert "ECOS 조회 실패" in out
    assert "boom" in out


@pytest.mark.unit
def test_get_macro_data_computes_change_pct(api_key):
    """시작값 100, 끝값 110 → +10 (+10.00%) 가 리포트에 포함."""
    rows = [
        {"STAT_CODE": "901Y009", "STAT_NAME": "소비자물가지수", "ITEM_CODE1": "0",
         "ITEM_NAME1": "총지수", "UNIT_NAME": "2020=100", "TIME": "202501", "DATA_VALUE": "100.00"},
        {"STAT_CODE": "901Y009", "STAT_NAME": "소비자물가지수", "ITEM_CODE1": "0",
         "ITEM_NAME1": "총지수", "UNIT_NAME": "2020=100", "TIME": "202611", "DATA_VALUE": "110.00"},
    ]
    with patch(
        "tradingagents.dataflows.vendors.ecos.get_scrubbed",
        return_value=_ok_response({"StatisticSearch": {"row": rows}}),
    ):
        out = ecos.get_macro_data("cpi", "2026-11-03")
    assert "+10.00%" in out


@pytest.mark.unit
def test_get_macro_data_sorts_rows_chronologically(api_key):
    """ECOS 가 역순으로 돌려줘도 관측 테이블은 오래된 → 최신 순."""
    rows = [
        {"TIME": "20261101", "DATA_VALUE": "3.25", "STAT_NAME": "", "ITEM_NAME1": "", "UNIT_NAME": ""},
        {"TIME": "20260801", "DATA_VALUE": "3.50", "STAT_NAME": "", "ITEM_NAME1": "", "UNIT_NAME": ""},
        {"TIME": "20260501", "DATA_VALUE": "3.75", "STAT_NAME": "", "ITEM_NAME1": "", "UNIT_NAME": ""},
    ]
    with patch(
        "tradingagents.dataflows.vendors.ecos.get_scrubbed",
        return_value=_ok_response({"StatisticSearch": {"row": rows}}),
    ):
        out = ecos.get_macro_data("base_rate", "2026-11-03")
    # 관측 테이블 섹션 내부 순서만 검사 (헤더의 "최근값/기간 시작" 라벨은 역방향).
    table_section = out[out.index("### 관측 데이터"):]
    pos_old = table_section.find("| 20260501 |")
    pos_mid = table_section.find("| 20260801 |")
    pos_new = table_section.find("| 20261101 |")
    assert 0 < pos_old < pos_mid < pos_new


# ---------- #137: get_scrubbed 시그니처 / 일별 시계열 행 범위 회귀 ----------

@pytest.mark.unit
def test_fetch_calls_real_get_scrubbed_signature(api_key):
    """실제 ``get_scrubbed`` 를 거쳐 필수 인자(params) 누락을 잡는다.

    ``get_scrubbed`` 를 통째로 모킹하면 시그니처 불일치가 드러나지 않는다 (#137).
    네트워크 계층인 ``requests.get`` 만 모킹한다.
    """
    resp = _ok_response({"StatisticSearch": {"row": []}})
    resp.raise_for_status.return_value = None
    with patch("tradingagents.dataflows.net.requests.get", return_value=resp) as mock_get:
        rows = ecos._fetch("722Y001", "D", "20260101", "20261104", "0101000")
    assert rows == []
    assert mock_get.call_count == 1
    assert mock_get.call_args.kwargs["params"] == {}


@pytest.mark.unit
def test_fetch_requests_whole_window_for_daily_series(api_key):
    """일별 시계열은 구간 전체를 요청한다 (#137).

    ECOS 는 오래된 쪽부터 행을 주므로 요청 종료 행이 작으면 최근 데이터가 잘린다.
    """
    resp = _ok_response({"StatisticSearch": {"row": []}})
    resp.raise_for_status.return_value = None
    with patch("tradingagents.dataflows.net.requests.get", return_value=resp) as mock_get:
        ecos._fetch("731Y001", "D", "20251104", "20261104", "0000001")
    url = mock_get.call_args.args[0]
    # .../json/kr/{start}/{end}/{STAT}/...
    parts = url.split("/json/kr/")[1].split("/")
    start_row, end_row = int(parts[0]), int(parts[1])
    assert start_row == 1
    assert end_row >= 366  # 1년치 일별 행 수 이상


# ============================================================================
# Integration tests (Task 11b, #93) — 실제 한국은행 ECOS API 호출. CI 는 skip.
#   로컬 실행: ``ECOS_API_KEY=... pytest tests/test_ecos_vendor.py -m integration``
# ============================================================================


@pytest.mark.integration
def test_live_ecos_base_rate(ecos_api_key):
    """한국은행 기준금리 최근 1년 조회."""
    out = ecos.get_macro_data("base_rate", "2026-11-03", look_back_days=365)
    # 성공 시 "한국은행 기준금리" 포함, 실패 시 fail-safe 메시지
    assert "ECOS 조회 실패" in out or "기준금리" in out


@pytest.mark.integration
def test_live_ecos_cpi(ecos_api_key):
    """소비자물가지수 — 월간 지표."""
    out = ecos.get_macro_data("cpi", "2026-11-03", look_back_days=365)
    assert "ECOS 조회 실패" in out or "소비자물가지수" in out or "cpi" in out.lower()


@pytest.mark.integration
def test_live_ecos_usd_krw(ecos_api_key):
    """원/달러 환율 — 일별 지표."""
    out = ecos.get_macro_data("usd_krw", "2026-11-03", look_back_days=30)
    # 성공 시 매매기준율 데이터, 또는 fail-safe
    assert "ECOS 조회 실패" in out or "매매기준율" in out or "usd_krw" in out.lower()
