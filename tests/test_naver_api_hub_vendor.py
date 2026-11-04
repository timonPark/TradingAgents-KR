"""#138: NAVER API HUB 뉴스 검색 vendor 유닛 테스트.

실제 API 호출 금지 — ``requests.get`` 과 종목명 조회를 모킹. 실호출은 ``-m integration``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from tradingagents.dataflows.errors import VendorNotConfiguredError, VendorUnavailableError
from tradingagents.dataflows.krx_symbol_search import SymbolHit
from tradingagents.dataflows.vendors import naver_api_hub

SECRET = "super-secret-value"
GET = "tradingagents.dataflows.vendors.naver_api_hub.requests.get"
SEARCH = "tradingagents.dataflows.krx_symbol_search.search"


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("NAVER_API_HUB_CLIENT_ID", "test-id")
    monkeypatch.setenv("NAVER_API_HUB_CLIENT_SECRET", SECRET)


@pytest.fixture
def known_company():
    with patch(SEARCH, return_value=[SymbolHit("001210", "금호전기", "KOSPI")]):
        yield


def _resp(payload=None, status=200):
    resp = MagicMock(status_code=status)
    resp.json.return_value = payload
    return resp


def _news(title, pub="Tue, 03 Nov 2026 16:28:00 +0900", desc="", link="https://www.example.com/a"):
    return {"title": title, "description": desc, "pubDate": pub, "originallink": link, "link": link}


def _payload(*items):
    return {"lastBuildDate": "x", "total": len(items), "start": 1, "display": len(items),
            "items": list(items)}


# ---------- 설정 ----------

@pytest.mark.unit
def test_missing_credentials_raises_not_configured(monkeypatch):
    monkeypatch.delenv("NAVER_API_HUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_API_HUB_CLIENT_SECRET", raising=False)
    with pytest.raises(VendorNotConfiguredError, match="NAVER_API_HUB_CLIENT_ID"):
        naver_api_hub.get_news("001210", "2026-10-28", "2026-11-04")


@pytest.mark.unit
def test_bad_date_format_returns_message(creds):
    out = naver_api_hub.get_news("001210", "2026/10/28", "2026-11-04")
    assert "잘못된 날짜 형식" in out


# ---------- 요청 형태 ----------

@pytest.mark.unit
def test_request_uses_api_hub_url_headers_and_quoted_query(creds, known_company):
    with patch(GET, return_value=_resp(_payload())) as mock_get:
        naver_api_hub.get_news("001210", "2026-10-28", "2026-11-04")
    args, kwargs = mock_get.call_args
    assert args[0] == "https://naverapihub.apigw.ntruss.com/search/v1/news"
    assert kwargs["headers"] == {
        "X-NCP-APIGW-API-KEY-ID": "test-id",
        "X-NCP-APIGW-API-KEY": SECRET,
    }
    assert kwargs["params"]["query"] == '"금호전기"'
    assert kwargs["params"]["sort"] == "date"


# ---------- 종목 매칭 · 정리 ----------

@pytest.mark.unit
def test_keeps_title_and_ticker_matches_drops_name_only_in_body(creds, known_company):
    payload = _payload(
        _news("<b>금호전기</b> 주가, 11월 3일 애프터마켓 6,880원 하락"),
        _news("오늘의 메모[10월 29일]", desc="▲보통주추가상장=금호전기(001210)(국내CB)"),
        _news("파나소닉 형광등 76년 만에 퇴장", desc="일본 업계에서는 금호전기 같은 국내 업체도"),
    )
    with patch(GET, return_value=_resp(payload)):
        out = naver_api_hub.get_news("001210", "2026-10-28", "2026-11-04")
    assert "금호전기 주가, 11월 3일 애프터마켓" in out
    assert "<b>" not in out
    assert "오늘의 메모[10월 29일]" in out
    assert "파나소닉 형광등" not in out


@pytest.mark.unit
def test_unescapes_entities_and_dedupes_titles(creds, known_company):
    payload = _payload(
        _news("금호전기 &quot;반등&quot; 전망"),
        _news("금호전기 &quot;반등&quot; 전망", link="https://www.other.com/b"),
    )
    with patch(GET, return_value=_resp(payload)):
        out = naver_api_hub.get_news("001210", "2026-10-28", "2026-11-04")
    assert out.count('금호전기 "반등" 전망') == 1


@pytest.mark.unit
def test_filters_date_window_and_formats_source_host(creds, known_company):
    payload = _payload(
        _news("금호전기 신제품 출시", pub="Wed, 04 Nov 2026 14:16:00 +0900"),
        _news("금호전기 과거 기사", pub="Mon, 20 Oct 2026 09:00:00 +0900"),
    )
    with patch(GET, return_value=_resp(payload)):
        out = naver_api_hub.get_news("001210", "2026-10-28", "2026-11-04")
    assert "금호전기 신제품 출시" in out
    assert "금호전기 과거 기사" not in out
    assert "example.com" in out
    assert "2026-11-04 14:16" in out


@pytest.mark.unit
def test_empty_items_means_no_news(creds, known_company):
    with patch(GET, return_value=_resp(_payload())):
        out = naver_api_hub.get_news("001210", "2026-10-28", "2026-11-04")
    assert "해당 기간 뉴스가 없습니다" in out


@pytest.mark.unit
def test_stops_paging_once_older_than_window(creds, known_company):
    old = [_news(f"금호전기 오래된 기사 {i}", pub="Mon, 05 Oct 2026 09:00:00 +0900") for i in range(100)]
    with patch(GET, return_value=_resp(_payload(*old))) as mock_get:
        naver_api_hub.get_news("001210", "2026-10-28", "2026-11-04")
    assert mock_get.call_count == 1


# ---------- 실패는 0건이 아니라 예외 ----------

@pytest.mark.unit
@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_raises_not_configured(creds, known_company, status):
    with patch(GET, return_value=_resp(None, status)), pytest.raises(
        VendorNotConfiguredError, match="인증 실패"
    ):
        naver_api_hub.get_news("001210", "2026-10-28", "2026-11-04")


@pytest.mark.unit
def test_rate_limit_raises_unavailable(creds, known_company):
    with patch(GET, return_value=_resp(None, 429)), pytest.raises(
        VendorUnavailableError, match="한도"
    ):
        naver_api_hub.get_news("001210", "2026-10-28", "2026-11-04")


@pytest.mark.unit
@pytest.mark.parametrize("status", [500, 502, 404])
def test_server_error_raises_unavailable(creds, known_company, status):
    with patch(GET, return_value=_resp(None, status)), pytest.raises(
        VendorUnavailableError, match=str(status)
    ):
        naver_api_hub.get_news("001210", "2026-10-28", "2026-11-04")


@pytest.mark.unit
def test_network_error_raises_unavailable_without_leaking_secret(creds, known_company):
    with patch(GET, side_effect=requests.ConnectionError(f"boom {SECRET}")), pytest.raises(
        VendorUnavailableError
    ) as exc_info:
        naver_api_hub.get_news("001210", "2026-10-28", "2026-11-04")
    assert SECRET not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


@pytest.mark.unit
def test_non_json_response_raises_unavailable(creds, known_company):
    resp = MagicMock(status_code=200)
    resp.json.side_effect = ValueError("not json")
    with patch(GET, return_value=resp), pytest.raises(VendorUnavailableError, match="JSON"):
        naver_api_hub.get_news("001210", "2026-10-28", "2026-11-04")


@pytest.mark.unit
def test_error_body_without_items_raises_unavailable(creds, known_company):
    with patch(GET, return_value=_resp({"errorCode": "SE99"})), pytest.raises(
        VendorUnavailableError, match="SE99"
    ):
        naver_api_hub.get_news("001210", "2026-10-28", "2026-11-04")


@pytest.mark.unit
def test_company_name_lookup_failure_raises_unavailable(creds):
    with patch(SEARCH, side_effect=RuntimeError("krx down")), pytest.raises(
        VendorUnavailableError, match="종목명"
    ):
        naver_api_hub.get_news("001210", "2026-10-28", "2026-11-04")


@pytest.mark.unit
def test_unknown_ticker_raises_unavailable(creds):
    with patch(SEARCH, return_value=[]), pytest.raises(VendorUnavailableError, match="종목명"):
        naver_api_hub.get_news("999999", "2026-10-28", "2026-11-04")


# ============================================================================
# Integration — 실제 API HUB 호출. NAVER_API_HUB_CLIENT_ID/SECRET 필요. CI 는 skip.
#   로컬: ``pytest tests/test_naver_api_hub_vendor.py -m integration``
# ============================================================================

@pytest.fixture
def live_credentials():
    import os

    if not (os.environ.get("NAVER_API_HUB_CLIENT_ID") and os.environ.get("NAVER_API_HUB_CLIENT_SECRET")):
        pytest.skip("NAVER_API_HUB_CLIENT_ID/SECRET 미설정")


@pytest.mark.integration
def test_live_api_hub_returns_matched_articles(live_credentials):
    from datetime import datetime, timedelta

    today = datetime.now()
    end = today.strftime("%Y-%m-%d")
    start = (today - timedelta(days=14)).strftime("%Y-%m-%d")
    with patch(SEARCH, return_value=[SymbolHit("005930", "삼성전자", "KOSPI")]):
        out = naver_api_hub.get_news("005930", start, end)
    assert f"## 005930 뉴스 ({start} ~ {end})" in out
    assert "해당 기간 뉴스가 없습니다" not in out


# ---------- 라우터 체인: API HUB → 네이버 증권 폴백 (#138) ----------

def _stock_json_response(*titles_and_stamps):
    items = [
        {"id": str(i), "officeName": "서울경제", "datetime": stamp, "title": title,
         "titleFull": title, "mobileNewsUrl": f"https://n.news.naver.com/{i}"}
        for i, (title, stamp) in enumerate(titles_and_stamps)
    ]
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"total": 1, "items": [i]} for i in items]
    return resp


@pytest.mark.unit
def test_router_falls_back_to_stock_json_when_api_hub_not_configured(monkeypatch):
    """키가 없으면 API HUB 는 건너뛰고 네이버 증권 JSON 이 기사를 돌려준다."""
    from tradingagents.dataflows.router import route_to_vendor

    monkeypatch.delenv("NAVER_API_HUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_API_HUB_CLIENT_SECRET", raising=False)
    fallback = _stock_json_response(("금호전기 CB 상장", "202611031000"))
    with patch("tradingagents.dataflows.vendors.naver_news.requests.get", return_value=fallback):
        out = route_to_vendor("get_news", "001210", "2026-11-01", "2026-11-04")
    assert "금호전기 CB 상장" in out
    assert "DATA_UNAVAILABLE" not in out


@pytest.mark.unit
def test_router_reports_data_unavailable_when_every_vendor_fails(creds, known_company):
    """두 vendor 모두 실패하면 "뉴스 0건" 이 아니라 DATA_UNAVAILABLE 로 보고한다."""
    from tradingagents.dataflows.router import route_to_vendor

    dead = MagicMock(status_code=410)
    with patch(GET, return_value=_resp(None, 429)), patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get", return_value=dead
    ):
        out = route_to_vendor("get_news", "001210", "2026-11-01", "2026-11-04")
    assert out.startswith("DATA_UNAVAILABLE")
    assert "해당 기간 뉴스가 없습니다" not in out
