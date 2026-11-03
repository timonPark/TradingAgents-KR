"""KRX (한국거래소) 영업일 캘린더 유틸.

Task 8 (#74): 미국 NYSE 캘린더 가정을 한국거래소 영업일 기반으로 교체. 백테스트
그리드와 날짜 처리 로직이 주말/공휴일 (설날/추석/광복절/개천절 등) 을 자동 제외
하도록.

### 라이브러리
``exchange_calendars`` 의 ``XKRX`` 캘린더를 사용. 순수 Python, API 키 불필요,
``Asia/Seoul`` 타임존.

### 공개 함수
- ``is_trading_day(date_str)`` — 지정 날짜가 KRX 영업일인지
- ``previous_trading_day(date_str)`` — 지정 날짜 직전 영업일 (당일이 영업일이면 당일 반환 안 함)
- ``next_trading_day(date_str)`` — 지정 날짜 직후 영업일
- ``trading_days_in_range(start, end)`` — [start, end] 범위 내 모든 영업일
- ``current_trading_date()`` — KST 기준 오늘 또는 가장 최근 영업일
"""

from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache

import exchange_calendars as xcals
import pandas as pd
import pytz

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")
_CAL_NAME = "XKRX"


@lru_cache(maxsize=1)
def _calendar():
    """``XKRX`` 캘린더 lazy singleton. exchange_calendars 초기화 비용을 1회로 제한."""
    return xcals.get_calendar(_CAL_NAME)


def _parse(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"KRX 캘린더 함수에는 YYYY-MM-DD 포맷 날짜가 필요합니다: got {date_str!r}"
        ) from exc


def is_trading_day(date_str: str) -> bool:
    """``date_str`` 이 KRX 영업일인지 (주말/공휴일 자동 제외)."""
    _parse(date_str)  # 포맷 검증
    return bool(_calendar().is_session(date_str))


def previous_trading_day(date_str: str) -> str:
    """``date_str`` 바로 이전 영업일. 당일 포함 안 함.

    예: 2026-11-02 (월) 이전 영업일 → 2026-10-30 (금, 주말 제외)
    """
    _parse(date_str)
    cal = _calendar()
    # previous_close 는 세션 종료 datetime 을 반환. date 만 추출.
    prev_dt = cal.previous_close(date_str)
    return prev_dt.strftime("%Y-%m-%d")


def next_trading_day(date_str: str) -> str:
    """``date_str`` 바로 다음 영업일. 당일 포함 안 함."""
    _parse(date_str)
    cal = _calendar()
    nxt_dt = cal.next_open(date_str)
    return nxt_dt.strftime("%Y-%m-%d")


def trading_days_in_range(start_date: str, end_date: str) -> list[str]:
    """``[start_date, end_date]`` 범위 내 모든 KRX 영업일 (오름차순).

    범위 끝점이 영업일이면 포함. 주말/공휴일은 자동 제외.
    """
    _parse(start_date)
    _parse(end_date)
    sessions = _calendar().sessions_in_range(start_date, end_date)
    return [str(s)[:10] for s in sessions]


def current_trading_date() -> str:
    """KST 기준 "오늘" 의 KRX 영업일. 오늘이 영업일 아니면 가장 최근 영업일.

    시스템 로컬 타임존이 UTC 나 다른 시간대라도 KST 기준으로 결정 (한국 증시 정규
    세션은 09:00-15:30 KST — 분석 그래프가 "오늘" 을 참조할 때 KRX 세션 기준이어야 함).
    """
    today_kst = datetime.now(KST).date()
    today_str = today_kst.strftime("%Y-%m-%d")
    if is_trading_day(today_str):
        return today_str
    return previous_trading_day(today_str)


def filter_to_trading_days(
    start_date: str,
    end_date: str,
    every_n_days: int = 1,
) -> list[str]:
    """``[start, end]`` 영업일 중 ``every_n_days`` 간격으로 샘플링한 리스트.

    ``every_n_days=1`` → 모든 영업일.
    ``every_n_days=5`` → 매주 월요일 (또는 연휴 뒤 첫 영업일) 샘플.
    """
    if every_n_days < 1:
        raise ValueError("every_n_days 는 1 이상이어야 합니다")
    days = trading_days_in_range(start_date, end_date)
    return days[::every_n_days]


def to_pandas_index(start_date: str, end_date: str) -> pd.DatetimeIndex:
    """pykrx OHLCV 와 join 하기 쉽도록 영업일을 ``pd.DatetimeIndex`` 로 반환."""
    sessions = _calendar().sessions_in_range(start_date, end_date)
    return pd.DatetimeIndex([pd.Timestamp(str(s)[:10]) for s in sessions])
