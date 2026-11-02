"""Interactive CLI prompts.

TradingAgents-KR 포크는 Claude Code 헤드리스가 유일한 LLM 백엔드이므로
(ADR-0001) provider 선택 UI 와 ChatGPT 로그인/OpenRouter/Qwen/Minimax/GLM
지역 선택 등 상류의 다중 provider UX 는 전부 제거되었습니다 (Task 2 #21).
사용자는 ticker/analysts/depth/model(sonnet·opus·haiku)/effort/언어만 고릅니다.
"""

import datetime

import questionary

from cli.display import console
from cli.models import AnalystType, AssetType
from tradingagents.dataflows.symbols import safe_ticker_component

TICKER_INPUT_EXAMPLES = (
    "005930 (삼성전자), 000660 (SK하이닉스), 035720 (카카오), 069500 (KODEX 200 ETF)"
)

ANALYST_CHOICES = [
    ("Market Analyst", AnalystType.MARKET),
    ("Sentiment Analyst", AnalystType.SOCIAL),
    ("News Analyst", AnalystType.NEWS),
    ("Fundamentals Analyst", AnalystType.FUNDAMENTALS),
]

# Task 4b (#43): KRX 포크는 암호자산을 지원하지 않습니다. CRYPTO_SUFFIXES 는
# 빈 튜플로 축소되어 detect_asset_type 은 항상 AssetType.STOCK 을 반환합니다.
# Task 7 에서 crypto 관련 분기 전체 정리 예정.
CRYPTO_SUFFIXES: tuple[str, ...] = ()

# Claude Code 헤드리스가 지원하는 모델 alias.
# `claude --model` 이 받는 세 alias (sonnet/opus/haiku) 외의 모델 ID 도 Custom
# 으로 입력 가능. 선택지는 Task 1f #7 의 균형 조합 (deep=sonnet, quick=haiku).
_CLAUDE_MODELS = [
    ("Sonnet — Claude Sonnet 4.6 (balanced, recommended for deep tier)", "sonnet"),
    ("Opus — Claude Opus 4.7 (max reasoning depth)", "opus"),
    ("Haiku — Claude Haiku 4.5 (fast, recommended for quick tier)", "haiku"),
    ("Custom — enter a model ID", "custom"),
]

# Claude Code 가 받는 `--effort` 레벨.
_EFFORT_LEVELS = [
    ("High — more thorough reasoning (recommended for deep tier)", "high"),
    ("Medium — balanced (recommended for quick tier)", "medium"),
    ("Low — faster, less thorough", "low"),
    ("Xhigh — extra high reasoning depth", "xhigh"),
    ("Max — maximum reasoning depth (slowest)", "max"),
]


# 모든 선택 메뉴의 공통 스타일.
_MENU_STYLE = questionary.Style([
    ("selected", "fg:magenta noinherit"),
    ("highlighted", "fg:magenta noinherit"),
    ("pointer", "fg:magenta noinherit"),
])


def is_valid_ticker_input(value: str) -> bool:
    """티커 입력이 데이터 레이어가 받아들일 수 있는 심볼인지 검증."""
    if not value.strip():
        return True
    try:
        safe_ticker_component(normalize_ticker_symbol(value))
    except ValueError:
        return False
    return True


def get_ticker() -> str:
    """사용자가 입력한 티커를 받아 정규화된 심볼로 반환."""
    ticker = questionary.text(
        f"KRX 종목코드를 입력하세요 (예: {TICKER_INPUT_EXAMPLES}):",
        validate=lambda x: (
            is_valid_ticker_input(x)
            or "KRX 6자리 숫자 종목코드만 지원합니다 (예: 005930 삼성전자)."
        ),
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()

    if ticker is None:
        console.print("\n[red]티커를 입력하지 않아 종료합니다.[/red]")
        exit(1)

    # Task 4b (#43): 빈 입력의 디폴트는 SPY 가 아니라 삼성전자 (005930). 미국
    # 종목으로의 폴백은 KRX 전용 포크에서 더 이상 의미 없음.
    return normalize_ticker_symbol(ticker) if ticker.strip() else "005930"


def parse_ticker(value: str) -> str:
    """커맨드라인으로 받은 티커를 정규화된 심볼로 변환. 빈/부적합 입력은 거부."""
    if not value.strip() or not is_valid_ticker_input(value):
        raise ValueError(f"not a ticker symbol: {value!r} (e.g. {TICKER_INPUT_EXAMPLES})")
    return normalize_ticker_symbol(value)


def parse_analysis_date(value: str) -> str:
    """분석 날짜를 YYYY-MM-DD 형식으로 파싱. 미래 날짜 거부."""
    try:
        day = datetime.datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"not a date: {value!r}; use YYYY-MM-DD") from None
    if day > datetime.date.today():
        raise ValueError(f"{value} is in the future")
    return day.isoformat()


def parse_analysts(value: str, asset_type: AssetType) -> list[AnalystType]:
    """쉼표로 구분된 analyst 이름 목록을 캐노니컬 순서로 변환."""
    names = [{"sentiment": "social"}.get(n, n) for n in (n.strip().lower() for n in value.split(",")) if n]
    if not names:
        raise ValueError("name at least one analyst")
    known = {a.value: a for a in AnalystType}
    unknown = [n for n in names if n not in known]
    if unknown:
        choices = ", ".join("sentiment" if name == "social" else name for name in known)
        raise ValueError(f"unknown analyst {', '.join(unknown)}; choose from {choices}")
    available = filter_analysts_for_asset_type(list(known.values()), asset_type)
    unavailable = [n for n in names if known[n] not in available]
    if unavailable:
        raise ValueError(f"{', '.join(unavailable)} is not available for {asset_type.value}")
    return [a for a in available if a.value in names]


def normalize_ticker_symbol(ticker: str) -> str:
    """사용자 입력을 KRX 종목코드로 정규화.

    Task 4a (#42): KRX 6자리 숫자 패턴 외의 입력은 ``ValueError`` 로 거부합니다.
    상류의 fallback (Exception 삼키고 upper-case 반환) 은 미국/홍콩 심볼을
    통과시켜 데이터 레이어에서 "ticker not found" 로 이어지는 문제가 있어 삭제.
    ``is_valid_ticker_input`` 가 이 예외를 바로 받아 False 로 변환합니다.
    """
    from tradingagents.dataflows.symbols import validate_krx_ticker

    return validate_krx_ticker(ticker)


def detect_asset_type(ticker: str) -> AssetType:
    """캐노니컬 심볼 기준으로 자산 타입(주식/암호자산) 분류."""
    canonical = normalize_ticker_symbol(ticker)
    if canonical.endswith(CRYPTO_SUFFIXES):
        return AssetType.CRYPTO
    return AssetType.STOCK


def filter_analysts_for_asset_type(
    analysts: list[AnalystType], asset_type: AssetType
) -> list[AnalystType]:
    if asset_type != AssetType.CRYPTO:
        return analysts
    return [
        analyst
        for analyst in analysts
        if analyst != AnalystType.FUNDAMENTALS
    ]


def _matching_choice(options, default):
    """``default`` 와 일치하는 옵션 값, 없으면 None."""
    return next((value for _, value in options if value == default), None)


def select_analysts(asset_type: AssetType = AssetType.STOCK, default=None) -> list[AnalystType]:
    """대화형 체크박스로 analyst 팀 구성."""
    available_analysts = filter_analysts_for_asset_type(
        [value for _, value in ANALYST_CHOICES],
        asset_type,
    )
    choices = questionary.checkbox(
        "Select Your [Analysts Team]:",
        choices=[
            questionary.Choice(display, value=value, checked=value.value in (default or []))
            for display, value in ANALYST_CHOICES
            if value in available_analysts
        ],
        instruction="\n- Press Space to select/unselect analysts\n- Press 'a' to select/unselect all\n- Press Enter when done",
        validate=lambda x: len(x) > 0 or "You must select at least one analyst.",
        style=questionary.Style(
            [
                ("checkbox-selected", "fg:green"),
                ("selected", "fg:green noinherit"),
                ("highlighted", "noinherit"),
                ("pointer", "noinherit"),
            ]
        ),
    ).ask()

    if not choices:
        console.print("\n[red]No analysts selected. Exiting...[/red]")
        exit(1)

    return choices


def select_research_depth(default=None) -> int:
    """대화형으로 리서치 깊이(토론 라운드 수) 선택."""

    DEPTH_OPTIONS = [
        ("Shallow - Quick research, few debate and strategy discussion rounds", 1),
        ("Medium - Middle ground, moderate debate rounds and strategy discussion", 3),
        ("Deep - Comprehensive research, in depth debate and strategy discussion", 5),
    ]

    choice = questionary.select(
        "Select Your [Research Depth]:",
        choices=[
            questionary.Choice(display, value=value) for display, value in DEPTH_OPTIONS
        ],
        default=_matching_choice(DEPTH_OPTIONS, default),
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:yellow noinherit"),
                ("highlighted", "fg:yellow noinherit"),
                ("pointer", "fg:yellow noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print("\n[red]No research depth selected. Exiting...[/red]")
        exit(1)

    return choice


def _require_text(message: str, hint: str) -> str:
    """필수 텍스트 입력. Ctrl-C/Esc 로 취소 시 깔끔히 exit."""
    response = questionary.text(
        message,
        validate=lambda x: len(x.strip()) > 0 or hint,
    ).ask()
    if response is None:
        console.print("\n[red]Cancelled. Exiting...[/red]")
        exit(1)
    return response.strip()


def _prompt_custom_model_id() -> str:
    """사용자가 커스텀 모델 ID 를 입력하도록 유도."""
    return _require_text(
        "Enter Claude model ID (e.g. claude-opus-4-7, claude-sonnet-4-6):",
        "Please enter a model ID.",
    )


def _select_model(mode: str, default=None) -> str:
    """Claude Code 모델 선택 (deep 또는 quick)."""
    choice = questionary.select(
        f"Select Your [{mode.title()}-Thinking Claude Model]:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in _CLAUDE_MODELS
        ],
        default=_matching_choice(_CLAUDE_MODELS, default),
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=_MENU_STYLE,
    ).ask()

    if choice is None:
        console.print(f"\n[red]No {mode} thinking llm engine selected. Exiting...[/red]")
        exit(1)

    if choice == "custom":
        return _prompt_custom_model_id()

    return choice


def select_shallow_thinking_agent(default=None) -> str:
    """빠른 추론 티어의 Claude 모델 선택."""
    return _select_model("quick", default)


def select_deep_thinking_agent(default=None) -> str:
    """깊은 추론 티어의 Claude 모델 선택."""
    return _select_model("deep", default)


def ask_effort(mode: str, default=None) -> str:
    """티어의 Claude Code `--effort` 레벨 선택 (deep 또는 quick)."""
    choice = questionary.select(
        f"Select Effort Level for [{mode.title()}-Thinking]:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in _EFFORT_LEVELS
        ],
        default=_matching_choice(_EFFORT_LEVELS, default),
        style=questionary.Style([
            ("selected", "fg:cyan noinherit"),
            ("highlighted", "fg:cyan noinherit"),
            ("pointer", "fg:cyan noinherit"),
        ]),
    ).ask()

    if choice is None:
        console.print(f"\n[red]No effort level selected for {mode}. Exiting...[/red]")
        exit(1)
    return choice


def ask_output_language(default=None) -> str:
    """리포트 출력 언어 선택.

    ``default`` 는 리스트에 있는 언어일 때만 preselect — 지난 번에 입력한
    커스텀 언어는 자유 텍스트이므로 메뉴에서 preselect 할 수 없음.
    """
    choices = [
        questionary.Choice("Korean (한국어, default)", "Korean"),
        questionary.Choice("English", "English"),
        questionary.Choice("Chinese (中文)", "Chinese"),
        questionary.Choice("Japanese (日本語)", "Japanese"),
        questionary.Choice("Hindi (हिन्दी)", "Hindi"),
        questionary.Choice("Spanish (Español)", "Spanish"),
        questionary.Choice("Portuguese (Português)", "Portuguese"),
        questionary.Choice("French (Français)", "French"),
        questionary.Choice("German (Deutsch)", "German"),
        questionary.Choice("Arabic (العربية)", "Arabic"),
        questionary.Choice("Russian (Русский)", "Russian"),
        questionary.Choice("Custom language", "custom"),
    ]
    choice = questionary.select(
        "Select Output Language:",
        choices=choices,
        default=_matching_choice([(c.title, c.value) for c in choices], default),
        style=questionary.Style([
            ("selected", "fg:yellow noinherit"),
            ("highlighted", "fg:yellow noinherit"),
            ("pointer", "fg:yellow noinherit"),
        ]),
    ).ask()

    # 출력 언어는 디폴트가 있으므로 취소 시 Korean 으로 폴백.
    if choice is None:
        return "Korean"
    if choice == "custom":
        return (questionary.text(
            "Enter language name (e.g. Turkish, Vietnamese, Thai, Indonesian):",
            validate=lambda x: len(x.strip()) > 0 or "Please enter a language name.",
        ).ask() or "").strip() or "Korean"

    return choice
