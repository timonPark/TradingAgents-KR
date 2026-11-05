"""#139: 네이버 증권 투자자별 매매동향(폴백) 유닛 테스트. 실호출은 ``-m integration``."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors import naver_investor

GET = "tradingagents.dataflows.vendors.naver_investor.requests.get"


def _row(day, foreign, organ, individual, ratio="12.77%"):
    return {
        "itemCode": "001210", "bizdate": day,
        "foreignerPureBuyQuant": foreign, "organPureBuyQuant": organ,
        "individualPureBuyQuant": individual, "foreignerHoldRatio": ratio,
        "closePrice": "6,990",
    }


def _resp(payload, status=200):
    resp = MagicMock(status_code=status)
    resp.json.return_value = payload
    return resp


_TREND = [  # 최신순 (실제 응답과 동일)
    _row("20261103", "+9,822", "0", "-10,122"),
    _row("20261102", "-21,196", "-6", "+20,695"),
    _row("20261030", "-1,000", "+500", "+500"),
    _row("20261029", "+2,000", "-100", "-1,900"),
    _row("20261028", "+300", "0", "-300"),
    _row("20261027", "+50", "0", "-50"),
]


@pytest.mark.unit
def test_formats_recent_days_with_sums_and_unit_note():
    with patch(GET, return_value=_resp(_TREND)):
        out = naver_investor.get_investor_flow("001210", "2026-11-03", look_back_days=3)
    assert "최근 3 거래일" in out
    assert "단위: 주" in out
    assert "| 2026-11-03 | +9,822 | +0 | -10,122 |" in out
    assert "2026-10-30" in out and "2026-10-29" not in out
    assert "**-12,374**" in out  # 외국인 3일 합: 9,822 - 21,196 - 1,000
    assert "금액(원)이 아니라 수량(주)" in out


@pytest.mark.unit
def test_excludes_rows_after_trade_date_to_avoid_lookahead():
    with patch(GET, return_value=_resp(_TREND)):
        out = naver_investor.get_investor_flow("001210", "2026-10-30", look_back_days=5)
    assert "2026-11-03" not in out and "2026-11-02" not in out
    assert "2026-10-30" in out


@pytest.mark.unit
def test_trade_date_older_than_available_window_raises():
    with patch(GET, return_value=_resp(_TREND)), pytest.raises(
        VendorUnavailableError, match="이전 데이터가 없습니다"
    ):
        naver_investor.get_investor_flow("001210", "2026-01-05")


@pytest.mark.unit
@pytest.mark.parametrize("status", [404, 410, 500])
def test_http_error_raises(status):
    with patch(GET, return_value=_resp(None, status)), pytest.raises(
        VendorUnavailableError, match=str(status)
    ):
        naver_investor.get_investor_flow("001210", "2026-11-03")


@pytest.mark.unit
def test_network_error_raises():
    with patch(GET, side_effect=requests.ConnectionError("boom")), pytest.raises(
        VendorUnavailableError
    ):
        naver_investor.get_investor_flow("001210", "2026-11-03")


@pytest.mark.unit
@pytest.mark.parametrize("payload", [{"error": "x"}, "<html></html>"])
def test_unexpected_structure_raises(payload):
    with patch(GET, return_value=_resp(payload)), pytest.raises(VendorUnavailableError):
        naver_investor.get_investor_flow("001210", "2026-11-03")


@pytest.mark.unit
def test_non_json_raises():
    resp = MagicMock(status_code=200)
    resp.json.side_effect = ValueError("nope")
    with patch(GET, return_value=resp), pytest.raises(VendorUnavailableError, match="JSON"):
        naver_investor.get_investor_flow("001210", "2026-11-03")


@pytest.mark.unit
def test_skips_rows_with_unparseable_numbers():
    rows = [_row("20261103", "N/A", "0", "0"), _row("20261102", "+10", "0", "-10")]
    with patch(GET, return_value=_resp(rows)):
        out = naver_investor.get_investor_flow("001210", "2026-11-03")
    assert "| 2026-11-02 |" in out and "| 2026-11-03 |" not in out


@pytest.mark.integration
def test_live_naver_trend_returns_recent_flow():
    from datetime import datetime

    out = naver_investor.get_investor_flow("005930", datetime.now().strftime("%Y-%m-%d"))
    assert "외국인" in out and "단위: 주" in out
