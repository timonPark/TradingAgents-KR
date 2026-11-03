"""Task 7a (#62): 네이버 금융 뉴스 vendor 유닛 테스트.

실제 네트워크 호출 금지 — 전부 `requests.get` 모킹. 통합 테스트는 Task 11 로.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows.vendors import naver_news


def _ok_response(html: str, encoding: str = "utf-8"):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = html
    resp.encoding = encoding
    resp.apparent_encoding = encoding
    return resp


# ---------- 종목 뉴스 파싱 ----------

_ITEM_NEWS_HTML = """
<html><body>
<table class="type5">
<tbody>
  <tr>
    <td class="title"><a href="/item/news_read.naver?article_id=001">삼성전자 4분기 실적 호조</a></td>
    <td class="info">머니투데이</td>
    <td class="date">2026.11.03 14:30</td>
  </tr>
  <tr>
    <td class="title"><a href="/item/news_read.naver?article_id=002">[포토] 삼성전자 신제품 발표회</a></td>
    <td class="info">연합뉴스</td>
    <td class="date">2026.11.03 10:00</td>
  </tr>
  <tr>
    <td class="title"><a href="/item/news_read.naver?article_id=003">삼성전자, 반도체 투자 확대</a></td>
    <td class="info">한국경제</td>
    <td class="date">2026.11.01 09:15</td>
  </tr>
</tbody>
</table>
</body></html>
"""


@pytest.mark.unit
def test_get_news_filters_date_range_and_noise(monkeypatch):
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_ok_response(_ITEM_NEWS_HTML),
    ):
        out = naver_news.get_news("005930", "2026-11-02", "2026-11-03")

    # 2026-11-03 뉴스 포함, 2026-11-01 뉴스 제외
    assert "4분기 실적 호조" in out
    assert "반도체 투자 확대" not in out
    # [포토] 는 노이즈 필터로 제외
    assert "[포토]" not in out


@pytest.mark.unit
def test_get_news_renders_markdown_header(monkeypatch):
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_ok_response(_ITEM_NEWS_HTML),
    ):
        out = naver_news.get_news("005930", "2026-11-01", "2026-11-03")

    assert "## 005930 뉴스 (2026-11-01 ~ 2026-11-03)" in out
    assert "머니투데이" in out
    assert "finance.naver.com" in out


@pytest.mark.unit
def test_get_news_handles_bad_date_format():
    out = naver_news.get_news("005930", "2026/11/01", "2026-11-03")
    assert "잘못된 날짜 형식" in out


@pytest.mark.unit
def test_get_news_handles_empty_html(monkeypatch):
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_ok_response("<html><body>no table</body></html>"),
    ):
        out = naver_news.get_news("005930", "2026-11-01", "2026-11-03")
    assert "해당 기간 뉴스가 없습니다" in out


@pytest.mark.unit
def test_get_news_handles_http_error(monkeypatch):
    err_resp = MagicMock(status_code=500, text="", encoding=None, apparent_encoding="utf-8")
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=err_resp,
    ):
        out = naver_news.get_news("005930", "2026-11-01", "2026-11-03")
    assert "해당 기간 뉴스가 없습니다" in out


@pytest.mark.unit
def test_get_news_handles_network_exception(monkeypatch):
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        side_effect=ConnectionError("boom"),
    ):
        out = naver_news.get_news("005930", "2026-11-01", "2026-11-03")
    assert "해당 기간 뉴스가 없습니다" in out


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
def test_live_item_news_for_005930_returns_markdown_header():
    """실제 네이버 금융에서 005930 뉴스를 크롤 — 최근 3일 범위."""
    from datetime import datetime, timedelta

    today = datetime.now()
    end = today.strftime("%Y-%m-%d")
    start = (today - timedelta(days=3)).strftime("%Y-%m-%d")
    out = naver_news.get_news("005930", start, end)
    # 네트워크 성공 또는 특정 범위에 뉴스 없음 두 경우 모두 Markdown 헤더는 포함.
    assert f"## 005930 뉴스 ({start} ~ {end})" in out


@pytest.mark.integration
def test_live_global_news_returns_markdown_header():
    """실제 네이버 금융 주요뉴스 — 최근 1일."""
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    out = naver_news.get_global_news(today, look_back_days=1, limit=5)
    assert "## 주요뉴스" in out
