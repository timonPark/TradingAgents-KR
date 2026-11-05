"""#144: 보고서 차트 — 사전조회 원본 → 정적 SVG.

파서 입력은 가능한 한 **실제 포매터 출력**으로 만든다 (vendor 형식이 바뀌면 여기서 깨진다).
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents import charts
from tradingagents.charts import (
    Chart,
    ChartGap,
    InvestorFlow,
    Series,
    build_market_charts,
    histogram_chart,
    investor_flow_chart,
    line_chart,
    parse_indicator,
    parse_investor_flow,
    parse_ohlcv,
    render_charts_html,
)

OHLCV = """# KRX OHLCV for 034020 from 2026-10-28 to 2026-11-05
# Total records: 6

Date,Open,High,Low,Close,Volume,ChangePct
2026-10-28,60000,61000,59000,60500,1000,0.5
2026-10-29,60500,62000,60000,61500,1100,1.6
2026-10-30,61500,62500,61000,61000,900,-0.8
2026-11-02,61000,61500,59000,59500,1200,-2.4
2026-11-03,59500,60000,58000,58500,1300,-1.7
2026-11-04,58500,59000,57000,57500,1400,-1.7
"""

INDICATORS = """## boll values from 2026-11-02 to 2026-11-04:

2026-11-04: 59000.0
2026-11-03: 59800.0
2026-11-02: 60200.0

Bollinger middle.

## boll_ub values from 2026-11-02 to 2026-11-04:

2026-11-04: 62000.0
2026-11-03: 62500.0
2026-11-02: 63000.0

## boll_lb values from 2026-11-02 to 2026-11-04:

2026-11-04: 56000.0
2026-11-03: 57100.0
2026-11-02: 57400.0

## macdh values from 2026-10-31 to 2026-11-04:

2026-11-04: -641.1
2026-11-03: -700.5
2026-11-02: -500.0
2026-11-01: N/A: 영업일 아님 (주말/공휴일)
2026-10-31: N/A: 영업일 아님 (주말/공휴일)

## rsi values from 2026-11-02 to 2026-11-04:

2026-11-04: 28.4
2026-11-03: 31.0
2026-11-02: 35.2
"""


def _krx_flow() -> str:
    """vendor(`pykrx.get_investor_net_purchases`) 가 만드는 KRX 수급 문자열과 같은 방식으로."""
    series = pd.Series(
        {"금융투자": 3.419e10, "투신": -2.437e10, "기관합계": 2.47e9, "기타법인": -2.5e8,
         "개인": 2.598e10, "외국인": -2.813e10, "전체": 0.0},
        name="순매수",
    )
    series.index.name = "투자자구분"
    header = ("**2026-11-05 기준 최근 5 거래일 순매수** "
              "(2026-10-30 ~ 2026-11-05, 단위: 원, 출처: KRX)\n\n")
    return header + series.to_markdown()


def _naver_flow() -> str:
    from tradingagents.dataflows.vendors import naver_investor

    def row(day, f, o, i):
        return {"bizdate": day, "foreignerPureBuyQuant": f, "organPureBuyQuant": o,
                "individualPureBuyQuant": i, "foreignerHoldRatio": "12.77%"}

    resp = MagicMock(status_code=200)
    resp.json.return_value = [row("20261103", "+9,822", "0", "-10,122"),
                              row("20261102", "-21,196", "-6", "+20,695")]
    with patch("tradingagents.dataflows.vendors.naver_investor.requests.get", return_value=resp):
        return naver_investor.get_investor_flow("001210", "2026-11-04", 5)


# ---------- 파서 ----------

@pytest.mark.unit
def test_parse_ohlcv_returns_ascending_closes():
    rows = parse_ohlcv(OHLCV)
    assert rows[0] == ("2026-10-28", 60500.0)
    assert rows[-1] == ("2026-11-04", 57500.0)
    assert len(rows) == 6


@pytest.mark.unit
@pytest.mark.parametrize("text", ["", "[prefetch failed: KeyError: 'x']", "no table here"])
def test_parse_ohlcv_empty_on_failure_text(text):
    assert parse_ohlcv(text) == []


@pytest.mark.unit
def test_parse_indicator_skips_na_and_does_not_mix_similarly_named_blocks():
    macdh = parse_indicator(INDICATORS, "macdh")
    assert macdh == [("2026-11-02", -500.0), ("2026-11-03", -700.5), ("2026-11-04", -641.1)]
    # "boll" 은 "boll_ub"/"boll_lb" 블록을 먹지 않는다
    assert [v for _, v in parse_indicator(INDICATORS, "boll")] == [60200.0, 59800.0, 59000.0]
    assert parse_indicator(INDICATORS, "atr") == []


@pytest.mark.unit
def test_parse_investor_flow_reads_krx_markdown_table():
    flow = parse_investor_flow(_krx_flow())
    assert flow.unit == "원" and flow.source == "KRX"
    assert flow.period == "2026-10-30 ~ 2026-11-05"
    values = dict(flow.rows)
    assert values["외국인"] == pytest.approx(-2.813e10)
    assert values["개인"] == pytest.approx(2.598e10)


@pytest.mark.unit
def test_parse_investor_flow_reads_naver_total_row_in_shares():
    flow = parse_investor_flow(_naver_flow())
    assert flow.unit == "주" and flow.source == "네이버 증권"
    assert dict(flow.rows) == {"외국인": -11374.0, "기관": -6.0, "개인": 10573.0}


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "",
    "[KRX 수급 조회 실패: KRX: x; 네이버 증권: y — 수급 데이터 없음]",
    "최근 수급 데이터가 없습니다.",
])
def test_parse_investor_flow_none_for_failures(text):
    assert parse_investor_flow(text) is None


# ---------- SVG ----------

@pytest.mark.unit
def test_line_chart_is_accessible_inline_svg_with_values():
    chart = line_chart("가격", [Series("종가", [("2026-11-02", 100.0), ("2026-11-03", 110.0)], "s1")])
    assert isinstance(chart, Chart)
    assert chart.svg.startswith("<svg") and 'role="img"' in chart.svg
    assert 'aria-label="가격:' in chart.svg and "110" in chart.svg
    assert "<polyline" in chart.svg
    assert "<script" not in chart.svg and "http" not in chart.svg.replace("http://www.w3.org", "")


@pytest.mark.unit
def test_line_chart_none_without_points():
    assert line_chart("x", []) is None
    assert line_chart("x", [Series("a", [], "s1")]) is None


@pytest.mark.unit
def test_line_chart_flat_series_does_not_divide_by_zero():
    chart = line_chart("flat", [Series("a", [("2026-11-02", 5.0), ("2026-11-03", 5.0)], "s1")])
    assert chart is not None and "nan" not in chart.svg.lower()


@pytest.mark.unit
def test_histogram_colors_follow_sign_and_axis_includes_zero():
    chart = histogram_chart("MACD", [("2026-11-02", -5.0), ("2026-11-03", 3.0)])
    assert chart.svg.count('class="bar down"') == 1 and chart.svg.count('class="bar up"') == 1
    assert 'class="zero"' in chart.svg


@pytest.mark.unit
def test_investor_chart_converts_won_to_eok_and_orders_main_rows_first():
    chart = investor_flow_chart(parse_investor_flow(_krx_flow()))
    assert "억 원" in chart.title
    assert "-281.3" in chart.svg and "+259.8" in chart.svg
    text = re.findall(r'class="axis"[^>]*>([^<]+)<', chart.svg)
    names = [t for t in text if t in ("외국인", "기관합계", "개인", "기타법인", "금융투자", "투신")]
    assert names == ["외국인", "기관합계", "개인", "기타법인", "금융투자", "투신"]
    assert "출처: KRX" in chart.note


@pytest.mark.unit
def test_investor_chart_for_naver_is_in_shares_and_notes_missing_detail():
    chart = investor_flow_chart(parse_investor_flow(_naver_flow()))
    assert "주" in chart.title and "네이버 증권" in chart.note and "기관 세부 구분 없음" in chart.note
    assert "-11,374" in chart.svg


@pytest.mark.unit
def test_investor_chart_none_when_no_rows():
    assert investor_flow_chart(InvestorFlow([], "원", "KRX")) is None


# ---------- 묶음·실패 ----------

@pytest.mark.unit
def test_build_market_charts_draws_every_chart_from_complete_data():
    items = build_market_charts({"ohlcv": OHLCV, "indicators": INDICATORS, "investor_flow": _krx_flow()})
    assert [type(i) for i in items] == [Chart] * 5
    assert [i.title.split(" (")[0] for i in items] == [
        "가격과 이동평균", "볼린저 밴드", "MACD 히스토그램", "RSI", "투자주체별 순매수",
    ]


@pytest.mark.unit
def test_no_market_data_means_no_chart_area():
    assert build_market_charts(None) == []
    assert build_market_charts({}) == []
    assert render_charts_html([]) == ""


@pytest.mark.unit
def test_failed_prefetch_is_a_stated_gap_not_an_empty_chart():
    failed = "[KRX 수급 조회 실패: KRX: 로그인 거부; 네이버 증권: HTTP 500 — 수급 데이터 없음]"
    items = build_market_charts({
        "ohlcv": "[prefetch failed: ConnectionError: boom]", "indicators": "", "investor_flow": failed,
    })
    assert all(isinstance(i, ChartGap) for i in items)
    by_title = {i.title: i.reason for i in items}
    assert "prefetch failed" in by_title["가격과 이동평균"]
    assert "수급 조회 실패" in by_title["투자주체별 순매수"]
    html = render_charts_html(items)
    assert "차트 없음" in html and "<svg" not in html


@pytest.mark.unit
def test_partial_data_draws_what_it_can_and_names_the_rest():
    items = build_market_charts({"ohlcv": OHLCV, "indicators": "", "investor_flow": _krx_flow()})
    kinds = {i.title.split(" (")[0]: type(i) for i in items}
    assert kinds["가격과 이동평균"] is Chart and kinds["투자주체별 순매수"] is Chart
    assert kinds["MACD 히스토그램"] is ChartGap and kinds["RSI"] is ChartGap


@pytest.mark.unit
def test_bollinger_close_covers_only_the_indicator_window():
    items = build_market_charts({"ohlcv": OHLCV, "indicators": INDICATORS, "investor_flow": ""})
    boll = next(i for i in items if isinstance(i, Chart) and i.title.startswith("볼린저"))
    # 지표 창(11-02~11-04)의 종가 3개 + 밴드 3개 = 선 4개, 각 3점
    assert boll.svg.count("<polyline") == 4
    assert "2026-10-28" not in boll.svg


@pytest.mark.unit
def test_html_fragment_escapes_titles_and_reasons():
    html = render_charts_html([ChartGap("<b>x</b>", "<script>alert(1)</script>")])
    assert "<script>" not in html and "&lt;script&gt;" in html and "<b>" not in html


@pytest.mark.unit
def test_module_is_pure_no_io():
    source = Path(charts.__file__).read_text(encoding="utf-8")
    for forbidden in ("import requests", "import socket", "open(", "subprocess"):
        assert forbidden not in source


# ---------- #144: 한국은행(ECOS) 거시 지표 ----------

def _ecos_section(indicator: str = "treasury_10y", rows=None) -> str:
    """실제 vendor(`ecos.get_macro_data`) 포매터 출력."""
    from tradingagents.dataflows.vendors import ecos

    rows = rows or [("20261102", "4.034"), ("20261103", "4.001"), ("20261104", "3.968")]
    payload = {"StatisticSearch": {"row": [
        {"STAT_CODE": "817Y002", "STAT_NAME": "시장금리(일별)", "ITEM_CODE1": "010210000",
         "ITEM_NAME1": "국고채(10년)", "UNIT_NAME": "연%", "TIME": t, "DATA_VALUE": v}
        for t, v in rows]}}
    resp = MagicMock(status_code=200)
    resp.json.return_value = payload
    with patch.dict("os.environ", {"ECOS_API_KEY": "k"}), \
         patch("tradingagents.dataflows.vendors.ecos.get_scrubbed", return_value=resp):
        return ecos.get_macro_data(indicator, "2026-11-05")


@pytest.mark.unit
def test_parse_ecos_section_reads_unit_and_dates_from_the_real_formatter():
    unit, rows = charts.parse_ecos_section(_ecos_section())
    assert unit == "연%"
    assert rows == [("2026-11-02", 4.034), ("2026-11-03", 4.001), ("2026-11-04", 3.968)]


@pytest.mark.unit
def test_parse_ecos_section_monthly_and_comma_values():
    section = _ecos_section("cpi", rows=[("202609", "1,234.5"), ("202610", "1,240.0")])
    assert charts.parse_ecos_section(section)[1] == [("2026-09", 1234.5), ("2026-10", 1240.0)]


@pytest.mark.unit
@pytest.mark.parametrize("text", ["", "DATA_UNAVAILABLE: x", "[prefetch failed: boom]", "표 없음"])
def test_parse_ecos_section_none_without_observations(text):
    assert charts.parse_ecos_section(text) is None


@pytest.mark.unit
def test_macro_charts_follow_display_order_and_title_carries_unit():
    items = charts.build_macro_charts({
        "usd_krw": _ecos_section("usd_krw"), "treasury_10y": _ecos_section(),
    })
    assert [i.title for i in items] == ["국고채 10년 금리 (연%)", "원/달러 환율 (연%)"]
    assert all(isinstance(i, Chart) for i in items)


@pytest.mark.unit
def test_macro_failure_is_a_stated_gap_and_others_still_draw():
    items = charts.build_macro_charts({
        "treasury_10y": _ecos_section(),
        "cpi": "DATA_UNAVAILABLE: ECOS 요청 실패 (HTTP 500)",
        "usd_krw": "[prefetch failed: ConnectionError: boom]",
    })
    kinds = {i.title.split(" (")[0]: i for i in items}
    assert isinstance(kinds["국고채 10년 금리"], Chart)
    assert isinstance(kinds["소비자물가지수"], ChartGap) and "HTTP 500" in kinds["소비자물가지수"].reason
    assert isinstance(kinds["원/달러 환율"], ChartGap) and "prefetch failed" in kinds["원/달러 환율"].reason


@pytest.mark.unit
def test_macro_single_observation_is_a_gap_not_a_dot():
    items = charts.build_macro_charts({"treasury_10y": _ecos_section(rows=[("20261104", "3.968")])})
    assert isinstance(items[0], ChartGap) and "1개" in items[0].reason


@pytest.mark.unit
def test_macro_none_means_no_chart_area():
    assert charts.build_macro_charts(None) == [] and charts.build_macro_charts({}) == []


# ---------- #144: 한눈에 보기 — 판정 흐름 ----------

def _verdict_state(**overrides):
    from tradingagents.agents.schemas import (
        PortfolioDecision,
        PortfolioRating,
        ResearchPlan,
        SentimentBand,
        SentimentReport,
        TraderAction,
        TraderProposal,
        render_pm_decision,
        render_research_plan,
        render_sentiment_report,
        render_trader_proposal,
    )

    state = {
        "sentiment_report": render_sentiment_report(SentimentReport(
            overall_band=SentimentBand.MIXED, overall_score=5.0, confidence="medium", narrative="n")),
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
def test_verdict_flow_reads_the_structured_lines_of_each_stage():
    nodes = charts.build_verdict_flow(_verdict_state())
    assert [(n.role, n.verdict, n.direction) for n in nodes] == [
        ("감성 분석가", "혼조", "level"),
        ("리서치 매니저", "비중 확대", "up"),
        ("트레이더", "매도", "down"),
        ("포트폴리오 매니저", "비중 축소", "down"),
    ]


@pytest.mark.unit
def test_verdict_flow_reads_english_headers_of_older_reports():
    state = _verdict_state(
        sentiment_report="**Overall Sentiment:** **Bearish** (Score: 3.0/10)\n**Confidence:** Low\n\nn",
        investment_plan="**추천**: Hold\n\nr",
        trader_investment_plan="최종 거래 제안: **HOLD**",   # 이전 한국어 보고서: 라벨 한국어, 값 영어
        final_trade_decision="**등급**: Hold\n\ns",
    )
    assert [(n.verdict, n.direction) for n in charts.build_verdict_flow(state)] == [
        ("약세", "down"), ("보유", "level"), ("보유", "level"), ("보유", "level"),
    ]


@pytest.mark.unit
def test_verdict_flow_names_an_unreadable_stage_instead_of_skipping_it():
    nodes = charts.build_verdict_flow(_verdict_state(investment_plan="전략만 있고 추천 줄이 없다"))
    research = next(n for n in nodes if n.role == "리서치 매니저")
    assert (research.verdict, research.direction) == ("판독 불가", "none")


@pytest.mark.unit
def test_verdict_flow_needs_at_least_two_stages():
    assert charts.build_verdict_flow({}) == []
    assert charts.build_verdict_flow({"final_trade_decision": "**등급**: 매수"}) == []


@pytest.mark.unit
def test_verdict_flow_chart_marks_direction_with_symbols_not_only_color():
    chart = charts.verdict_flow_chart(charts.build_verdict_flow(_verdict_state()))
    assert "▲ 비중 확대" in chart.svg and "▼ 매도" in chart.svg and "■ 혼조" in chart.svg
    assert 'aria-label="에이전트별 판정 흐름:' in chart.svg and "→" in chart.note
    assert charts.verdict_flow_chart([]) is None


@pytest.mark.unit
def test_render_charts_html_without_heading_has_no_h4():
    html = render_charts_html([ChartGap("t", "r")], None)
    assert "<h4>" not in html and 'class="viz-group"' in html
