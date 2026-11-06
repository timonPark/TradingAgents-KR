"""#166: 현재 핵심 이슈 — 조회한 뉴스·공시에서 근거가 확인되는 이슈만, 출처는 조회 데이터로."""

from __future__ import annotations

import json

import pytest

from tradingagents.agents.analysts import company_issues as ci
from tradingagents.report_html import company_overview_html

NEWS = """## 196170 뉴스 (2026-10-29 ~ 2026-11-05)

- **2026-11-05 16:34** | sisajournal-e.com | [K바이오 10대장 점검⑥] 알테오젠, 소송 이겨도 시간이 문제···시장 ...
  - https://www.sisajournal-e.com/news/articleView.html?idxno=424821
- **2026-11-05 15:16** | job-post.co.kr | 알테오젠 21만1000원·3.43%↑…분기 최대 실적에 시선
  - https://www.job-post.co.kr/news/articleView.html?idxno=236798
- **2026-11-05 14:55** | news1.kr | AI 데이터센터 규제 우려…코스피·코스닥 동반 '매도 사이드카'
  - https://www.news1.kr/finance/market-exr/6344347
"""
DISCLOSURES = json.dumps({"items": [
    {"date": "2026-10-28", "title": "정정신고서제출요구( 2026.10.19. 제출 증권신고서(합병) )", "filer": "금융감독원",
     "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261028000001"},
]}, ensure_ascii=False)
SOURCES = ci.numbered_sources(ci.parse_news(NEWS), ci.parse_disclosures(DISCLOSURES))

EARNINGS = ci.Issue(title="분기 최대 실적", summary="3분기 실적이 분기 기준 최대치로 보도됐다.",
                    source_ids=["N2"], evidence="분기 최대 실적에 시선")


class _Structured:
    def __init__(self, result):
        self.result, self.prompts = result, []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.unit
def test_news_and_disclosures_are_numbered_from_the_fetched_data():
    assert list(SOURCES) == ["N1", "N2", "N3", "D1"]
    assert SOURCES["N2"] == {"kind": "news", "date": "2026-11-05", "source": "job-post.co.kr",
                             "title": "알테오젠 21만1000원·3.43%↑…분기 최대 실적에 시선",
                             "url": "https://www.job-post.co.kr/news/articleView.html?idxno=236798"}
    assert SOURCES["D1"]["kind"] == "disclosure" and SOURCES["D1"]["source"] == "금융감독원"


@pytest.mark.unit
@pytest.mark.parametrize("text", ["", "조회 실패", "[prefetch failed: boom]", "최근 30일간 공시가 없습니다."])
def test_unreadable_fetch_results_yield_no_sources(text):
    assert ci.parse_news(text) == [] and ci.parse_disclosures(text) == []


@pytest.mark.unit
def test_a_verified_issue_carries_sources_taken_from_the_fetched_data():
    out = ci.verify_issues([EARNINGS], SOURCES)
    assert out[0]["title"] == "분기 최대 실적"
    assert out[0]["sources"] == [{"id": "N2", **SOURCES["N2"]}]   # 제목·링크는 모델이 쓰지 않는다


@pytest.mark.unit
def test_quote_may_come_from_a_disclosure_title():
    merger = ci.Issue(title="합병 증권신고서 정정 요구", summary="금융감독원이 합병 증권신고서의 정정을 요구했다.",
                      source_ids=["D1"], evidence="2026.10.19. 제출 증권신고서(합병)")
    assert ci.verify_issues([merger], SOURCES)[0]["sources"][0]["kind"] == "disclosure"


@pytest.mark.unit
@pytest.mark.parametrize("change", [
    {"source_ids": ["N9"]},                                # 조회하지 않은 번호
    {"source_ids": []},                                    # 근거 번호 없음
    {"evidence": "사상 최대 실적을 기록했다는 보도"},               # 헤드라인에 없는 인용
    {"source_ids": ["N1"]},                                # 인용구가 다른 자료의 제목에 있음
    {"evidence": "분기 최대"},                               # 인용이 너무 짧음
    {"evidence": "소송 이겨도 시간이 문제···시장 ..."},          # 줄임표 포함 인용
    {"title": "가" * 41},
    {"summary": ""},
])
def test_an_issue_that_cannot_be_checked_is_dropped(change):
    assert ci.verify_issues([EARNINGS.model_copy(update=change)], SOURCES) == []


@pytest.mark.unit
def test_quote_of_a_truncated_headline_is_checked_against_the_visible_part():
    lawsuit = ci.Issue(title="소송 일정", summary="특허 소송 결과가 나와도 시간이 걸린다는 분석이 있다.",
                       source_ids=["N1"], evidence="알테오젠, 소송 이겨도 시간이 문제")
    assert ci.verify_issues([lawsuit], SOURCES)[0]["sources"][0]["id"] == "N1"


@pytest.mark.unit
def test_at_most_three_distinct_issues_and_ids_are_normalised():
    issues = [EARNINGS.model_copy(update={"title": t, "source_ids": ["n2", "N2"]}) for t in ("가", "가", "나", "다", "라")]
    out = ci.verify_issues(issues, SOURCES)
    assert [i["title"] for i in out] == ["가", "나", "다"] and len(out[0]["sources"]) == 1


@pytest.mark.unit
def test_extract_prompts_with_numbered_sources_and_returns_verified_issues():
    llm = _Structured(ci.IssueList(issues=[
        EARNINGS, ci.Issue(title="지어낸 이슈", summary="없는 사건", source_ids=["N1"], evidence="존재하지 않는 제목입니다 정말")]))
    out = ci.extract_issues(llm, "Company: 알테오젠", NEWS, DISCLOSURES)
    assert out["status"] == "ok" and [i["title"] for i in out["issues"]] == ["분기 최대 실적"]
    assert "[N2] 2026-11-05 · job-post.co.kr · 알테오젠 21만1000원" in llm.prompts[0]
    assert "[D1]" in llm.prompts[0] and "Company: 알테오젠" in llm.prompts[0]
    assert "한 글자도 바꾸지 않고" in llm.prompts[0]


@pytest.mark.unit
def test_extract_statuses():
    none = ci.extract_issues(_Structured(ci.IssueList(issues=[])), "", NEWS, DISCLOSURES)
    assert (none["status"], none["issues"]) == ("none", [])
    assert ci.extract_issues(_Structured(RuntimeError("boom")), "", NEWS, DISCLOSURES)["status"] == "error"
    assert ci.extract_issues(None, "", NEWS, DISCLOSURES)["status"] == "unavailable"
    llm = _Structured(ci.IssueList(issues=[EARNINGS]))
    assert ci.extract_issues(llm, "", "조회 실패", "조회 실패")["status"] == "unavailable" and llm.prompts == []


@pytest.mark.unit
def test_disclosures_alone_are_enough_to_extract():
    merger = ci.Issue(title="합병 증권신고서 정정 요구", summary="정정을 요구했다.", source_ids=["D1"],
                      evidence="증권신고서(합병)")
    out = ci.extract_issues(_Structured(ci.IssueList(issues=[merger])), "", "뉴스 없음", DISCLOSURES)
    assert out["status"] == "ok"


def _state(issues):
    state = {"fundamentals_data": {"business": json.dumps({"company_name": "알테오젠", "overview": "당사는 바이오기업입니다."},
                                                          ensure_ascii=False)}}
    if issues is not None:
        state["company_issues"] = issues
    return state


@pytest.mark.unit
def test_report_lists_each_issue_with_its_sources_as_links():
    issues = ci.verify_issues([EARNINGS], SOURCES)
    html = company_overview_html("196170", _state({"status": "ok", "issues": issues, "reason": ""}))
    assert "현재 핵심 이슈" in html and "<strong>분기 최대 실적</strong>" in html
    assert '<a href="https://www.job-post.co.kr/news/articleView.html?idxno=236798" rel="noopener">' in html
    assert "[뉴스] 2026-11-05 · job-post.co.kr · 알테오젠 21만1000원" in html
    assert html.index("현재 핵심 이슈") < html.index("당사는")


@pytest.mark.unit
def test_report_escapes_model_text_and_refuses_non_http_links():
    bad = {"title": "<b>제목</b>", "summary": "<script>x</script>", "evidence": "e",
           "sources": [{"id": "N1", "kind": "news", "date": "d", "source": "s", "title": "t", "url": "javascript:alert(1)"}]}
    html = company_overview_html("196170", _state({"status": "ok", "issues": [bad], "reason": ""}))
    assert "<script>" not in html and "&lt;b&gt;제목&lt;/b&gt;" in html and "javascript:" not in html


@pytest.mark.unit
@pytest.mark.parametrize("status", ["none", "error", "unavailable"])
def test_report_states_why_there_is_no_issue(status):
    html = company_overview_html("196170", _state({"status": status, "issues": [], "reason": "사유 문구"}))
    assert "현재 핵심 이슈" in html and "확인되지 않음 — 사유 문구" in html


@pytest.mark.unit
def test_report_without_an_issue_record_omits_the_block():
    assert "현재 핵심 이슈" not in company_overview_html("196170", _state(None))
