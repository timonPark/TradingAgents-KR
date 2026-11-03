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
    welcome_content += "[bold]워크플로 단계:[/bold]\n"
    welcome_content += "I. 분석가 팀 → II. 리서치 팀 → III. 트레이더 → IV. 리스크 관리 → V. 포트폴리오 관리\n\n"
    welcome_content += (
        "[dim]LLM 백엔드: Claude Code 헤드리스 (ADR-0001)[/dim]"
    )

    welcome_box = Panel(
        welcome_content,
        border_style="green",
        padding=(1, 2),
        title="TradingAgents-KR 에 오신 것을 환영합니다",
        subtitle="한국 증시 멀티에이전트 LLM 트레이딩 프레임워크",
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
            box_content += f"\n[dim]기본값: {default}[/dim]"
        return Panel(box_content, border_style="blue", padding=(1, 2))

    # Step 1: Ticker symbol
    if flags.get("ticker") is not None:
        selected_ticker = _from_flag(parse_ticker, flags["ticker"])
        console.print(f"[green]✓ --ticker 플래그에서 종목코드:[/green] {selected_ticker}")
    else:
        console.print(
            create_question_box(
                "1단계: 종목코드",
                "KRX 종목코드를 입력하세요 (6자리 숫자, 예: 005930 삼성전자)",
                "005930",
            )
        )
        selected_ticker = get_ticker()
    asset_type = detect_asset_type(selected_ticker)
    if asset_type.value != "stock":
        console.print(
            f"[green]감지된 자산 유형:[/green] {asset_type.value}"
        )

    # Step 2: Analysis date
    if flags.get("date") is not None:
        analysis_date = _from_flag(parse_analysis_date, flags["date"])
        console.print(f"[green]✓ --date 플래그에서 분석일:[/green] {analysis_date}")
    else:
        default_date = datetime.datetime.now().strftime("%Y-%m-%d")
        console.print(
            create_question_box(
                "2단계: 분석일",
                "분석 기준일을 입력하세요 (YYYY-MM-DD)",
                default_date,
            )
        )
        analysis_date = get_analysis_date()

    # Step 3: Output language (TRADINGAGENTS_OUTPUT_LANGUAGE 로 skip)
    if os.environ.get("TRADINGAGENTS_OUTPUT_LANGUAGE"):
        output_language = DEFAULT_CONFIG["output_language"]
        console.print(
            f"[green]✓ 환경변수에서 출력 언어:[/green] {output_language}"
        )
    else:
        console.print(
            create_question_box(
                "3단계: 출력 언어",
                "분석가 리포트와 최종 결정의 출력 언어를 선택하세요"
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
                "4단계: 분석가 팀", "분석에 활용할 LLM 분석가를 선택하세요"
            )
        )
        selected_analysts = select_analysts(asset_type, prefs.get("analysts"))
    console.print(
        f"[green]선택된 분석가:[/green] {', '.join(analyst.value for analyst in selected_analysts)}"
    )

    # Step 5: Research depth (양쪽 라운드 수가 env 로 설정되면 skip)
    if depth_from_env():
        selected_research_depth = DEFAULT_CONFIG["max_debate_rounds"]
        console.print(
            f"[green]✓ 환경변수에서 리서치 깊이:[/green] "
            f"토론 {DEFAULT_CONFIG['max_debate_rounds']} / "
            f"리스크 {DEFAULT_CONFIG['max_risk_discuss_rounds']} 라운드"
        )
    else:
        console.print(
            create_question_box(
                "5단계: 리서치 깊이", "리서치 깊이를 선택하세요"
            )
        )
        selected_research_depth = select_research_depth(prefs.get("research_depth"))

    # Step 6: Thinking agents (양쪽 중 하나라도 env 로 설정되면 skip)
    if os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM") or os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM"):
        selected_shallow_thinker = DEFAULT_CONFIG["quick_think_llm"]
        selected_deep_thinker = DEFAULT_CONFIG["deep_think_llm"]
        console.print(
            f"[green]✓ 환경변수에서 추론 모델:[/green] "
            f"간이={selected_shallow_thinker}, 심층={selected_deep_thinker}"
        )
    else:
        console.print(
            create_question_box(
                "6단계: 추론 모델 (Claude)",
                "간이 추론(분석가) 과 심층 추론(매니저/트레이더) 티어의 Claude 모델을 선택하세요"
            )
        )
        selected_shallow_thinker = select_shallow_thinking_agent(prefs.get("quick_think_llm"))
        selected_deep_thinker = select_deep_thinking_agent(prefs.get("deep_think_llm"))

    # Step 7: Effort levels — Claude Code `--effort` per tier.
    # TRADINGAGENTS_EFFORT / TRADINGAGENTS_QUICK_EFFORT 로 각각 skip.
    if os.environ.get("TRADINGAGENTS_EFFORT"):
        selected_deep_effort = DEFAULT_CONFIG["effort"]
        console.print(
            f"[green]✓ 환경변수에서 심층 추론 Effort:[/green] {selected_deep_effort}"
        )
    else:
        console.print(
            create_question_box(
                "7a단계: 심층 추론 Effort",
                "심층 추론 티어 (리서처/매니저/트레이더/디베이터) 의 --effort 선택"
            )
        )
        selected_deep_effort = ask_effort("deep", prefs.get("effort"))

    if os.environ.get("TRADINGAGENTS_QUICK_EFFORT"):
        selected_quick_effort = DEFAULT_CONFIG["quick_effort"]
        console.print(
            f"[green]✓ 환경변수에서 간이 추론 Effort:[/green] {selected_quick_effort}"
        )
    else:
        console.print(
            create_question_box(
                "7b단계: 간이 추론 Effort",
                "간이 추론 티어 (분석가) 의 --effort 선택"
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
            console.print(f"[red]오류: {exc}[/red]")
