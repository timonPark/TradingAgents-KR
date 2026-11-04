"""Task 7a (#62): 네이버 금융 뉴스 vendor 유닛 테스트.

실제 네트워크 호출 금지 — 전부 `requests.get` 모킹. 통합 테스트는 Task 11 로.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors import naver_news


def _ok_response(html: str, encoding: str = "utf-8"):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = html
    resp.encoding = encoding
    resp.apparent_encoding = encoding
    return resp


# ---------- 종목 뉴스 (네이버 증권 JSON, #138) ----------

def _json_response(payload, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    return resp


def _item(title, stamp, office="머니투데이", article_id="001"):
    return {
        "id": f"015{article_id}",
        "officeName": office,
        "datetime": stamp,
        "title": title,
        "titleFull": title,
        "mobileNewsUrl": f"https://n.news.naver.com/mnews/article/015/{article_id}",
    }


def _clusters(*items):
    """증권 JSON 은 ``[{"total": N, "items": [...]}, ...]`` 클러스터 리스트."""
    return [{"total": 1, "items": [i]} for i in items]


_STOCK_NEWS_JSON = _clusters(
    _item("삼성전자 4분기 실적 호조", "202611031430", article_id="001"),
    _item("[포토] 삼성전자 신제품 발표회", "202611031000", office="연합뉴스", article_id="002"),
    _item("삼성전자, 반도체 투자 확대", "202611010915", office="한국경제", article_id="003"),
)


@pytest.mark.unit
def test_get_news_filters_date_range_and_noise():
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_json_response(_STOCK_NEWS_JSON),
    ):
        out = naver_news.get_news("005930", "2026-11-02", "2026-11-03")

    # 2026-11-03 뉴스 포함, 2026-11-01 뉴스 제외
    assert "4분기 실적 호조" in out
    assert "반도체 투자 확대" not in out
    # [포토] 는 노이즈 필터로 제외
    assert "[포토]" not in out


@pytest.mark.unit
def test_get_news_renders_markdown_header():
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_json_response(_STOCK_NEWS_JSON),
    ):
        out = naver_news.get_news("005930", "2026-11-01", "2026-11-03")

    assert "## 005930 뉴스 (2026-11-01 ~ 2026-11-03)" in out
    assert "머니투데이" in out
    assert "n.news.naver.com" in out


@pytest.mark.unit
def test_get_news_unescapes_html_entities():
    payload = _clusters(_item("&quot;코스피 반등&quot; 전망", "202611031430"))
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_json_response(payload),
    ):
        out = naver_news.get_news("005930", "2026-11-03", "2026-11-03")
    assert '"코스피 반등" 전망' in out
    assert "&quot;" not in out


@pytest.mark.unit
def test_get_news_handles_bad_date_format():
    out = naver_news.get_news("005930", "2026/11/01", "2026-11-03")
    assert "잘못된 날짜 형식" in out


@pytest.mark.unit
def test_get_news_empty_response_means_no_news():
    """정상 응답인데 기사가 없을 때만 "뉴스 없음" — 실패와 구분된다."""
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_json_response([]),
    ):
        out = naver_news.get_news("005930", "2026-11-01", "2026-11-03")
    assert "해당 기간 뉴스가 없습니다" in out


@pytest.mark.unit
@pytest.mark.parametrize("status", [410, 404, 500])
def test_get_news_http_error_raises_not_empty(status):
    """폐지(410)·서버 오류는 "뉴스 0건" 이 아니라 실패 (#138)."""
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_json_response(None, status=status),
    ), pytest.raises(VendorUnavailableError, match=str(status)):
        naver_news.get_news("005930", "2026-11-01", "2026-11-03")


@pytest.mark.unit
def test_get_news_network_exception_raises():
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        side_effect=requests.ConnectionError("boom"),
    ), pytest.raises(VendorUnavailableError):
        naver_news.get_news("005930", "2026-11-01", "2026-11-03")


@pytest.mark.unit
@pytest.mark.parametrize("payload", [{"error": "x"}, "<html>spa</html>"])
def test_get_news_unexpected_structure_raises(payload):
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_json_response(payload),
    ), pytest.raises(VendorUnavailableError):
        naver_news.get_news("005930", "2026-11-01", "2026-11-03")


@pytest.mark.unit
def test_get_news_non_json_body_raises():
    resp = MagicMock(status_code=200)
    resp.json.side_effect = ValueError("not json")
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get", return_value=resp,
    ), pytest.raises(VendorUnavailableError, match="JSON"):
        naver_news.get_news("005930", "2026-11-01", "2026-11-03")


# ---------- 날짜 파싱 ----------

@pytest.mark.unit
@pytest.mark.parametrize(
    "text,expected_ymd",
    [
        ("2026.11.03 14:30", (2026, 11, 3)),
        ("2026-11-03 14:30", (2026, 11, 3)),
        ("2026.11.03", (2026, 11, 3)),
        ("2026-11-03", (2026, 11, 3)),
    ],
)
def test_parse_naver_date_handles_known_formats(text, expected_ymd):
    dt = naver_news._parse_naver_date(text)
    assert dt is not None
    assert (dt.year, dt.month, dt.day) == expected_ymd


@pytest.mark.unit
def test_parse_naver_date_handles_mm_dd_short_form():
    dt = naver_news._parse_naver_date("11/03")
    assert dt is not None
    assert (dt.month, dt.day) == (11, 3)


@pytest.mark.unit
def test_parse_naver_date_returns_none_for_junk():
    assert naver_news._parse_naver_date("not-a-date") is None


# ---------- 노이즈 필터 ----------

@pytest.mark.unit
@pytest.mark.parametrize("title", ["[포토] 신제품 발표", "[부고] XX 회장 별세", "증시요약 삼성전자 상승"])
def test_noise_filter_rejects_known_patterns(title):
    assert naver_news._is_noise(title) is True


@pytest.mark.unit
def test_noise_filter_passes_normal_titles():
    assert naver_news._is_noise("삼성전자 4분기 실적 호조") is False


# ---------- 주요뉴스 ----------

_MAIN_NEWS_HTML = """
<html><body>
<ul class="newsList">
  <li class="block1">
    <a href="/news/news_read.naver?article_id=100">한국은행 기준금리 동결</a>
    <div class="articleSummary">
      <span>연합뉴스</span>
      <span class="date">2026.11.03 15:00</span>
    </div>
  </li>
  <li class="block1">
    <a href="/news/news_read.naver?article_id=101">코스피 2% 상승 마감</a>
    <div class="articleSummary">
      <span>이데일리</span>
      <span class="date">2026.11.03 15:30</span>
    </div>
  </li>
</ul>
</body></html>
"""


@pytest.mark.unit
def test_get_global_news_renders_items(monkeypatch):
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_ok_response(_MAIN_NEWS_HTML),
    ):
        out = naver_news.get_global_news("2026-11-03", look_back_days=1, limit=5)

    assert "## 주요뉴스" in out
    assert "기준금리 동결" in out
    assert "코스피 2% 상승 마감" in out


@pytest.mark.unit
def test_get_global_news_respects_limit(monkeypatch):
    # 두 건이지만 limit=1 로 제한
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_ok_response(_MAIN_NEWS_HTML),
    ):
        out = naver_news.get_global_news("2026-11-03", look_back_days=1, limit=1)

    assert "기준금리 동결" in out
    assert "코스피 2% 상승 마감" not in out


@pytest.mark.unit
def test_get_global_news_handles_empty(monkeypatch):
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_ok_response("<html></html>"),
    ):
        out = naver_news.get_global_news("2026-11-03")

    assert "주요뉴스가 없습니다" in out


@pytest.mark.unit
def test_get_global_news_redirect_to_other_host_raises():
    """mainnews 가 stock.naver.com 으로 리다이렉트되면 "주요뉴스 없음" 이 아니라 실패."""
    resp = _ok_response("<html>spa</html>")
    resp.url = "https://stock.naver.com/news/mainnews"
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get", return_value=resp,
    ), pytest.raises(VendorUnavailableError, match="stock.naver.com"):
        naver_news.get_global_news("2026-11-03")


@pytest.mark.unit
def test_get_global_news_http_error_raises():
    resp = _ok_response("")
    resp.status_code = 410
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get", return_value=resp,
    ), pytest.raises(VendorUnavailableError, match="410"):
        naver_news.get_global_news("2026-11-03")


@pytest.mark.unit
def test_get_global_news_handles_bad_date():
    out = naver_news.get_global_news("not-a-date")
    assert "잘못된 날짜 형식" in out


@pytest.mark.unit
def test_get_global_news_dedupes_titles(monkeypatch):
    """여러 날짜/페이지에서 같은 제목이 나와도 중복 제거."""
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_ok_response(_MAIN_NEWS_HTML),
    ):
        out = naver_news.get_global_news("2026-11-03", look_back_days=3, limit=10)

    # "기준금리 동결" 이 하루 3페이지 × 3일 = 9회 반복되어도 1회만
    assert out.count("기준금리 동결") == 1


# ============================================================================
# Integration tests (Task 11a, #92) — 실제 네이버 금융 크롤. CI 는 skip.
#   로컬 실행: ``pytest tests/test_naver_news_vendor.py -m integration``
#   keyless 라 환경변수 불필요.
# ============================================================================


@pytest.mark.integration
def test_live_item_news_for_001210_returns_articles():
    """실제 네이버 증권 JSON — 최근 30일에 기사가 1건 이상 (0건 위장 회귀 방지, #138)."""
    from datetime import datetime, timedelta

    today = datetime.now()
    end = today.strftime("%Y-%m-%d")
    start = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    out = naver_news.get_news("001210", start, end)
    assert f"## 001210 뉴스 ({start} ~ {end})" in out
    assert "해당 기간 뉴스가 없습니다" not in out
