"""#165: 소속 테마 — 공시 발췌에서 근거 문장이 확인되는 테마만 남긴다."""

from __future__ import annotations

import json

import pytest

from tradingagents.agents.analysts import company_themes as ct
from tradingagents.report_html import company_overview_html

OVERVIEW = (
    "당사는 정맥주사(IV) 제형을 피하주사(SC) 제형으로 바꾸는 Hybrozyme 플랫폼 기술을 보유한 바이오 기업입니다.\n"
    "글로벌 제약사와 기술이전 계약을 체결하고 마일스톤과 로열티 수익을 인식합니다."
)
BUSINESS = json.dumps({"company_name": "알테오젠", "report": "사업보고서 (2025.12)", "overview": OVERVIEW},
                      ensure_ascii=False)
PLATFORM = ct.Theme(name="바이오 플랫폼",
                    evidence="정맥주사(IV) 제형을 피하주사(SC) 제형으로 바꾸는 Hybrozyme 플랫폼 기술을 보유한 바이오 기업")


class _Structured:
    """with_structured_output 이 돌려주는 Runnable 의 대역."""

    def __init__(self, result):
        self.result = result
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.unit
def test_a_theme_whose_evidence_is_in_the_filing_is_kept():
    assert ct.verify_themes([PLATFORM], OVERVIEW) == [{"name": "바이오 플랫폼", "evidence": PLATFORM.evidence}]


@pytest.mark.unit
def test_a_theme_with_invented_evidence_is_dropped():
    invented = ct.Theme(name="AI 신약", evidence="인공지능을 이용한 신약 후보물질 발굴 사업을 확대하고 있습니다")
    assert ct.verify_themes([invented, PLATFORM], OVERVIEW) == [
        {"name": "바이오 플랫폼", "evidence": PLATFORM.evidence}]


@pytest.mark.unit
def test_evidence_matches_despite_line_breaks_and_quotes():
    spaced = ct.Theme(name="기술이전", evidence='"글로벌 제약사와 기술이전 계약을\n체결하고 마일스톤과 로열티 수익을 인식합니다"')
    assert ct.verify_themes([spaced], OVERVIEW)[0]["name"] == "기술이전"


@pytest.mark.unit
def test_evidence_too_short_to_prove_anything_is_rejected():
    assert ct.verify_themes([ct.Theme(name="바이오", evidence="바이오 기업")], OVERVIEW) == []


@pytest.mark.unit
def test_at_most_three_distinct_themes_and_no_runaway_names():
    base = PLATFORM.evidence
    themes = [ct.Theme(name=n, evidence=base) for n in ("가", "가", "나", "다", "라")]
    themes.insert(0, ct.Theme(name="x" * 40, evidence=base))
    assert [t["name"] for t in ct.verify_themes(themes, OVERVIEW)] == ["가", "나", "다"]


@pytest.mark.unit
def test_extract_returns_verified_themes_and_prompts_with_the_filing():
    llm = _Structured(ct.ThemeList(themes=[PLATFORM, ct.Theme(name="AI 신약", evidence="존재하지 않는 문장입니다 입니다 입니다")]))
    out = ct.extract_themes(llm, BUSINESS)
    assert out["status"] == "ok"
    assert [t["name"] for t in out["themes"]] == ["바이오 플랫폼"]
    assert "Hybrozyme" in llm.prompts[0] and "한 글자도 바꾸지 말고" in llm.prompts[0]


@pytest.mark.unit
def test_extract_says_none_when_nothing_is_provable():
    out = ct.extract_themes(_Structured(ct.ThemeList(themes=[])), BUSINESS)
    assert (out["status"], out["themes"]) == ("none", [])


@pytest.mark.unit
def test_extract_survives_a_failed_call():
    out = ct.extract_themes(_Structured(RuntimeError("boom")), BUSINESS)
    assert out["status"] == "error" and out["themes"] == []


@pytest.mark.unit
@pytest.mark.parametrize("business", ["조회된 정기보고서가 없습니다.", "", "[DART 조회 실패]"])
def test_extract_does_not_call_the_model_without_a_filing(business):
    llm = _Structured(ct.ThemeList(themes=[PLATFORM]))
    out = ct.extract_themes(llm, business)
    assert out["status"] == "unavailable" and llm.prompts == []


@pytest.mark.unit
def test_extract_is_unavailable_without_structured_output():
    assert ct.extract_themes(None, BUSINESS)["status"] == "unavailable"


def _state(themes):
    data = {"business": BUSINESS}
    if themes is not None:
        data["themes"] = themes
    return {"fundamentals_data": data}


@pytest.mark.unit
def test_report_shows_each_theme_with_its_filing_quote():
    html = company_overview_html("196170", _state(
        {"status": "ok", "themes": [{"name": "바이오 플랫폼", "evidence": "<b>Hybrozyme</b> 플랫폼 기술"}], "reason": ""}))
    assert "소속 테마" in html and "<strong>바이오 플랫폼</strong>" in html
    assert "<q>&lt;b&gt;Hybrozyme&lt;/b&gt; 플랫폼 기술</q>" in html   # 근거는 이스케이프된 원문
    assert html.index("소속 테마") < html.index("당사는")


@pytest.mark.unit
@pytest.mark.parametrize("status", ["none", "error", "unavailable"])
def test_report_states_why_there_is_no_theme(status):
    html = company_overview_html("196170", _state({"status": status, "themes": [], "reason": "사유 문구"}))
    assert "확인되지 않음 — 사유 문구" in html


@pytest.mark.unit
def test_report_without_a_theme_record_omits_the_block():
    assert "소속 테마" not in company_overview_html("196170", _state(None))
