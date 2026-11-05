"""#144: 보고서 차트 — 사전조회 원본 → 정적 SVG.

파서 입력은 가능한 한 **실제 포매터 출력**으로 만든다 (vendor 형식이 바뀌면 여기서 깨진다).
"""

from __future__ import annotations

import json
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


# ---------- #144: 가격 레벨 (거래 계획) ----------

def _levels_state(**overrides):
    from tradingagents.agents.schemas import (
        PortfolioDecision,
        PortfolioRating,
        TraderAction,
        TraderProposal,
        render_pm_decision,
        render_trader_proposal,
    )

    state = {
        "market_data": {"ohlcv": OHLCV},       # 마지막 종가 57,500
        "trader_investment_plan": render_trader_proposal(TraderProposal(
            action=TraderAction.SELL, reasoning="r", entry_price=60000, stop_loss=63000.5)),
        "final_trade_decision": render_pm_decision(PortfolioDecision(
            rating=PortfolioRating.UNDERWEIGHT, executive_summary="s", investment_thesis="t",
            price_target=50000)),
    }
    state.update(overrides)
    return state


@pytest.mark.unit
def test_price_levels_come_from_structured_lines_and_last_close():
    levels = charts.parse_price_levels(_levels_state())
    assert [(lv.kind, lv.value) for lv in levels] == [
        ("current", 57500.0), ("entry", 60000.0), ("stop", 63000.5), ("target", 50000.0),
    ]


@pytest.mark.unit
def test_not_provided_levels_are_skipped_not_read_as_zero():
    from tradingagents.agents.schemas import TraderAction, TraderProposal, render_trader_proposal

    state = _levels_state(trader_investment_plan=render_trader_proposal(
        TraderProposal(action=TraderAction.HOLD, reasoning="r")))
    assert [lv.kind for lv in charts.parse_price_levels(state)] == ["current", "target"]


@pytest.mark.unit
def test_price_levels_are_not_read_from_free_prose():
    state = _levels_state(trader_investment_plan="진입가는 60,000원 정도가 좋아 보입니다.",
                          final_trade_decision="목표가 50,000원")
    assert [lv.kind for lv in charts.parse_price_levels(state)] == ["current"]


@pytest.mark.unit
def test_price_levels_chart_shows_distance_from_current_and_all_labels():
    chart = charts.build_price_levels(_levels_state())
    assert isinstance(chart, Chart)
    for text in ("현재가 57,500원", "진입가 60,000원 (+4.3%)", "손절가 63,000원 (+9.6%)", "목표가 50,000원 (-13.0%)"):
        assert text in chart.svg
    assert 'aria-label="가격 레벨:' in chart.svg and 'viewBox="0 0 660 300"' in chart.svg


@pytest.mark.unit
def test_price_level_labels_do_not_overlap_when_prices_are_close():
    from tradingagents.charts import PriceLevel, price_levels_chart

    chart = price_levels_chart([
        PriceLevel("current", "현재가", 57500), PriceLevel("entry", "진입가", 57600),
        PriceLevel("stop", "손절가", 57550), PriceLevel("target", "목표가", 100000),
    ])
    ys = sorted(float(y) for y in re.findall(r'<text x="[\d.]+" y="([\d.]+)"', chart.svg))
    assert all(b - a >= 17.9 for a, b in zip(ys, ys[1:], strict=False))
    assert max(ys) < 300


@pytest.mark.unit
def test_price_levels_need_two_levels():
    from tradingagents.charts import PriceLevel, price_levels_chart

    assert price_levels_chart([PriceLevel("current", "현재가", 1)]) is None
    assert price_levels_chart([]) is None


@pytest.mark.unit
def test_price_levels_gap_only_when_a_trader_stage_gave_nothing_to_draw():
    nothing = {"trader_investment_plan": "최종 거래 제안: **보유**", "final_trade_decision": "**등급**: 보유"}
    gap = charts.build_price_levels(nothing)
    assert isinstance(gap, ChartGap) and "제시하지 않았" in gap.reason
    # 트레이더 단계도, 그릴 가격도 없으면 영역 자체를 만들지 않는다
    assert charts.build_price_levels({"final_trade_decision": "**등급**: 보유"}) is None
    assert charts.build_price_levels({}) is None


# ---------- #149: 재무 차트 (DART 표준 계정 ID 기반) ----------

def _fin(**accounts):
    """``dart.get_financial_accounts`` 가 돌려주는 JSON 과 같은 모양 (값은 원)."""
    import json

    return json.dumps({
        "year": 2026, "report": "반기보고서", "period": "반기 누적 (1~6월)", "basis": "연결", "unit": "원",
        "accounts": {k: {"name": k, "value": v} for k, v in accounts.items()},
    }, ensure_ascii=False)


_FULL = {
    "revenue": 18_687_443_966, "gross_profit": 5_650_725_225, "operating_income": -986_018_595,
    "net_income": 1_922_976_626, "cash_begin": 3_815_574_106, "cfo": -4_713_250_282,
    "cfi": 6_050_719_351, "cff": -767_821_802, "cash_end": 4_502_405_775,
}


@pytest.mark.unit
def test_parse_financial_accounts_reads_json_and_rejects_failure_text():
    assert charts.parse_financial_accounts(_fin(revenue=1))["accounts"]["revenue"]["value"] == 1
    for text in ("", "조회된 재무제표가 없습니다.", "[DART 조회 실패: x]", "[1, 2]", '{"no": "accounts"}'):
        assert charts.parse_financial_accounts(text) is None


@pytest.mark.unit
def test_income_waterfall_ties_out_and_shows_losses_below_zero():
    chart = charts.income_waterfall(charts.parse_financial_accounts(_fin(**_FULL)))
    assert isinstance(chart, Chart) and chart.title == "손익 폭포"
    # 단위 억 원: 매출 186.9, 매출원가 -130.4, 매출총이익 56.5, 판관비 등 -66.4, 영업이익 -9.9 …
    for text in (">186.9<", ">-130.4<", ">56.5<", ">-66.4<", ">-9.9<", ">+29.1<", ">19.2<"):
        assert text in chart.svg, text
    assert "반기 누적 (1~6월)" in chart.note and "연결 재무제표" in chart.note and "억 원" in chart.note
    assert chart.svg.count('class="bar down"') == 2      # 매출원가, 판관비 등
    assert chart.svg.count('class="bar up"') == 1        # 영업외·법인세 등 (+29.1)
    assert chart.svg.count('class="bar total"') == 4     # 매출액, 매출총이익, 영업이익, 순이익


@pytest.mark.unit
def test_income_waterfall_without_gross_profit_skips_the_subtotal():
    accounts = {k: v for k, v in _FULL.items() if k != "gross_profit"}
    chart = charts.income_waterfall(charts.parse_financial_accounts(_fin(**accounts)))
    assert isinstance(chart, Chart) and "매출총이익" not in chart.svg and "영업비용 등" in chart.svg


@pytest.mark.unit
def test_missing_accounts_are_named_not_guessed():
    accounts = {k: v for k, v in _FULL.items() if k != "operating_income"}
    gap = charts.income_waterfall(charts.parse_financial_accounts(_fin(**accounts)))
    assert isinstance(gap, ChartGap) and "영업이익" in gap.reason and "표준 계정 ID" in gap.reason
    cash_gap = charts.cash_bridge(charts.parse_financial_accounts(_fin(revenue=1)))
    assert isinstance(cash_gap, ChartGap) and "기초 현금" in cash_gap.reason and "영업활동 현금흐름" in cash_gap.reason


@pytest.mark.unit
def test_cash_bridge_ties_to_the_ending_balance_with_the_remainder_shown():
    chart = charts.cash_bridge(charts.parse_financial_accounts(_fin(**_FULL)))
    assert isinstance(chart, Chart)
    # 38.2 + (-47.1) + 60.5 + (-7.7) + 환율·기타 1.2 = 45.0
    for text in (">38.2<", ">-47.1<", ">+60.5<", ">-7.7<", ">+1.2<", ">45.0<"):
        assert text in chart.svg, text
    assert "환율·기타" in chart.svg


@pytest.mark.unit
def test_cash_bridge_omits_the_remainder_step_when_it_is_zero():
    accounts = dict(_FULL, cash_end=_FULL["cash_begin"] + _FULL["cfo"] + _FULL["cfi"] + _FULL["cff"])
    chart = charts.cash_bridge(charts.parse_financial_accounts(_fin(**accounts)))
    assert "환율·기타" not in chart.svg


@pytest.mark.unit
def test_large_amounts_use_trillions_without_a_pointless_negative_axis():
    chart = charts.income_waterfall(charts.parse_financial_accounts(_fin(
        revenue=305_372_914_000_000, gross_profit=201_213_884_000_000,
        operating_income=146_725_209_000_000, net_income=118_849_733_000_000)))
    assert "조 원" in chart.note and ">305.37<" in chart.svg
    axis = [float(t) for t in re.findall(r'class="axis" x="[\d.]+" y="[\d.]+" text-anchor="end">(-?[\d.,]+)<', chart.svg)]
    assert min(axis) == 0.0           # 음수가 없는 손익은 0 아래로 축을 늘리지 않는다


@pytest.mark.unit
def test_build_financial_charts_states_a_dart_failure_for_every_chart():
    for text in ("[DART 조회 실패: DART_API_KEY 환경변수가 설정되지 않았습니다.]", "조회된 재무제표가 없습니다."):
        items = charts.build_financial_charts({"accounts": text})
        assert [type(i) for i in items] == [ChartGap, ChartGap, ChartGap]
        assert items[0].reason == text.splitlines()[0][:160]


@pytest.mark.unit
def test_no_fundamentals_data_means_no_chart_area():
    assert charts.build_financial_charts(None) == [] and charts.build_financial_charts({}) == []


@pytest.mark.unit
def test_build_financial_charts_draws_the_income_and_cash_charts_and_gaps_the_missing_liquidity():
    items = charts.build_financial_charts({"accounts": _fin(**_FULL)})
    assert [i.title for i in items] == ["손익 폭포", "현금 흐름 브리지", "유동성 (현금 vs 단기 차입)"]
    assert isinstance(items[0], Chart) and isinstance(items[1], Chart)
    assert isinstance(items[2], ChartGap) and "현금및현금성자산" in items[2].reason   # BS 계정 없음 → 사유


# ---------- #149: 유동성 (현금 vs 단기 차입) ----------

_BS_DOOSAN = {   # 두산에너빌리티 반기 (원)
    "cash": 2_541_888_000_000, "short_term_deposits": 276_246_000_000,
    "short_borrowings": 2_916_241_000_000, "current_long_term_debt": 1_578_345_000_000,
}


@pytest.mark.unit
def test_liquidity_chart_draws_cash_and_debt_bars_with_asset_and_debt_colours():
    chart = charts.liquidity_chart(json.loads(_fin(**_BS_DOOSAN)))
    assert isinstance(chart, Chart)
    assert chart.svg.count('class="bar up"') == 2 and chart.svg.count('class="bar down"') == 2
    for label in ("현금및현금성자산", "단기금융상품", "단기차입금", "유동성장기부채"):
        assert f">{label}<" in chart.svg
    assert "조 원" in chart.note and "현금성 2.82 vs 단기 차입 4.49" in chart.note
    assert "유동성전환사채" in chart.note          # 못 찾은 항목은 부제에 밝힌다
    assert 'class="link"' not in chart.svg         # 독립 막대 — 수준선으로 잇지 않는다
    assert "+" not in "".join(re.findall(r'class="axis val"[^>]*>([^<]*)<', chart.svg))


@pytest.mark.unit
def test_liquidity_chart_includes_convertible_bonds_when_present():
    chart = charts.liquidity_chart(json.loads(_fin(
        cash=4_502_405_775, short_borrowings=1_357_209_246, current_convertible_bonds=2_948_032_257)))
    assert chart.svg.count('class="bar down"') == 2 and ">유동성전환사채<" in chart.svg
    assert "억 원" in chart.note and "단기금융상품" in chart.note   # 단기금융상품은 못 찾은 항목


@pytest.mark.unit
def test_liquidity_chart_without_cash_account_names_the_missing_account():
    gap = charts.liquidity_chart(json.loads(_fin(short_borrowings=1.0)))
    assert isinstance(gap, ChartGap) and "현금및현금성자산" in gap.reason


@pytest.mark.unit
def test_liquidity_chart_without_any_debt_account_is_a_gap_not_a_zero_bar():
    gap = charts.liquidity_chart(json.loads(_fin(cash=1_000_000_000)))
    assert isinstance(gap, ChartGap)
    assert "단기차입금" in gap.reason and "차입이 없는 회사" in gap.reason


@pytest.mark.unit
def test_standalone_bars_do_not_change_the_waterfall_links():
    steps = [("a", 10e8, "total"), ("b", -4e8, "delta"), ("c", 6e8, "total")]
    chart = charts.waterfall_chart("t", steps, note="n", scale=(1e8, "억 원", 1))
    assert chart.svg.count('class="link"') == 2
