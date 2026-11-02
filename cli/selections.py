"""한 run 의 대화형 선택: ticker, date, analysts, depth, 모델, effort.

TradingAgents-KR 포크는 Claude Code 헤드리스가 유일 LLM 백엔드이므로 (ADR-0001)
provider 선택 흐름은 제거되었습니다 (Task 2 #21). 사용자는 ticker/date/언어/
analysts/depth/model/effort 만 고르면 됩니다 — 백엔드 URL, 지역, API 키 입력
단계가 전부 사라졌습니다.
"""

import datetime
import os
from pathlib import Path

import typer
from rich.align import Align
from rich.panel import Panel

from cli import updates
from cli.display import console
from cli.prefs import load_last_run, sanitize, save_last_run
from cli.prompts import (
    ask_effort,
    ask_output_language,
    detect_asset_type,
    get_ticker,
    parse_analysis_date,
    parse_analysts,
    parse_ticker,
    select_analysts,
    select_deep_thinking_agent,
    select_research_depth,
    select_shallow_thinking_agent,
)
from tradingagents.default_config import DEFAULT_CONFIG


def get_user_selections(flags=None):
    """Run 설정을 대화형으로 수집. 지난 번 답을 디폴트로 제시."""
    selections = _prompt_selections(load_last_run(), flags or {})
    save_last_run(selections)
    return selections


def depth_from_env() -> bool:
    """두 라운드 수가 전부 환경변수로 설정되어 있으면 depth 질문 skip."""
    return bool(os.environ.get("TRADINGAGENTS_MAX_DEBATE_ROUNDS")
                and os.environ.get("TRADINGAGENTS_MAX_RISK_ROUNDS"))


def unattended_gaps(flags) -> list[str]:
    """터미널 없는 run 에 필요한 환경변수/플래그 중 비어있는 것들."""
    env = os.environ.get
    gaps = [f"--{name}" for name in ("ticker", "date", "analysts") if flags.get(name) is None]
    gaps += [f"--{name} or --no-{name}" for name in ("save", "show") if flags.get(name) is None]
    if not env("TRADINGAGENTS_OUTPUT_LANGUAGE"):
        gaps.append("TRADINGAGENTS_OUTPUT_LANGUAGE")
    if not depth_from_env():
        gaps.append("TRADINGAGENTS_MAX_DEBATE_ROUNDS and TRADINGAGENTS_MAX_RISK_ROUNDS")
    if not (env("TRADINGAGENTS_QUICK_THINK_LLM") or env("TRADINGAGENTS_DEEP_THINK_LLM")):
        gaps.append("TRADINGAGENTS_QUICK_THINK_LLM or TRADINGAGENTS_DEEP_THINK_LLM")
    return gaps


def _from_flag(parse, value, *args):
    """플래그 값을 프롬프트와 동일한 검증으로 통과시킴. 부적합이면 run 종료."""
    try:
        return parse(value, *args)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None


def _prompt_selections(prefs, flags):
    """선택 단계를 순회. ``prefs`` 가 pre-fill, flags/환경변수가 skip."""
    with open(Path(__file__).parent / "static" / "welcome.txt", encoding="utf-8") as f:
        welcome_ascii = f.read()

    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]TradingAgents-KR: 한국 증시 멀티에이전트 LLM 트레이딩 프레임워크 - CLI[/bold green]\n\n"
    welcome_content += "[bold]Workflow Steps:[/bold]\n"
    welcome_content += "I. Analyst Team → II. Research Team → III. Trader → IV. Risk Management → V. Portfolio Management\n\n"
    welcome_content += (
        "[dim]LLM 백엔드: Claude Code 헤드리스 (ADR-0001)[/dim]"
    )

    welcome_box = Panel(
        welcome_content,
        border_style="green",
        padding=(1, 2),
        title="Welcome to TradingAgents-KR",
        subtitle="Korean Market Multi-Agents LLM Trading Framework",
    )
    console.print(Align.center(welcome_box))
    console.print()
    console.print()

    # What's new 는 터미널이 있을 때만. unattended run 은 skip.
    if updates.enabled():
        updates.show(console)
        updates.start_background_refresh()

    def create_question_box(title, prompt, default=None):
        box_content = f"[bold]{title}[/bold]\n"
        box_content += f"[dim]{prompt}[/dim]"
        if default:
            box_content += f"\n[dim]Default: {default}[/dim]"
        return Panel(box_content, border_style="blue", padding=(1, 2))

    # Step 1: Ticker symbol
    if flags.get("ticker") is not None:
        selected_ticker = _from_flag(parse_ticker, flags["ticker"])
        console.print(f"[green]✓ Ticker from --ticker:[/green] {selected_ticker}")
    else:
        console.print(
            create_question_box(
                "Step 1: Ticker Symbol",
                "Enter the ticker (한국 종목코드 6자리 또는 상류 포맷)",
                "005930",
            )
        )
        selected_ticker = get_ticker()
    asset_type = detect_asset_type(selected_ticker)
    if asset_type.value != "stock":
        console.print(
            f"[green]Detected asset type:[/green] {asset_type.value}"
        )

    # Step 2: Analysis date
    if flags.get("date") is not None:
        analysis_date = _from_flag(parse_analysis_date, flags["date"])
        console.print(f"[green]✓ Analysis date from --date:[/green] {analysis_date}")
    else:
        default_date = datetime.datetime.now().strftime("%Y-%m-%d")
        console.print(
            create_question_box(
                "Step 2: Analysis Date",
                "Enter the analysis date (YYYY-MM-DD)",
                default_date,
            )
        )
        analysis_date = get_analysis_date()

    # Step 3: Output language (TRADINGAGENTS_OUTPUT_LANGUAGE 로 skip)
    if os.environ.get("TRADINGAGENTS_OUTPUT_LANGUAGE"):
        output_language = DEFAULT_CONFIG["output_language"]
        console.print(
            f"[green]✓ Output language from environment:[/green] {output_language}"
        )
    else:
        console.print(
            create_question_box(
                "Step 3: Output Language",
                "Select the language for analyst reports and final decision"
            )
        )
        output_language = ask_output_language(prefs.get("output_language"))

    # Step 4: Select analysts
    prefs = sanitize(prefs, asset_type.value)
    if flags.get("analysts") is not None:
        selected_analysts = _from_flag(parse_analysts, flags["analysts"], asset_type)
    else:
        console.print(
            create_question_box(
                "Step 4: Analysts Team", "Select your LLM analyst agents for the analysis"
            )
        )
        selected_analysts = select_analysts(asset_type, prefs.get("analysts"))
    console.print(
        f"[green]Selected analysts:[/green] {', '.join(analyst.value for analyst in selected_analysts)}"
    )

    # Step 5: Research depth (양쪽 라운드 수가 env 로 설정되면 skip)
    if depth_from_env():
        selected_research_depth = DEFAULT_CONFIG["max_debate_rounds"]
        console.print(
            f"[green]✓ Research depth from environment:[/green] "
            f"{DEFAULT_CONFIG['max_debate_rounds']} debate / "
            f"{DEFAULT_CONFIG['max_risk_discuss_rounds']} risk rounds"
        )
    else:
        console.print(
            create_question_box(
                "Step 5: Research Depth", "Select your research depth level"
            )
        )
        selected_research_depth = select_research_depth(prefs.get("research_depth"))

    # Step 6: Thinking agents (양쪽 중 하나라도 env 로 설정되면 skip)
    if os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM") or os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM"):
        selected_shallow_thinker = DEFAULT_CONFIG["quick_think_llm"]
        selected_deep_thinker = DEFAULT_CONFIG["deep_think_llm"]
        console.print(
            f"[green]✓ Thinking agents from environment:[/green] "
            f"quick={selected_shallow_thinker}, deep={selected_deep_thinker}"
        )
    else:
        console.print(
            create_question_box(
                "Step 6: Thinking Agents (Claude models)",
                "Select Claude models for quick (analyst) and deep (manager/trader) tiers"
            )
        )
        selected_shallow_thinker = select_shallow_thinking_agent(prefs.get("quick_think_llm"))
        selected_deep_thinker = select_deep_thinking_agent(prefs.get("deep_think_llm"))

    # Step 7: Effort levels — Claude Code `--effort` per tier.
    # TRADINGAGENTS_EFFORT / TRADINGAGENTS_QUICK_EFFORT 로 각각 skip.
    if os.environ.get("TRADINGAGENTS_EFFORT"):
        selected_deep_effort = DEFAULT_CONFIG["effort"]
        console.print(
            f"[green]✓ Deep tier effort from environment:[/green] {selected_deep_effort}"
        )
    else:
        console.print(
            create_question_box(
                "Step 7a: Deep Tier Effort",
                "Select --effort for deep tier (researchers/managers/trader/debaters)"
            )
        )
        selected_deep_effort = ask_effort("deep", prefs.get("effort"))

    if os.environ.get("TRADINGAGENTS_QUICK_EFFORT"):
        selected_quick_effort = DEFAULT_CONFIG["quick_effort"]
        console.print(
            f"[green]✓ Quick tier effort from environment:[/green] {selected_quick_effort}"
        )
    else:
        console.print(
            create_question_box(
                "Step 7b: Quick Tier Effort",
                "Select --effort for quick tier (analysts)"
            )
        )
        selected_quick_effort = ask_effort("quick", prefs.get("quick_effort"))

    return {
        "ticker": selected_ticker,
        "asset_type": asset_type.value,
        "analysis_date": analysis_date,
        "analysts": selected_analysts,
        "research_depth": selected_research_depth,
        "llm_provider": "claude-code",
        "quick_think_llm": selected_shallow_thinker,
        "deep_think_llm": selected_deep_thinker,
        "effort": selected_deep_effort,
        "quick_effort": selected_quick_effort,
        "output_language": output_language,
    }


def get_analysis_date():
    """사용자 입력에서 분석 날짜를 받음."""
    while True:
        date_str = typer.prompt(
            "", default=datetime.datetime.now().strftime("%Y-%m-%d")
        )
        try:
            return parse_analysis_date(date_str)
        except ValueError as exc:
            console.print(f"[red]Error: {exc}[/red]")
