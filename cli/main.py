import sys

import typer

from cli.display import console
from cli.models import AnalystType, AssetType
from cli.prompts import filter_analysts_for_asset_type, parse_analysts
from cli.run import run_analysis
from tradingagents.backtest import iter_grid, run_backtest, summarize
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.portfolio import load_portfolio

# prompt_toolkit's win32 output module is importable only on Windows (it asserts
# the platform at import time), so gate on the platform rather than catching the
# failure — that way a genuinely broken prompt_toolkit on Windows still surfaces
# instead of silently disabling the handler below. Off Windows this stays an
# empty tuple, which `except` accepts and never matches (#1138).
if sys.platform == "win32":  # pragma: no cover - platform dependent
    from prompt_toolkit.output.win32 import NoConsoleScreenBufferError

    _NO_CONSOLE_ERRORS: tuple[type[BaseException], ...] = (NoConsoleScreenBufferError,)
else:
    _NO_CONSOLE_ERRORS = ()

app = typer.Typer(
    name="TradingAgents",
    help="TradingAgents-KR CLI: 한국 증시 멀티에이전트 LLM 트레이딩 프레임워크",
    add_completion=True,  # Enable shell completion
)


@app.callback(invoke_without_command=True)
def analyze(
    ctx: typer.Context,
    checkpoint: bool | None = typer.Option(
        None,
        "--checkpoint/--no-checkpoint",
        help="체크포인트/재개 활성화 (각 노드 후 상태 저장 — 중단된 run 을 "
        "재개 가능). 생략 시 TRADINGAGENTS_CHECKPOINT_ENABLED 를 따름.",
    ),
    clear_checkpoints: bool = typer.Option(
        False,
        "--clear-checkpoints",
        help="실행 전 저장된 체크포인트 전부 삭제 (강제 새로 시작).",
    ),
    portfolio: str = typer.Option(
        None,
        "--portfolio",
        help="현재 보유 종목·현금 JSON 파일. 트레이더/리스크/포트폴리오 에이전트가 실제 포지션에 "
        "맞춰 사이징합니다.",
    ),
    ticker: str = typer.Option(None, "--ticker", help="분석할 KRX 종목코드 (예: 005930 삼성전자); 지정하면 프롬프트 생략"),
    date: str = typer.Option(None, "--date", help="분석일 (YYYY-MM-DD); 지정하면 프롬프트 생략"),
    analysts: str = typer.Option(
        None, "--analysts", help="쉼표로 구분된 분석가 (예: market,news); 지정하면 프롬프트 생략"
    ),
    save: bool | None = typer.Option(
        None, "--save/--no-save", help="results_dir 아래에 보고서를 질문 없이 저장"
    ),
    show: bool | None = typer.Option(
        None, "--show/--no-show", help="마지막에 전체 보고서를 질문 없이 표시"
    ),
    html: bool | None = typer.Option(
        None, "--html/--no-html",
        help="complete_report.html HTML 페이지도 질문 없이 저장 (기본값: yes)",
    ),
):
    """분석 실행. 플래그 없이 `tradingagents` 를 실행하면 이 명령이 호출됩니다.

    플래그가 질문에 대신 답합니다. provider / 모델 / 깊이 / 언어가 TRADINGAGENTS_*
    환경변수로도 설정되면 run 은 질문을 하지 않습니다.
    """
    if ctx.invoked_subcommand is not None:
        return
    if clear_checkpoints:
        from tradingagents.graph.checkpointer import clear_all_checkpoints
        n = clear_all_checkpoints(DEFAULT_CONFIG["data_cache_dir"])
        console.print(f"[yellow]체크포인트 {n}개 삭제됨.[/yellow]")
    portfolio_context = None
    if portfolio:
        try:
            portfolio_context = load_portfolio(portfolio)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from None

    try:
        flags = {"ticker": ticker, "date": date, "analysts": analysts, "save": save, "show": show, "html": html}
        run_analysis(checkpoint=checkpoint, portfolio=portfolio_context, flags=flags)
    except _NO_CONSOLE_ERRORS:
        # A terminal with no console buffer cannot host the interactive prompts.
        # Emit one actionable line on stderr instead of a prompt_toolkit
        # traceback; plain text, since rich may not render here either (#1138).
        typer.echo(
            "오류: Windows 콘솔을 사용할 수 없습니다. 대화형 CLI 는 실제 콘솔 버퍼가 필요합니다 — "
            "Windows Terminal / PowerShell / cmd.exe 에서 실행하세요 (파이프/임베디드 터미널 금지).",
            err=True,
        )
        raise typer.Exit(code=1) from None


@app.command()
def backtest(
    tickers: str = typer.Argument(..., help="쉼표로 구분된 KRX 종목코드 (예: 005930,000660,035720)"),
    start: str = typer.Option(..., "--start", help="시작 분석일 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", help="종료 분석일 (YYYY-MM-DD)"),
    every: int = typer.Option(7, "--every", help="분석일 사이 간격 (일)"),
    analysts: str = typer.Option(
        None, "--analysts", help="실행할 분석가 (쉼표 구분): market, sentiment, news, fundamentals. 생략 시 자산 유형이 허용하는 전부 실행"
    ),
    asset_type: str = typer.Option("stock", "--asset-type", help="stock 또는 crypto"),
    portfolio: str = typer.Option(
        None, "--portfolio", help="보유 종목·현금 JSON 파일. 그리드 전체에서 동일하게 유지"
    ),
    run_id: str = typer.Option(
        None, "--run-id", help="이전 sweep 이어서 실행: 해당 셀은 건너뛰고 로그 재사용"
    ),
):
    """티커·날짜 그리드에 대해 과거 결정을 평가."""

    try:
        dates = iter_grid(start, end, every)
        book = load_portfolio(portfolio) if portfolio else None
        kind = AssetType(asset_type.strip().lower())
        # The analysts are named and checked as for an analysis; without a
        # choice, every analyst the asset type allows runs.
        chosen = (parse_analysts(analysts, kind) if analysts
                  else filter_analysts_for_asset_type(list(AnalystType), kind))
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    names = [t.strip() for t in tickers.split(",") if t.strip()]
    if not names:
        console.print("[red]분석할 종목코드가 없습니다. 쉼표로 구분해 입력하세요 (예: 005930,000660).[/red]")
        raise typer.Exit(code=1)

    def show_progress(done, total, ticker, date):
        console.print(f"[dim][{done}/{total}] {ticker} {date}[/dim]")

    kwargs = {"asset_type": kind.value, "portfolio": book, "run_id": run_id, "progress": show_progress,
              "selected_analysts": [a.value for a in chosen]}

    try:
        result = run_backtest(names, dates, DEFAULT_CONFIG, **kwargs)
    except Exception as exc:  # a missing key or an unknown analyst is a setup error
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(summarize(result).render())
    console.print(f"\n{result.cells_run}개 셀 실행, {result.skipped}개 건너뜀. 로그: {result.log_path}")
    console.print(f"이 sweep 을 이어서 실행하거나 settle 하려면: --run-id {result.run_id}")
    for ticker, date, reason in result.failures:
        console.print(f"[yellow]실패:[/yellow] {ticker} {date}: {reason}")
    for ticker, reason in result.settlement_failures:
        console.print(f"[yellow]settle 안 됨:[/yellow] {ticker}: {reason}")


# ChatGPT 플랜 로그인/로그아웃 명령 (`login`/`logout`) 은 Task 2 (#21) 에서
# 삭제되었습니다 — 포크는 Claude Code 헤드리스가 유일 LLM 백엔드이며 (ADR-0001),
# OAuth 인증은 Claude Code CLI 자체가 담당합니다 (`claude login`).

if __name__ == "__main__":
    app()
