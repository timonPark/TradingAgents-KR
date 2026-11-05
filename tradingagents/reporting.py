"""Reusable report-tree writer shared by the CLI and the programmatic API.

Writes a run's per-section markdown (analysts, research, trading, risk,
portfolio) plus a consolidated ``complete_report.md`` under ``save_path``. The
CLI and ``TradingAgentsGraph.save_reports`` both call this, so a headless / API
run produces the same on-disk report tree a CLI run does.
"""

from datetime import datetime
from pathlib import Path

from tradingagents.agents.rating import display_rating, run_rating


def analyst_names(keys) -> list[str]:
    """The analysts as users select them: the sentiment analyst's key is "social"."""
    return ["sentiment" if key == "social" else key for key in keys or []]


def _header(ticker: str, final_state: dict, settings: dict | None) -> str:
    """리포트 제목과 생성 내역: 분석일, 버전, 모델, 분석가, vendor.

    Task 9c (#82): KRX 하드 포크 (ADR-0003) 에 따라 사용자 노출 라벨은 한국어.
    내부 state 키 (``trade_date``, ``market_report`` 등) 는 영어 유지 — 코드
    식별자 i18n 경계.
    """
    lines = [f"# 트레이딩 분석 보고서: {ticker}", ""]
    if final_state.get("trade_date"):
        lines.append(f"- 분석일: {final_state['trade_date']}")
    if final_state.get("final_trade_decision"):
        lines.append(f"- 등급: {display_rating(run_rating(final_state))}")
    lines.append(f"- 생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if settings:
        s = settings.get
        # Task 2 (#21): deep_think_provider / quick_think_provider 는 제거됨.
        # Claude Code 가 유일 provider 이므로 llm_provider 하나로 모든 티어 표현.
        provider = s("llm_provider", "?")
        models = (f"{provider}, deep {s('deep_think_llm', '?')} "
                  f"(effort {s('effort', '?')}), "
                  f"quick {s('quick_think_llm', '?')} "
                  f"(effort {s('quick_effort', '?')})")
        lines.append(f"- TradingAgents {s('version', '?')}: {models}")
        lines.append(f"- 분석가: {', '.join(analyst_names(s('analysts')))}; "
                     f"리서치 토론 라운드 {s('max_debate_rounds', '?')}, "
                     f"리스크 토론 라운드 {s('max_risk_discuss_rounds', '?')}")
        vendors = {**(s("data_vendors") or {}), **(s("tool_vendors") or {})}
        if vendors:
            lines.append("- 데이터 vendor: " + ", ".join(f"{k} {v}" for k, v in vendors.items()))
    if final_state.get("memory_note"):
        lines.append(f"- 메모리 로그: {final_state['memory_note']}")
    return "\n".join(lines) + "\n\n"


# 리포트 섹션 순서: (한국어 헤딩, 폴더 영문, [(에이전트 한국어 표시명, 파일명 영문,
# state 경로 영문)]).
# Task 9c (#82): 사용자 노출 라벨/표시명은 한국어, 파일시스템 경로와 state 키는
# 영어 유지 (i18n 경계).
_SECTIONS = (
    ("I. 분석가 팀 보고서", "1_analysts", (
        ("시장 분석가", "market.md", ("market_report",)),
        ("감성 분석가", "sentiment.md", ("sentiment_report",)),
        ("뉴스 분석가", "news.md", ("news_report",)),
        ("재무 분석가", "fundamentals.md", ("fundamentals_report",)),
    )),
    ("II. 리서치 팀 결정", "2_research", (
        ("강세 리서처", "bull.md", ("investment_debate_state", "bull_history")),
        ("약세 리서처", "bear.md", ("investment_debate_state", "bear_history")),
        ("리서치 매니저", "manager.md", ("investment_plan",)),
    )),
    ("III. 트레이딩 팀 계획", "3_trading", (
        ("트레이더", "trader.md", ("trader_investment_plan",)),
    )),
    ("IV. 리스크 관리 팀 결정", "4_risk", (
        ("공격적 분석가", "aggressive.md", ("risk_debate_state", "aggressive_history")),
        ("보수적 분석가", "conservative.md", ("risk_debate_state", "conservative_history")),
        ("중립적 분석가", "neutral.md", ("risk_debate_state", "neutral_history")),
    )),
    ("V. 포트폴리오 매니저 결정", "5_portfolio", (
        ("포트폴리오 매니저", "decision.md", ("final_trade_decision",)),
    )),
)


def _report_parts(final_state: dict) -> list[tuple[str, str, list[tuple[str, str, str]]]]:
    """The sections with something to say: (heading, folder, [(agent, file, text)])."""
    parts = []
    for heading, folder, agents in _SECTIONS:
        written = []
        for agent, filename, path in agents:
            value = final_state
            for key in path:
                value = (value or {}).get(key)
            if value:
                written.append((agent, filename, value))
        if written:
            parts.append((heading, folder, written))
    return parts


def write_report_tree(final_state: dict, ticker: str, save_path, settings: dict | None = None,
                      html: bool = True) -> Path:
    """Save a completed run's reports to ``save_path``; return the complete-report path.

    ``settings`` (``TradingAgentsGraph.run_settings()``) adds what produced the run
    to the report's header. ``html`` also writes ``complete_report.html``, one
    self-contained page of the same report (#1419).
    Reusing a directory replaces the generated report files, removing sections
    absent from this run and disabled HTML. Other files and directories are kept.
    """
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)
    parts = _report_parts(final_state)
    sections = []
    for heading, folder, written in parts:
        (save_path / folder).mkdir(exist_ok=True)
        for _agent, filename, text in written:
            (save_path / folder / filename).write_text(text, encoding="utf-8")
        content = "\n\n".join(f"### {agent}\n{text}" for agent, _filename, text in written)
        sections.append(f"## {heading}\n\n{content}")

    (save_path / "complete_report.md").write_text(
        _header(ticker, final_state, settings) + "\n\n".join(sections), encoding="utf-8"
    )
    if html:
        from tradingagents.report_html import render_report

        (save_path / "complete_report.html").write_text(
            render_report(ticker, final_state, settings, parts), encoding="utf-8"
        )
    else:
        (save_path / "complete_report.html").unlink(missing_ok=True)

    # Reconcile only the filenames owned by this writer; never clear the tree,
    # since callers may keep notes or other artifacts alongside the reports.
    current_files = {
        (folder, filename)
        for _heading, folder, written in parts
        for _agent, filename, _text in written
    }
    for _heading, folder, agents in _SECTIONS:
        for _agent, filename, _path in agents:
            if (folder, filename) not in current_files:
                (save_path / folder / filename).unlink(missing_ok=True)
    return save_path / "complete_report.md"
