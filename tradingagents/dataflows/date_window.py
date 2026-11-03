"""Point-in-time rules shared by every dated path: data is served as of the run's date.

- ``as_of`` / ``as_of_window`` clamp a date or window the model asks for to the
  trade date, so no tool reaches a vendor with a later one, and always hand it
  over as ``YYYY-MM-DD``: vendors compare dates as text.
- ``in_window`` trims dated items (news) to the analysis window: timestamps
  normalized to UTC, the upper bound exclusive at midnight after ``end``, and an
  undated item kept only when the window reaches the present, since a backtest
  cannot prove it is not from the future (#1126, #1220).
- ``coverage_gap`` reports a window a feed cannot reach as unavailable, not empty.
- ``get_current_date`` returns today's KST calendar date (not KRX trading day;
  for the latest KRX session, use ``krx_calendar.current_trading_date``).

Task 8 (#74): ``get_current_date`` 가 KST 타임존 기준으로 동작. 레거시
``withhold_live_profile`` / ``withhold_undisclosed_trades`` /
``withhold_undated_statements`` 는 Yahoo/AV/SEC EDGAR 전용 dead code 라
Task 7 vendor 삭제 이후 호출 사이트가 사라져 제거됨.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytz

_KST = pytz.timezone("Asia/Seoul")


def to_utc(dt: datetime) -> datetime:
    """Normalize a datetime to UTC-aware; a naive value is assumed to be UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def in_window(pub_dt: datetime | None, start_dt: datetime, end_dt: datetime) -> bool:
    """Whether an item belongs in the half-open window ``[start, end + 1 day)``.

    ``pub_dt`` None means undated: kept only when the window reaches the present.
    """
    end = to_utc(end_dt)
    if pub_dt is not None:
        return to_utc(start_dt) <= to_utc(pub_dt) < end + timedelta(days=1)
    return end >= datetime.now(UTC) - timedelta(days=1)


def get_current_date() -> str:
    """오늘 날짜 (KST 기준), ``YYYY-MM-DD``.

    Task 8 (#74): 시스템 로컬 타임존이 UTC 등 다른 시간대라도 KST (``Asia/Seoul``)
    기준으로 결정. KRX 세션 (09:00-15:30 KST) 과 "오늘" 개념이 일치하도록.
    """
    return datetime.now(_KST).strftime("%Y-%m-%d")


def is_historical(run_date) -> bool:
    """Whether a run is dated before today, so live-only data would come from after it."""
    return bool(run_date) and str(run_date) < get_current_date()


def coverage_gap(
    dates, start_date: str, end_date: str, source: str, subject: str
) -> str | None:
    """Placeholder for a window a feed did not fully observe, else None.

    Yahoo news and the Reddit and StockTwits feeds return their latest items
    whatever window is asked for, so "none found" over a window they never
    observed would claim an absence nobody saw. A window is observed when
    coverage reaches its first day and it ends by today; an empty result is then
    a real absence and this returns None.

    ``dates`` are the returned items' timestamps, plus the lookback start for a
    feed with a fixed lookback. The oldest one bounds coverage only for a feed
    returned newest-first and unbroken in time; a merged or relevance-ranked
    result passes no dates, leaving only the present as the bound.
    """
    now = datetime.now(UTC)
    oldest = min((to_utc(d) for d in dates if d is not None), default=now)
    if datetime.strptime(end_date, "%Y-%m-%d").date() > now.date():
        reason = "the window extends past today"
    elif oldest.date() > datetime.strptime(start_date, "%Y-%m-%d").date():
        reason = "it only serves recent items"
    else:
        return None
    return f"<{source} unavailable for {start_date}..{end_date}: {reason}, so this is not an absence of {subject}>"


def _parse(date: str | None) -> datetime | None:
    try:
        return datetime.strptime(date, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def as_of(requested: str | None, trade_date: str) -> str | None:
    """The date a tool serves: the model's date, but never later than the run's.

    A model can omit the date or pass today's instead of the analysis date, which
    would walk past every point-in-time guard behind the tool. A date is served in
    its canonical form: "2026-7-3" compares as later than "2026-07-23". An empty
    ``trade_date`` (a direct call outside a graph run) passes the request through.
    """
    parsed = _parse(requested)
    if not trade_date:
        return requested if parsed is None else f"{parsed:%Y-%m-%d}"
    return f"{parsed:%Y-%m-%d}" if parsed is not None and parsed <= _parse(trade_date) else trade_date


def as_of_window(start_date: str, end_date: str, trade_date: str) -> tuple[str, str]:
    """``[start, end]`` with its end clamped to the run date.

    A window wholly after the run date keeps its length and moves back to end there.
    An unreadable end reads as the run date, but no window can be guessed from an
    unreadable start or from a start after the end, so those raise ValueError for
    the caller to send back (#1476).
    """
    start, old_end = _parse(start_date), _parse(end_date)
    if start is None:
        raise ValueError(f"start_date {start_date!r} is not a date; give it as YYYY-MM-DD")
    if old_end is not None and start > old_end:
        raise ValueError(f"start_date {start_date} is after end_date {end_date}; give the earlier date first")
    end = as_of(end_date, trade_date)
    end_dt = _parse(end)
    if end_dt is None or end_dt == old_end or start <= end_dt:
        return f"{start:%Y-%m-%d}", end
    span = (old_end - start) if old_end is not None and old_end >= start else timedelta(0)
    return f"{end_dt - span:%Y-%m-%d}", end


# Task 8 (#74): withhold_live_profile / withhold_undisclosed_trades /
# withhold_undated_statements 함수는 Yahoo / Alpha Vantage / SEC EDGAR 전용
# dead code 라 Task 7 vendor 삭제 이후 호출 사이트가 사라져 제거됨.
# KRX 전용 vendor (DART, pykrx, 네이버뉴스, ECOS) 는 공시일 또는 영업일 기반
# 자체 point-in-time 로직을 가지므로 공통 withhold_ 추상화 불필요.
