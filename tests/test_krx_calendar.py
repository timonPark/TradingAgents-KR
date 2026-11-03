"""Task 8 (#74): KRX 캘린더 유틸 유닛 테스트.

``exchange_calendars`` 는 순수 Python 이라 네트워크 호출 없음.
"""

from __future__ import annotations

import pytest

from tradingagents.dataflows import krx_calendar as cal

# ---------- is_trading_day ----------

@pytest.mark.unit
@pytest.mark.parametrize("date,expected", [
    ("2026-11-03", True),   # 월요일, 평일
    ("2026-11-02", True),   # 월요일
    ("2026-11-06", True),   # 금요일
    ("2026-11-01", False),  # 일요일
    ("2026-11-07", False),  # 토요일
])
def test_is_trading_day_weekdays_vs_weekends(date, expected):
    assert cal.is_trading_day(date) is expected


@pytest.mark.unit
@pytest.mark.parametrize("date", [
    "2026-10-03",   # 개천절
    "2026-10-09",   # 한글날
    "2026-08-15",   # 광복절 (토요일이지만 공휴일)
    "2026-01-01",   # 신정
    "2026-05-05",   # 어린이날
])
def test_is_trading_day_rejects_korean_holidays(date):
    assert cal.is_trading_day(date) is False


@pytest.mark.unit
def test_is_trading_day_rejects_bad_format():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        cal.is_trading_day("2026/11/03")


# ---------- previous / next trading day ----------

@pytest.mark.unit
def test_previous_trading_day_skips_weekend():
    """월요일의 전 영업일은 금요일 (주말 제외)."""
    assert cal.previous_trading_day("2026-11-02") == "2026-10-30"


@pytest.mark.unit
def test_previous_trading_day_skips_holiday():
    """2026-10-05 (추석 대체공휴일) 의 전 영업일은 10/02 (연휴 전 금요일)."""
    assert cal.previous_trading_day("2026-10-05") == "2026-10-02"


@pytest.mark.unit
def test_next_trading_day_skips_weekend():
    assert cal.next_trading_day("2026-10-30") == "2026-11-02"


@pytest.mark.unit
def test_next_trading_day_skips_holiday():
    """추석 연휴 (10/5-10/8) 끝의 다음 영업일은 10/12 (한글날 다음 월요일)."""
    assert cal.next_trading_day("2026-10-02") == "2026-10-06"


# ---------- range + filter ----------

@pytest.mark.unit
def test_trading_days_in_range_excludes_weekends_and_holidays():
    days = cal.trading_days_in_range("2026-10-01", "2026-10-15")
    assert "2026-10-03" not in days  # 개천절
    assert "2026-10-05" not in days  # 추석
    assert "2026-10-09" not in days  # 한글날
    assert "2026-10-10" not in days  # 토요일
    assert "2026-10-02" in days  # 금요일 (영업일)
    assert "2026-10-12" in days  # 월요일 (영업일)


@pytest.mark.unit
def test_trading_days_in_range_covers_bounds_inclusively():
    days = cal.trading_days_in_range("2026-11-02", "2026-11-03")
    assert days == ["2026-11-02", "2026-11-03"]


@pytest.mark.unit
def test_filter_to_trading_days_steps_by_n():
    """every_n_days=5 → 매 5번째 영업일."""
    full = cal.trading_days_in_range("2026-10-01", "2026-11-15")
    every5 = cal.filter_to_trading_days("2026-10-01", "2026-11-15", 5)
    assert every5 == full[::5]


@pytest.mark.unit
def test_filter_to_trading_days_rejects_zero_step():
    with pytest.raises(ValueError, match="1 이상"):
        cal.filter_to_trading_days("2026-10-01", "2026-11-15", 0)


# ---------- current_trading_date ----------

@pytest.mark.unit
def test_current_trading_date_returns_valid_trading_day():
    """반환값은 KRX 영업일이어야 함."""
    today = cal.current_trading_date()
    assert cal.is_trading_day(today)


# ---------- Pandas DatetimeIndex ----------

@pytest.mark.unit
def test_to_pandas_index_matches_sessions():
    import pandas as pd
    idx = cal.to_pandas_index("2026-10-01", "2026-10-15")
    assert isinstance(idx, pd.DatetimeIndex)
    # 영업일 수만큼 레코드
    assert len(idx) == len(cal.trading_days_in_range("2026-10-01", "2026-10-15"))
