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


# ---------- 조회 한도 (#188) ----------

def _page(prefix, stamp, n=20):
    """``n`` 건짜리 한 쪽 (제목 유일). 한 쪽이 꽉 차 있으면 소스가 더 남은 것으로 본다."""
    return _clusters(*[_item(f"{prefix} {i}", stamp, article_id=f"{prefix}{i}") for i in range(n)])


def _patch_stock_pages(*pages):
    """호출 순서대로 ``pages`` 를 돌려주고, 소진되면 빈 쪽."""
    responses = [_json_response(p) for p in pages]
    return patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        side_effect=responses + [_json_response([])] * 200,
    )


@pytest.mark.unit
def test_get_news_raises_when_limit_hit_before_reaching_window(monkeypatch):
    """한도(최신 N건)가 전부 기간 끝보다 새로우면 "기사 없음" 이 아니라 실패."""
    monkeypatch.setattr(naver_news, "_STOCK_NEWS_MAX_PAGES", 3)
    newer = _page("너무 최근", "202611050900")
    with _patch_stock_pages(newer, newer, newer) as get, pytest.raises(
        VendorUnavailableError, match="조회 한도",
    ):
        naver_news.get_news("005930", "2026-11-01", "2026-11-03")
    assert get.call_count == 3


@pytest.mark.unit
def test_get_news_marks_partial_coverage_when_limit_hit_inside_window(monkeypatch):
    """기간 끝에는 닿았지만 시작까지 못 갔으면 조회된 만큼 반환하고 일부만 조회됐음을 명시."""
    monkeypatch.setattr(naver_news, "_STOCK_NEWS_MAX_PAGES", 2)
    newer = _page("너무 최근", "202611050900")
    inside = _clusters(
        _item("기간 안 기사", "202611031000", article_id="in"),
        *[_item(f"최근 {i}", "202611050900", article_id=f"n{i}") for i in range(19)],
    )
    with _patch_stock_pages(newer, inside):
        out = naver_news.get_news("005930", "2026-11-01", "2026-11-03")

    assert "기간 안 기사" in out
    assert "조회 한도" in out
    assert "2026-11-03 이후 기사만 조회됨" in out
    assert "기사 없음으로 해석하지 마세요" in out


@pytest.mark.unit
def test_get_news_short_page_means_no_news_not_limit():
    """소스를 끝까지 읽었는데 기간 안 기사가 없으면 정상적인 "뉴스 없음"."""
    few = _clusters(_item("기간 밖 기사", "202611050900", article_id="x"))
    with _patch_stock_pages(few):
        out = naver_news.get_news("005930", "2026-11-01", "2026-11-03")

    assert "해당 기간 뉴스가 없습니다" in out
    assert "조회 한도" not in out


@pytest.mark.unit
def test_get_news_reads_whole_window_instead_of_stopping_at_item_cap(monkeypatch):
    """30건이 차도 멈추지 않고 기간 끝까지 읽는다 — 최신 몇 시간치로 채우지 않기 위해 (#195)."""
    monkeypatch.setattr(naver_news, "_STOCK_NEWS_MAX_PAGES", 5)
    older = _clusters(_item("기간 시작 전", "202610310900", article_id="old"))
    with _patch_stock_pages(
        _page("가", "202611031000"), _page("나", "202611021000"), _page("다", "202611011000"), older,
    ) as get:
        out = naver_news.get_news("005930", "2026-11-01", "2026-11-03")

    assert get.call_count == 4
    assert out.count("- **") == naver_news._STOCK_NEWS_MAX_ITEMS
    assert "조회 한도" not in out


@pytest.mark.unit
def test_get_news_samples_evenly_by_day_with_day_counts(monkeypatch):
    """기사가 상한보다 많으면 날짜별로 고르게 뽑고, 일자별 기사 수를 헤더에 붙인다 (#195)."""
    monkeypatch.setattr(naver_news, "_STOCK_NEWS_MAX_ITEMS", 6)
    day3 = [_item(f"3일 {i}", f"2026110321{i:02d}", article_id=f"c{i}") for i in range(10)]
    day2 = [_item(f"2일 {i}", f"2026110221{i:02d}", article_id=f"b{i}") for i in range(4)]
    day1 = [_item("1일 0", "202611011200", article_id="a0")]
    older = _item("기간 시작 전", "202610310900", article_id="old")
    with _patch_stock_pages(_clusters(*day3, *day2, *day1, older)):
        out = naver_news.get_news("005930", "2026-11-01", "2026-11-03")

    lines = [ln for ln in out.splitlines() if ln.startswith("- **")]
    days = [ln[4:14] for ln in lines]
    # 6건을 3일에 고르게: 11-01 은 1건뿐이라 남는 몫이 다른 날로 간다 (3일 3건·2일 2건·1일 1건 또는 비슷하게)
    assert days.count("2026-11-01") == 1
    assert days.count("2026-11-02") >= 2
    assert days.count("2026-11-03") >= 2
    assert days == sorted(days, reverse=True)  # 최신순 정렬 유지
    # 각 날짜 안에서는 최신 기사부터
    assert "3일 9" in out and "3일 0" not in out
    assert "기간 내 기사 15건 중 날짜별로 고르게 6건" in out
    assert "11-01 1 · 11-02 4 · 11-03 10" in out


@pytest.mark.unit
def test_get_news_no_day_counts_when_all_items_fit():
    """기사가 상한 이하면 전부 싣고 샘플링 문구를 붙이지 않는다."""
    with _patch_stock_pages(_STOCK_NEWS_JSON):
        out = naver_news.get_news("005930", "2026-11-01", "2026-11-03")
    assert "날짜별로 고르게" not in out


@pytest.mark.unit
def test_sample_by_day_keeps_undated_items_last():
    from datetime import datetime
    items = [
        {"title": "날짜 없음", "date": None},
        {"title": "a", "date": datetime(2026, 11, 3, 10)},
        {"title": "b", "date": datetime(2026, 11, 3, 9)},
        {"title": "c", "date": datetime(2026, 11, 2, 9)},
    ]
    picked = naver_news._sample_by_day(items, 3)
    assert [i["title"] for i in picked] == ["a", "c", "날짜 없음"]


@pytest.mark.unit
def test_get_news_requests_documented_page_size():
    """pageSize 50/100 은 서버가 불규칙·비-JSON 으로 응답한다 — 20 을 유지한다."""
    with _patch_stock_pages([]) as get:
        naver_news.get_news("005930", "2026-11-01", "2026-11-03")
    assert get.call_args_list[0].kwargs["params"] == {"pageSize": 20, "page": 1}


# ---------- 일시적 오류 재시도·부분 결과 (#194) ----------

@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    """재시도 대기를 없앤다 — 대기 시간은 ``_STOCK_NEWS_RETRY_DELAYS`` 로 검증."""
    sleeps: list[float] = []
    monkeypatch.setattr(naver_news.time, "sleep", sleeps.append)
    return sleeps


@pytest.mark.unit
def test_get_news_retries_transient_502_on_same_page(_no_retry_sleep):
    """쪽 하나가 502 → 같은 쪽을 다시 불러 성공하면 정상 결과."""
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        side_effect=[_json_response(None, status=502), _json_response(_STOCK_NEWS_JSON)],
    ) as get:
        out = naver_news.get_news("005930", "2026-11-02", "2026-11-03")

    assert "4분기 실적 호조" in out
    assert get.call_count == 2
    assert get.call_args_list[1].kwargs["params"]["page"] == 1
    assert _no_retry_sleep == [naver_news._STOCK_NEWS_RETRY_DELAYS[0]]


@pytest.mark.unit
def test_get_news_retries_network_error():
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        side_effect=[requests.ConnectionError("boom"), _json_response(_STOCK_NEWS_JSON)],
    ):
        out = naver_news.get_news("005930", "2026-11-02", "2026-11-03")
    assert "4분기 실적 호조" in out


@pytest.mark.unit
@pytest.mark.parametrize("status", [404, 410])
def test_get_news_does_not_retry_non_transient_status(status):
    """폐지(410)·404 는 다시 불러도 같다 — 재시도 없이 바로 실패."""
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_json_response(None, status=status),
    ) as get, pytest.raises(VendorUnavailableError, match=str(status)):
        naver_news.get_news("005930", "2026-11-01", "2026-11-03")
    assert get.call_count == 1


@pytest.mark.unit
def test_get_news_first_page_failing_after_retries_raises(_no_retry_sleep):
    """첫 쪽이 재시도 후에도 실패하면 읽은 기사가 없으므로 사유와 함께 실패 (기존 동작)."""
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_json_response(None, status=502),
    ) as get, pytest.raises(VendorUnavailableError, match="502"):
        naver_news.get_news("005930", "2026-11-01", "2026-11-03")
    assert get.call_count == 1 + len(naver_news._STOCK_NEWS_RETRY_DELAYS)
    assert _no_retry_sleep == list(naver_news._STOCK_NEWS_RETRY_DELAYS)


@pytest.mark.unit
def test_get_news_returns_partial_result_when_later_page_keeps_failing():
    """기간 안 기사를 읽은 뒤 다음 쪽이 계속 502 면, 버리지 않고 일부만 조회됐음을 명시해 반환."""
    inside = _clusters(*[_item(f"기간 안 {i}", "202611031000", article_id=f"in{i}") for i in range(10)],
                       *[_item(f"최근 {i}", "202611050900", article_id=f"n{i}") for i in range(10)])
    failures = [_json_response(None, status=502)] * (1 + len(naver_news._STOCK_NEWS_RETRY_DELAYS))
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        side_effect=[_json_response(inside), *failures],
    ):
        out = naver_news.get_news("005930", "2026-11-01", "2026-11-03")

    assert "기간 안 0" in out
    assert "HTTP 502" in out
    assert "2026-11-03 10:00 이후 기사만 조회됨" in out
    assert "기사 없음으로 해석하지 마세요" in out


@pytest.mark.unit
def test_get_news_later_page_failure_before_reaching_window_raises():
    """기간 끝에 닿기 전(전부 더 최근 기사) 실패하면 부분 결과가 의미 없으므로 실패."""
    newer = _page("너무 최근", "202611050900")
    failures = [_json_response(None, status=502)] * (1 + len(naver_news._STOCK_NEWS_RETRY_DELAYS))
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        side_effect=[_json_response(newer), *failures],
    ), pytest.raises(VendorUnavailableError, match="502"):
        naver_news.get_news("005930", "2026-11-01", "2026-11-03")


# ---------- 빈 쪽 재확인 (#198) ----------

@pytest.mark.unit
def test_get_news_empty_first_page_is_rechecked(_no_retry_sleep):
    """첫 쪽이 일시적으로 비어 와도 "뉴스 없음" 으로 끝내지 않고 같은 쪽을 다시 본다."""
    with _patch_stock_pages([], _STOCK_NEWS_JSON) as get:
        out = naver_news.get_news("005930", "2026-11-02", "2026-11-03")

    assert "4분기 실적 호조" in out
    assert "해당 기간 뉴스가 없습니다" not in out
    assert [c.kwargs["params"]["page"] for c in get.call_args_list[:2]] == [1, 1]
    assert _no_retry_sleep == [naver_news._STOCK_NEWS_RETRY_DELAYS[0]]


@pytest.mark.unit
def test_get_news_empty_middle_page_continues_to_next_page():
    """중간 쪽이 두 번 다 비어도 다음 쪽에 기사가 있으면 이어서 읽는다."""
    newer = _page("너무 최근", "202611050900")
    after_gap = _clusters(_item("빈 쪽 뒤 기사", "202611031000", article_id="gap"))
    with _patch_stock_pages(newer, [], [], after_gap) as get:
        out = naver_news.get_news("005930", "2026-11-01", "2026-11-03")

    assert "빈 쪽 뒤 기사" in out
    assert [c.kwargs["params"]["page"] for c in get.call_args_list] == [1, 2, 2, 3]


@pytest.mark.unit
def test_get_news_really_no_news_still_means_no_news():
    """같은 쪽 재확인과 다음 쪽이 모두 비면 정말 기사 끝 — 기존대로 "뉴스 없음"."""
    with _patch_stock_pages() as get:
        out = naver_news.get_news("005930", "2026-11-01", "2026-11-03")

    assert "해당 기간 뉴스가 없습니다" in out
    assert "조회 한도" not in out
    assert [c.kwargs["params"]["page"] for c in get.call_args_list] == [1, 1, 2]


@pytest.mark.unit
def test_get_news_empty_last_page_does_not_request_beyond_limit(monkeypatch):
    """마지막 허용 쪽이 비면 다음 쪽(서버 상한 밖, HTTP 400)을 부르지 않는다."""
    monkeypatch.setattr(naver_news, "_STOCK_NEWS_MAX_PAGES", 2)
    newer = _page("너무 최근", "202611050900")
    with _patch_stock_pages(newer) as get:
        naver_news.get_news("005930", "2026-11-01", "2026-11-03")

    assert [c.kwargs["params"]["page"] for c in get.call_args_list] == [1, 2, 2]


# ---------- 노이즈 필터 ----------

@pytest.mark.unit
@pytest.mark.parametrize("title", ["[포토] 신제품 발표", "[부고] XX 회장 별세", "증시요약 삼성전자 상승"])
def test_noise_filter_rejects_known_patterns(title):
    assert naver_news._is_noise(title) is True


@pytest.mark.unit
def test_noise_filter_passes_normal_titles():
    assert naver_news._is_noise("삼성전자 4분기 실적 호조") is False


# ---------- 주요뉴스 (네이버 증권 JSON, #189) ----------

def _main(title, stamp, office="연합뉴스", oid="001", aid="0000000001"):
    return {
        "type": 1,
        "subcontent": "본문 요약",
        "oid": oid,
        "ohnm": office,
        "aid": aid,
        "tit": title,
        "dt": stamp,
    }


_MAIN_PAGE = [
    _main("한국은행 기준금리 동결", "20261103150000", aid="0000000100"),
    _main("코스피 2% 상승 마감", "20261103143000", office="이데일리", aid="0000000101"),
]


def _patch_main_get(*pages):
    """``requests.get`` 이 호출 순서대로 ``pages`` 를 JSON 으로 돌려주게 한다. 소진 후엔 빈 리스트."""
    responses = [_json_response(list(p)) for p in pages]
    return patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        side_effect=responses + [_json_response([])] * 100,
    )


@pytest.mark.unit
def test_get_global_news_renders_items():
    with _patch_main_get(_MAIN_PAGE) as get:
        out = naver_news.get_global_news("2026-11-03", look_back_days=1, limit=5)

    assert "## 주요뉴스" in out
    assert "한국은행 기준금리 동결" in out
    assert "코스피 2% 상승 마감" in out
    assert "| 이데일리 |" in out
    assert "https://n.news.naver.com/mnews/article/001/0000000100" in out
    # 날짜 파라미터가 없으므로 category/pageSize/page 로만 호출
    assert get.call_args_list[0].kwargs["params"] == {
        "category": "mainnews", "pageSize": 20, "page": 1,
    }


@pytest.mark.unit
def test_get_global_news_respects_limit():
    with _patch_main_get(_MAIN_PAGE):
        out = naver_news.get_global_news("2026-11-03", look_back_days=1, limit=1)

    assert "기준금리 동결" in out
    assert "코스피 2% 상승 마감" not in out


@pytest.mark.unit
def test_get_global_news_handles_empty():
    with _patch_main_get([]):
        out = naver_news.get_global_news("2026-11-03")

    assert "주요뉴스가 없습니다" in out


@pytest.mark.unit
def test_get_global_news_skips_newer_than_as_of_and_stops_at_window_start():
    """기준일보다 새로운 기사는 건너뛰고, 창보다 오래된 기사에서 멈춘다 (다음 쪽을 읽지 않는다)."""
    page1 = [
        _main("기준일 이후 기사", "20261104090000", aid="1"),
        _main("기준일 당일 기사", "20261103100000", aid="2"),
        _main("전일 기사", "20261102100000", aid="3"),
    ]
    with _patch_main_get(page1, [_main("읽으면 안 되는 기사", "20261103090000", aid="4")]) as get:
        out = naver_news.get_global_news("2026-11-03", look_back_days=1)

    assert "기준일 당일 기사" in out
    assert "기준일 이후 기사" not in out
    assert "전일 기사" not in out
    assert get.call_count == 1


@pytest.mark.unit
def test_get_global_news_look_back_includes_earlier_days():
    page1 = [
        _main("당일 기사", "20261103100000", aid="1"),
        _main("전일 기사", "20261102100000", aid="2"),
        _main("3일 전 기사", "20261031100000", aid="3"),
    ]
    with _patch_main_get(page1):
        out = naver_news.get_global_news("2026-11-03", look_back_days=2)

    assert "당일 기사" in out
    assert "전일 기사" in out
    assert "3일 전 기사" not in out


@pytest.mark.unit
def test_get_global_news_pages_back_to_past_as_of_date():
    """기준일이 과거면 최신 쪽들을 넘겨 기준일 창에 닿을 때까지 읽는다."""
    newer = [_main("너무 최근 기사", "20261105100000", aid="1")]
    target = [_main("기준일 기사", "20261103100000", aid="2")]
    with _patch_main_get(newer, newer, target) as get:
        out = naver_news.get_global_news("2026-11-03", look_back_days=1)

    assert "기준일 기사" in out
    assert "너무 최근 기사" not in out
    assert [c.kwargs["params"]["page"] for c in get.call_args_list][:3] == [1, 2, 3]


@pytest.mark.unit
def test_get_global_news_unreachable_as_of_date_raises(monkeypatch):
    """조회 한도 안에서 기준일에 못 닿으면 "주요뉴스 없음" 이 아니라 실패."""
    monkeypatch.setattr(naver_news, "_MAIN_NEWS_MAX_PAGES", 3)
    newer = [_main("너무 최근 기사", "20261105100000", aid="1")]
    with _patch_main_get(newer, newer, newer), pytest.raises(VendorUnavailableError, match="조회 한도"):
        naver_news.get_global_news("2026-11-03")


@pytest.mark.unit
def test_get_global_news_filters_noise_and_dedupes_titles():
    page = [
        _main("[포토] 증시 현장", "20261103150000", aid="1"),
        _main("한국은행 기준금리 동결", "20261103140000", aid="2"),
        _main("한국은행 기준금리 동결", "20261103130000", office="이데일리", aid="3"),
    ]
    with _patch_main_get(page):
        out = naver_news.get_global_news("2026-11-03")

    assert "[포토]" not in out
    assert out.count("기준금리 동결") == 1


@pytest.mark.unit
def test_get_global_news_skips_malformed_items():
    page = ["문자열", {"tit": "", "dt": "20261103150000"}, {"tit": "시각 없음"}, *_MAIN_PAGE]
    with _patch_main_get(page):
        out = naver_news.get_global_news("2026-11-03")

    assert "한국은행 기준금리 동결" in out
    assert "시각 없음" not in out


@pytest.mark.unit
def test_get_global_news_html_response_raises():
    """엔드포인트가 이전돼 HTML(SPA) 이 오면 "주요뉴스 없음" 이 아니라 실패."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.side_effect = ValueError("not json")
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get", return_value=resp,
    ), pytest.raises(VendorUnavailableError, match="JSON"):
        naver_news.get_global_news("2026-11-03")


@pytest.mark.unit
def test_get_global_news_http_error_raises():
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        return_value=_json_response([], status=410),
    ), pytest.raises(VendorUnavailableError, match="410"):
        naver_news.get_global_news("2026-11-03")


@pytest.mark.unit
def test_get_global_news_network_exception_raises():
    with patch(
        "tradingagents.dataflows.vendors.naver_news.requests.get",
        side_effect=requests.ConnectionError("boom"),
    ), pytest.raises(VendorUnavailableError, match="ConnectionError"):
        naver_news.get_global_news("2026-11-03")


@pytest.mark.unit
def test_get_global_news_handles_bad_date():
    out = naver_news.get_global_news("not-a-date")
    assert "잘못된 날짜 형식" in out


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


@pytest.mark.integration
def test_live_global_news_returns_articles():
    """실제 네이버 증권 주요뉴스 JSON — 오늘 기준 기사 1건 이상 (엔드포인트 이전 회귀 방지, #189)."""
    from datetime import datetime

    out = naver_news.get_global_news(datetime.now().strftime("%Y-%m-%d"), limit=5)
    assert "주요뉴스가 없습니다" not in out
    assert "https://n.news.naver.com/mnews/article/" in out
