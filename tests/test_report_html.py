"""An optional HTML copy of the report, for readers who do not open Markdown (#1419).

It is one self-contained file: no script, no remote asset, nothing a report's
text can inject; the Markdown report is unchanged.
"""

import re

import pytest

from tradingagents.reporting import write_report_tree

SETTINGS = {"version": "1.2.3", "llm_provider": "claude-code", "deep_think_llm": "sonnet",
            "quick_think_llm": "haiku", "effort": "high", "quick_effort": "medium",
            "analysts": ["market", "news"], "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1, "data_vendors": {"core_stock_apis": "yfinance"}}


def _state(**overrides):
    state = {"trade_date": "2026-09-26",
             "market_report": "# Market view\n\nPrice | Level\n--- | ---\nClose | 181.2\n",
             "news_report": "News text.",
             "final_trade_decision": "**Rating**: Overweight\n\nAdd on weakness."}
    state.update(overrides)
    return state


def _html(tmp_path, **overrides):
    write_report_tree(_state(**overrides), "NVDA", tmp_path, settings=SETTINGS, html=True)
    return (tmp_path / "complete_report.html").read_text(encoding="utf-8")


@pytest.mark.unit
def test_the_html_page_is_written_unless_declined(tmp_path):
    write_report_tree(_state(), "NVDA", tmp_path / "plain", settings=SETTINGS, html=False)
    assert not (tmp_path / "plain" / "complete_report.html").exists()
    write_report_tree(_state(), "NVDA", tmp_path / "default", settings=SETTINGS)
    assert (tmp_path / "default" / "complete_report.html").exists()

    page = _html(tmp_path / "html")
    assert "<h1" in page and "NVDA" in page and "비중 확대" in page and "2026-09-26" in page
    assert '<table>' in page and "181.2" in page


@pytest.mark.unit
def test_the_markdown_report_is_the_same_with_or_without_html(tmp_path):
    write_report_tree(_state(), "NVDA", tmp_path / "a", settings=SETTINGS, html=False)
    write_report_tree(_state(), "NVDA", tmp_path / "b", settings=SETTINGS)
    def undated(path):
        return re.sub(r"- Generated: .*\n", "", path.read_text(encoding="utf-8"))

    assert undated(tmp_path / "a" / "complete_report.md") == undated(tmp_path / "b" / "complete_report.md")


@pytest.mark.unit
def test_the_page_loads_nothing_and_runs_nothing(tmp_path):
    page = _html(tmp_path)
    assert "Content-Security-Policy" in page and "default-src 'none'" in page
    assert "<script" not in page.lower()
    assert not re.search(r'<(img|link|iframe|object|embed)\b', page, re.IGNORECASE)


@pytest.mark.unit
def test_report_text_cannot_inject_markup_or_fetch_anything(tmp_path):
    hostile = ("<script>alert(1)</script> <img src=x onerror=alert(1)>\n\n"
               "![pixel](https://tracker.example/p.png) [x](javascript:alert(1))")
    page = _html(tmp_path, news_report=hostile)
    assert "<script>alert" not in page and "<img" not in page.lower()
    assert "tracker.example/p.png" not in re.findall(r'(?:src|href)="([^"]*)"', page)
    assert 'href="javascript:' not in page


@pytest.mark.unit
def test_header_values_are_escaped(tmp_path):
    write_report_tree(_state(), "<b>NV</b>", tmp_path, settings={**SETTINGS, "deep_think_llm": "<i>m</i>"}, html=True)
    page = (tmp_path / "complete_report.html").read_text(encoding="utf-8")
    assert "<b>NV</b>" not in page and "&lt;b&gt;NV&lt;/b&gt;" in page and "<i>m</i>" not in page


@pytest.mark.unit
def test_an_agent_s_own_headings_sit_below_its_heading(tmp_path):
    page = _html(tmp_path)
    assert page.count("<h1") == 1                     # only the report's title
    assert re.search(r"<h4[^>]*>Market view</h4>", page)


def _fields(fragment):
    return re.findall(r'<span class="field">([^<]*)</span>', fragment)


@pytest.mark.unit
def test_run_details_show_each_value_as_its_own_field(tmp_path):
    # Task 2 (#21): deep_think_provider 는 제거됨. 모든 티어가 claude-code.
    # Task 5b (#48): fundamental_data 는 DART 단일 vendor.
    settings = {**SETTINGS, "deep_think_llm": "opus",
                "data_vendors": {"core_stock_apis": "yfinance", "fundamental_data": "dart"}}
    write_report_tree(_state(), "NVDA", tmp_path, settings=settings, html=True)
    page = (tmp_path / "complete_report.html").read_text(encoding="utf-8")
    header = page[page.index("<header"):page.index("</header>")]
    for value in ("claude-code", "opus", "haiku", "market", "news",
                  "dart", "yfinance"):
        assert value in _fields(header)
    # Vendors are named by what they serve.
    assert "Prices" in header and "Fundamentals" in header and "fundamental_data" not in header


@pytest.mark.unit
def test_the_contents_name_each_section_once_and_list_its_agents_beneath(tmp_path):
    page = _html(tmp_path)
    nav = page[page.index('<nav class="contents"'):page.index("</nav>")]
    assert "<ol" not in nav                     # no list numbers beside the sections' own I-V
    # Task 9c (#82): 섹션/에이전트 표시명 한국어화. 로마 숫자는 영어 유지.
    assert re.search(r'<a href="#s1"><span class="num">I</span>\s*<span class="label">분석가 팀 보고서</span></a>', nav)
    assert re.search(r'<a href="#s1-1"><span class="bar"></span>\s*<span class="label">시장 분석가</span></a>', nav)


@pytest.mark.unit
def test_the_section_rail_opens_on_hover_and_keyboard_focus(tmp_path):
    page = _html(tmp_path)
    css = page[page.index("<style>"):page.index("</style>")]
    # Wide screens: a rail centred on the left edge whose names are hidden from
    # sight only (still read by screen readers) until it is pointed at or focused.
    assert "top: 50%" in css and "translateY(-50%)" in css
    assert ".contents:hover .label" in css and ".contents:focus-within .label" in css
    assert "display: none" not in css.split(".contents .label", 1)[1].split("}", 1)[0]


@pytest.mark.unit
def test_the_sections_stay_within_reach(tmp_path):
    page = _html(tmp_path)
    nav = page[page.index('<nav class="contents"'):page.index("</nav>")]
    assert "<h2" not in nav                                         # the list needs no heading
    assert 'id="top"' in page and 'href="#top"' in page             # a way back on small screens
    assert ".contents { position: fixed;" in page                   # beside the text on wide ones


@pytest.mark.unit
def test_the_page_heading_is_the_ticker_and_its_rating(tmp_path):
    page = _html(tmp_path)
    heading = re.search(r"<h1>(.*?)</h1>", page).group(1)
    assert re.sub(r"<[^>]+>", "", heading).split() == ["NVDA", "비중", "확대"]


@pytest.mark.unit
def test_the_header_carries_the_official_logo_unaltered(tmp_path):
    from importlib.resources import files

    logo = files("tradingagents").joinpath("assets/tauric-logo.svg").read_text(encoding="utf-8").strip()
    page = _html(tmp_path)
    header = page[page.index("<header"):page.index("</header>")]
    assert logo in header                           # drawn in the page, nothing fetched
    assert 'href="https://tauric.ai"' in header and 'aria-label="Tauric Research"' in header
    assert header.index('class="logo"') < header.index("<h1")   # leads the header, above the title


@pytest.mark.unit
def test_the_page_credits_its_maker_in_a_line_of_text(tmp_path):
    page = _html(tmp_path)
    footer = page[page.index('<footer class="credit">'):page.index("</footer>")]
    assert re.sub(r"<[^>]+>", "", footer).split() == ["TradingAgents", "powered", "by", "Tauric", "Research"]
    # The logo already leads to tauric.ai; the credit leads to the project and the org.
    assert 'href="https://github.com/TauricResearch/TradingAgents"' in footer
    assert 'href="https://github.com/TauricResearch"' in footer and "tauric.ai" not in footer
    assert "<svg" not in footer and 'class="brand"' in footer
    assert page.index("</main>") < page.index('<footer class="credit">')


@pytest.mark.unit
def test_the_packaged_logo_stays_inert(tmp_path):
    # The logo is drawn inside every report, so it may only ever hold shapes:
    # no script, event handler, link, embedded document or external reference.
    from importlib.resources import files

    logo = files("tradingagents").joinpath("assets/tauric-logo.svg").read_text(encoding="utf-8")
    tags = set(re.findall(r"<\s*([a-zA-Z][\w:-]*)", logo))
    assert tags <= {"svg", "path", "rect", "circle", "g", "defs", "clipPath", "linearGradient", "stop"}
    assert not re.search(r"\son\w+\s*=|href|url\(|@import|javascript:|<!entity|<!doctype", logo, re.IGNORECASE)


# ---- #144: 시장 분석가 섹션의 차트 ----

_MARKET_DATA = {
    "ohlcv": "Date,Open,High,Low,Close,Volume,ChangePct\n2026-11-02,1,2,1,100,10,0\n2026-11-03,1,2,1,110,10,10\n",
    "indicators": "",
    "investor_flow": "[KRX 수급 조회 실패: KRX: x; 네이버 증권: y — 수급 데이터 없음]",
}


@pytest.mark.unit
def test_market_section_carries_charts_after_the_analyst_text(tmp_path):
    page = _html(tmp_path, market_data=_MARKET_DATA)
    market = page[page.index('id="s1-1"'):page.index('id="s1-2"')]
    assert 'class="viz"' in market and "<svg" in market
    assert market.index("Market view") < market.index('class="viz-group"')
    # 수집에 실패한 차트는 빈 그래프가 아니라 사유로 남는다
    assert "차트 없음" in market and "수급 조회 실패" in market


@pytest.mark.unit
def test_no_market_data_leaves_the_page_without_a_chart_area(tmp_path):
    page = _html(tmp_path)
    assert 'class="viz-group"' not in page and 'class="viz"' not in page


@pytest.mark.unit
def test_charts_do_not_break_the_self_contained_page(tmp_path):
    page = _html(tmp_path, market_data=_MARKET_DATA)
    assert "<script" not in page.lower()
    assert "default-src 'none'" in page
    assert not re.findall(r'(?:src|href)="https?://(?!tauric\.ai|github\.com)', page)
    assert "--up" in page and ".viz .bar.up" in page      # 색은 페이지 변수


@pytest.mark.unit
def test_charts_only_in_the_market_analyst_section(tmp_path):
    page = _html(tmp_path, market_data=_MARKET_DATA)
    news = page[page.index('id="s1-2"'):]
    assert 'class="viz-group"' not in news.split("<h2")[0]


# ---- #144: 한눈에 보기 · 거시 지표 차트 ----

def _decision_state(**overrides):
    from tradingagents.agents.schemas import (
        PortfolioDecision,
        PortfolioRating,
        ResearchPlan,
        TraderAction,
        TraderProposal,
        render_pm_decision,
        render_research_plan,
        render_trader_proposal,
    )
    state = {
        "investment_plan": render_research_plan(ResearchPlan(
            recommendation=PortfolioRating.OVERWEIGHT, rationale="r", strategic_actions="a")),
        "trader_investment_plan": render_trader_proposal(TraderProposal(
            action=TraderAction.SELL, reasoning="r")),
        "final_trade_decision": render_pm_decision(PortfolioDecision(
            rating=PortfolioRating.UNDERWEIGHT, executive_summary="s", investment_thesis="t")),
    }
    state.update(overrides)
    return state


@pytest.mark.unit
def test_page_opens_with_the_verdict_flow_and_lists_it_in_the_contents(tmp_path):
    page = _html(tmp_path, **_decision_state())
    assert page.index('id="s0"') < page.index('id="s1"')
    glance = page[page.index('id="s0"'):page.index('id="s1"')]
    assert "한눈에 보기" in glance and "▲ 비중 확대" in glance and "▼ 비중 축소" in glance
    assert "<h4>" not in glance
    nav = page[page.index('<nav class="contents"'):page.index("</nav>")]
    assert nav.index('href="#s0"') < nav.index('href="#s1"')


@pytest.mark.unit
def test_no_glance_section_when_fewer_than_two_stages_were_decided(tmp_path):
    page = _html(tmp_path)           # 기본 상태: 최종 결정만 있음
    assert 'id="s0"' not in page and "한눈에 보기" not in page


@pytest.mark.unit
def test_macro_charts_follow_the_news_analyst_text(tmp_path):
    macro = {"treasury_10y": "- **단위**: 연%\n\n| 기간 | 값 |\n|---|---:|\n| 20261103 | 4.0 |\n| 20261104 | 3.9 |\n",
             "cpi": "DATA_UNAVAILABLE: ECOS 요청 실패"}
    page = _html(tmp_path, macro_data=macro)
    news = page[page.index('id="s1-2"'):]
    assert news.index("News text.") < news.index("거시 지표 차트")
    assert "국고채 10년 금리 (연%)" in news and "차트 없음" in news and "ECOS 요청 실패" in news
    market = page[page.index('id="s1-1"'):page.index('id="s1-2"')]
    assert "거시 지표 차트" not in market


@pytest.mark.unit
def test_no_macro_data_leaves_the_news_section_without_charts(tmp_path):
    assert "거시 지표 차트" not in _html(tmp_path)


@pytest.mark.unit
def test_glance_section_carries_price_levels_under_the_verdict_flow(tmp_path):
    from tradingagents.agents.schemas import (
        PortfolioDecision,
        PortfolioRating,
        TraderAction,
        TraderProposal,
        render_pm_decision,
        render_trader_proposal,
    )
    page = _html(
        tmp_path, **_decision_state(
            trader_investment_plan=render_trader_proposal(TraderProposal(
                action=TraderAction.SELL, reasoning="r", entry_price=130, stop_loss=140)),
            final_trade_decision=render_pm_decision(PortfolioDecision(
                rating=PortfolioRating.UNDERWEIGHT, executive_summary="s", investment_thesis="t",
                price_target=90)),
            market_data=_MARKET_DATA,       # 마지막 종가 110
        ),
    )
    glance = page[page.index('id="s0"'):page.index('id="s1"')]
    assert glance.index("에이전트별 판정 흐름") < glance.index("가격 레벨 (거래 계획)")
    assert "진입가 130원 (+18.2%)" in glance and "목표가 90원 (-18.2%)" in glance


# ---- #149: 재무 분석가 섹션의 재무 차트 ----

@pytest.mark.unit
def test_financial_charts_follow_the_fundamentals_text(tmp_path):
    import json

    accounts = json.dumps({"year": 2026, "report": "반기보고서", "period": "반기 누적 (1~6월)",
                           "basis": "연결", "unit": "원", "accounts": {
        "revenue": {"name": "수익", "value": 1.0e10}, "operating_income": {"name": "x", "value": 1.0e9},
        "net_income": {"name": "y", "value": 8.0e8}}})
    page = _html(tmp_path, fundamentals_report="재무 본문.", fundamentals_data={"accounts": accounts})
    fund = page[page.index("재무 본문."):]
    assert fund.index("재무 본문.") < fund.index("재무 차트")
    assert "손익 폭포" in fund and "현금 흐름 브리지" in fund
    assert fund.count("<svg") == 1                     # 손익 폭포만 그려지고
    assert "차트 없음" in fund and "기초 현금" in fund    # 현금 계정이 없는 브리지는 사유로 남는다


@pytest.mark.unit
def test_no_fundamentals_data_leaves_that_section_without_charts(tmp_path):
    assert "재무 차트" not in _html(tmp_path, fundamentals_report="재무 본문.")


# ---------- #161: PDF 변환 — WeasyPrint 는 페이지 CSS 를 인라인 SVG 에 적용하지 않는다 ----------

_BARS = ('<svg viewBox="0 0 100 40" width="300" height="120">'
         '<rect class="bar up" x="5" y="5" width="20" height="30"/>'
         '<rect class="bar down" x="35" y="5" width="20" height="30"/></svg>')


def _page_with(svg):
    from tradingagents.report_html import _CSS

    return f"<html><head><style>{_CSS}</style></head><body><figure class='viz'>{svg}</figure></body></html>"


def _pdf_fill_colors(html):
    import contextlib
    import re as _re
    import zlib

    from weasyprint import HTML

    pdf = HTML(string=html).write_pdf()
    content = b""
    for m in _re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, _re.S):
        with contextlib.suppress(zlib.error):
            content += zlib.decompress(m.group(1))
    return set(_re.findall(rb"([\d.]+ [\d.]+ [\d.]+) rg", content))


@pytest.mark.unit
def test_svg_print_css_has_literal_svg_relative_rules():
    from tradingagents.report_html import svg_print_css

    css = svg_print_css()
    assert ".bar.up{fill: #087a59;}" in css and ".bar.down{fill: #b4372f;}" in css
    assert ".flow.up .node{stroke: #087a59;}" in css and ".lvl.stop line{" in css
    assert "var(" not in css                     # WeasyPrint 는 SVG 안에서 변수를 풀지 못한다
    assert ".viz" not in css and "svg " not in css  # SVG 안에서는 조상 선택자가 맞지 않는다
    assert "scroll" not in css and "figcaption" not in css   # SVG 바깥 규칙은 뺀다
    assert not re.search(r"font:\s", css)        # 단축 속성은 글자를 거대하게 만든다
    assert "font-size: 15px" in css and "font-weight: 600" in css


@pytest.mark.unit
def test_svg_print_css_uses_the_light_palette_not_the_print_override():
    from tradingagents.report_html import svg_print_css

    # 인쇄용 :root 는 --accent 를 검정으로 덮어써 .s1(잉크) 과 .s2(강조) 가 같은 검정이 된다
    assert ".s1{stroke: #1c2126;}" in svg_print_css() and ".s2{stroke: #087a59;}" in svg_print_css()


@pytest.mark.unit
def test_prepare_html_for_pdf_puts_the_style_in_every_svg_and_leaves_the_page_alone():
    from tradingagents.report_html import prepare_html_for_pdf

    html = _page_with(_BARS + _BARS)
    out = prepare_html_for_pdf(html)
    assert out.count("<svg") == 2 and out.count('<svg viewBox="0 0 100 40" width="300" height="120"><style>') == 2
    assert "white-space: nowrap" in out                  # 표지 등급이 갈라지지 않게 (PDF 전용)
    assert html.count("<style>") == 1                    # 입력은 바뀌지 않는다 (문자열 변환)


@pytest.mark.unit
def test_browser_html_is_not_changed_by_the_pdf_preparation(tmp_path):
    html = _html(tmp_path)
    assert html.count("<style>") == 1                      # SVG 안 <style> 이나 PDF 보정 <style> 이 없다
    assert ".masthead .rating { white-space: nowrap; }" not in html


@pytest.mark.unit
def test_pdf_bars_get_their_up_and_down_colours():
    pytest.importorskip("weasyprint")
    from tradingagents.report_html import prepare_html_for_pdf

    html = _page_with(_BARS)
    before = _pdf_fill_colors(html)
    after = _pdf_fill_colors(prepare_html_for_pdf(html))
    assert b"0.031373 0.478431 0.34902" not in before          # 고치기 전: 검정뿐
    assert b"0.031373 0.478431 0.34902" in after and b"0.705882 0.215686 0.184314" in after   # up / down


# ---------- #163: 회사 개요 — 공시 발췌 + 표지 회사명 ----------

import json as _json  # noqa: E402

_BUSINESS = _json.dumps({
    "company_name": "(주)알테오젠", "market": "KOSDAQ", "ceo": "전태연", "established": "20080513",
    "homepage": "www.alteogen.com", "report": "사업보고서 (2025.12)", "rcept_no": "20260323001596",
    "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260323001596",
    "overview": "당사는 바이오기업입니다.\n라이선스 계약으로 마일스톤을 받습니다.",
}, ensure_ascii=False)


def _overview_html(tmp_path, business=_BUSINESS, ticker="196170", **extra):
    state = {"fundamentals_data": {"accounts": "x", "business": business}, **extra}
    write_report_tree(_state(**state), ticker, tmp_path, settings=SETTINGS, html=True)
    return (tmp_path / "complete_report.html").read_text(encoding="utf-8")


@pytest.mark.unit
def test_cover_shows_the_company_name_with_the_ticker(tmp_path):
    html = _overview_html(tmp_path)
    assert '<span class="ticker">알테오젠 <span class="code">196170</span></span>' in html
    assert "<title>알테오젠 2026-09-26" in html            # (주) 접미어는 표지에서 뗀다


@pytest.mark.unit
def test_cover_name_falls_back_to_the_resolved_instrument_context(tmp_path):
    ctx = "The instrument to analyze is `196170`. Resolved identity: Company: 에코프로비엠; Exchange: KOSDAQ."
    html = _overview_html(tmp_path, business="[DART 조회 실패: x]", instrument_context=ctx)
    assert '<span class="ticker">에코프로비엠 <span class="code">196170</span></span>' in html


@pytest.mark.unit
def test_cover_has_only_the_ticker_when_no_name_is_known(tmp_path):
    html = _html(tmp_path)
    assert '<span class="ticker">NVDA</span>' in html and 'class="code"' not in html.split("</h1>")[0]


@pytest.mark.unit
def test_overview_section_shows_the_filing_excerpt_facts_and_source(tmp_path):
    html = _overview_html(tmp_path)
    section = re.search(r'<section id="s-overview".*?</section>', html, re.S).group(0)
    for expected in ("<h2>회사 개요</h2>", "<dd>알테오젠 (196170)</dd>", "<dd>KOSDAQ</dd>",
                     "<dd>전태연</dd>", "<dd>2008-05-13</dd>"):
        assert expected in section
    assert section.count('<p class="text">') == 2 and "마일스톤을 받습니다" in section
    assert 'href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260323001596"' in section
    assert "DART 사업보고서 (2025.12)" in section and "모델이 작성한 글이 아님" in section


@pytest.mark.unit
def test_overview_comes_first_with_a_contents_entry_before_the_glance_section(tmp_path):
    html = _overview_html(tmp_path, **_decision_state())
    assert html.index('id="s-overview"') < html.index('id="s0"') < html.index('id="s1"')
    nav = re.search(r'<nav class="contents".*?</nav>', html, re.S).group(0)
    assert nav.index("회사 개요") < nav.index("한눈에 보기")


@pytest.mark.unit
def test_overview_escapes_markup_from_the_filing(tmp_path):
    bad = _json.loads(_BUSINESS)
    bad["overview"] = "<script>alert(1)</script> 정상 문장"
    bad["company_name"] = "<b>회사</b>"
    html = _overview_html(tmp_path, business=_json.dumps(bad, ensure_ascii=False))
    assert "<script>alert" not in html and "&lt;script&gt;alert(1)" in html
    assert "<b>회사</b>" not in html


@pytest.mark.unit
def test_overview_states_the_reason_when_the_filing_could_not_be_read(tmp_path):
    html = _overview_html(tmp_path, business="조회된 정기보고서가 없습니다.")
    section = re.search(r'<section id="s-overview".*?</section>', html, re.S).group(0)
    assert "회사 개요 없음 — 조회된 정기보고서가 없습니다." in section and "<dl" not in section


@pytest.mark.unit
def test_no_overview_section_when_the_fundamentals_analyst_did_not_run(tmp_path):
    assert "s-overview" not in _html(tmp_path).split("</style>")[1]
