"""Report parity: the shared writer produces the report tree for the CLI and the
programmatic API alike (#1037)."""

import re
from types import SimpleNamespace

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import write_report_tree


def _state():
    return {
        "market_report": "MKT",
        "news_report": "NEWS",
        "investment_debate_state": {"bull_history": "BULL"},
        "investment_plan": "RM PLAN",
        "trader_investment_plan": "TRADE",
        "risk_debate_state": {"neutral_history": "NEUTRAL"},
        "final_trade_decision": "PM DECISION",
    }


SETTINGS = {"version": "0.5.2", "llm_provider": "claude-code", "deep_think_llm": "sonnet",
            "quick_think_llm": "haiku", "effort": "high", "quick_effort": "medium",
            "analysts": ["market", "news"], "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 2, "data_vendors": {"core_stock_apis": "yfinance"}}


@pytest.mark.unit
def test_write_report_tree_creates_files(tmp_path):
    out = write_report_tree(_state(), "AAPL", tmp_path)
    assert out.name == "complete_report.md"
    assert (tmp_path / "1_analysts" / "market.md").read_text() == "MKT"
    assert (tmp_path / "1_analysts" / "news.md").read_text() == "NEWS"
    assert (tmp_path / "2_research" / "manager.md").read_text() == "RM PLAN"
    assert (tmp_path / "3_trading" / "trader.md").read_text() == "TRADE"
    assert (tmp_path / "5_portfolio" / "decision.md").read_text() == "PM DECISION"
    complete = out.read_text()
    assert "트레이딩 분석 보고서: AAPL" in complete
    assert "MKT" in complete and "PM DECISION" in complete


@pytest.mark.unit
def test_save_reports_explicit_path(tmp_path):
    graph = SimpleNamespace(run_settings=lambda: SETTINGS)
    out = TradingAgentsGraph.save_reports(graph, _state(), "AAPL", save_path=tmp_path)
    assert (tmp_path / "complete_report.md").exists()
    assert out == tmp_path / "complete_report.md"


@pytest.mark.unit
@pytest.mark.parametrize("empty_value", [None, ""])
def test_save_reports_replaces_previous_run_sections(tmp_path, empty_value):
    graph = SimpleNamespace(run_settings=lambda: SETTINGS)
    first = dict(_state(), trade_date="2026-09-22")
    TradingAgentsGraph.save_reports(graph, first, "AAPL", save_path=tmp_path)
    (tmp_path / "notes.md").write_text("User notes", encoding="utf-8")
    (tmp_path / "1_analysts" / "notes.md").write_text("Analyst notes", encoding="utf-8")

    second = {
        "trade_date": "2026-09-23",
        "market_report": "NEW MARKET",
        "news_report": empty_value,
        "investment_debate_state": {"bull_history": empty_value},
    }
    out = TradingAgentsGraph.save_reports(graph, second, "AAPL", save_path=tmp_path)

    assert (tmp_path / "1_analysts" / "market.md").read_text() == "NEW MARKET"
    for filename in (
        "1_analysts/news.md", "2_research/bull.md", "2_research/manager.md",
        "3_trading/trader.md", "4_risk/neutral.md", "5_portfolio/decision.md",
    ):
        assert not (tmp_path / filename).exists()
    assert (tmp_path / "notes.md").read_text() == "User notes"
    assert (tmp_path / "1_analysts" / "notes.md").read_text() == "Analyst notes"
    assert "NEW MARKET" in out.read_text(encoding="utf-8")
    assert "NEWS" not in out.read_text(encoding="utf-8")
    assert "NEWS" not in (tmp_path / "complete_report.html").read_text(encoding="utf-8")


@pytest.mark.unit
def test_empty_report_removes_previous_sections_and_disabled_html(tmp_path):
    write_report_tree(_state(), "AAPL", tmp_path)
    out = write_report_tree({}, "AAPL", tmp_path, html=False)

    assert list(tmp_path.rglob("*.md")) == [out]
    assert not (tmp_path / "complete_report.html").exists()
    assert "트레이딩 분석 보고서: AAPL" in out.read_text()


@pytest.mark.unit
def test_save_reports_defaults_under_results_dir(tmp_path):
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"results_dir": str(tmp_path)}
    graph.run_settings = lambda: SETTINGS
    out = graph.save_reports(_state(), "AAPL")
    assert out.exists()
    assert out.parent.parent.name == "reports"  # results_dir/reports/AAPL_<stamp>/...
    assert out.parent.name.startswith("AAPL_")



@pytest.mark.unit
def test_the_report_names_the_analysis_date_and_what_produced_it(tmp_path):
    state = dict(_state(), trade_date="2026-09-23")

    header = write_report_tree(state, "NVDA", tmp_path, settings=SETTINGS).read_text().split("## ")[0]

    assert "분석일: 2026-09-23" in header
    assert "TradingAgents 0.5.2" in header
    assert "claude-code, deep sonnet (effort high), quick haiku (effort medium)" in header
    assert "분석가: market, news" in header
    assert "리서치 토론 라운드 1, 리스크 토론 라운드 2" in header
    assert "core_stock_apis yfinance" in header


@pytest.mark.unit
def test_run_settings_record_the_run_without_endpoints_or_paths():
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.selected_analysts = ("market", "news")
    graph.config = {"llm_provider": "claude-code", "deep_think_llm": "sonnet", "quick_think_llm": "haiku",
                    "effort": "high", "quick_effort": "medium",
                    "max_debate_rounds": 1, "max_risk_discuss_rounds": 1, "output_language": "Korean",
                    "data_vendors": {"core_stock_apis": "yfinance"}, "tool_vendors": {},
                    "results_dir": "/home/me/results"}

    settings = graph.run_settings()

    assert settings["analysts"] == ["market", "news"]
    assert settings["deep_think_llm"] == "sonnet"
    assert settings["effort"] == "high"
    # 로컬 경로는 run_settings 에 기록되지 않음.
    assert "/home/me" not in str(settings)


@pytest.mark.unit
def test_a_partial_settings_dict_still_writes_the_report(tmp_path):
    out = write_report_tree(_state(), "AAPL", tmp_path, settings={"llm_provider": "claude-code"})
    assert "claude-code" in out.read_text()


@pytest.mark.unit
def test_run_settings_name_the_version_of_the_running_code():
    import tradingagents
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.selected_analysts, graph.config = ("market",), {}
    assert graph.run_settings()["version"] == tradingagents.__version__


@pytest.mark.unit
@pytest.mark.parametrize("decision, rating", [
    ("**Rating**: Overweight\n\nAdd on weakness.", "Overweight"),
    ("Add on weakness.", "REVIEW"),           # no readable rating is said, not left out
])
def test_the_report_header_names_the_rating(tmp_path, decision, rating):
    state = dict(_state(), final_trade_decision=decision)

    header = write_report_tree(state, "NVDA", tmp_path, settings=SETTINGS).read_text().split("## ")[0]

    assert f"- 등급: {rating}" in header


@pytest.mark.unit
def test_the_header_names_the_analysts_as_users_select_them(tmp_path):
    settings = {**SETTINGS, "analysts": ["market", "social", "news"]}

    write_report_tree(_state(), "NVDA", tmp_path, settings=settings, html=True)

    markdown = (tmp_path / "complete_report.md").read_text(encoding="utf-8")
    assert "market, sentiment, news" in markdown and "social" not in markdown
    page = (tmp_path / "complete_report.html").read_text(encoding="utf-8")
    fields = re.findall(r'<span class="field">([^<]*)</span>', page)
    assert {"market", "sentiment", "news"} <= set(fields) and "social" not in page
