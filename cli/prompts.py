"""Interactive CLI prompts.

TradingAgents-KR 포크는 Claude Code 헤드리스가 유일한 LLM 백엔드이므로
(ADR-0001) provider 선택 UI 와 ChatGPT 로그인/OpenRouter/Qwen/Minimax/GLM
지역 선택 등 상류의 다중 provider UX 는 전부 제거되었습니다 (Task 2 #21).
사용자는 ticker/analysts/depth/model(sonnet·opus·haiku)/effort/언어만 고릅니다.
"""

import datetime
import re

import questionary

from cli.display import console
from cli.models import AnalystType, AssetType
from tradingagents.dataflows.symbols import KRX_TICKER_PATTERN, safe_ticker_component

_TICKER_CODE_PATTERN = re.compile(KRX_TICKER_PATTERN)


TICKER_INPUT_EXAMPLES = (
    "005930 (삼성전자), 000660 (SK하이닉스), 035720 (카카오), 069500 (KODEX 200 ETF)"
)

ANALYST_CHOICES = [
    # Task 9f (#85): 표시명은 한국어, enum 값 (AnalystType.MARKET 등) 영어 유지 (i18n 경계).
    ("시장 분석가 (Market)", AnalystType.MARKET),
    ("감성 분석가 (Sentiment)", AnalystType.SOCIAL),
    ("뉴스 분석가 (News)", AnalystType.NEWS),
    ("재무 분석가 (Fundamentals)", AnalystType.FUNDAMENTALS),
]

# Task 4b (#43): KRX 포크는 암호자산을 지원하지 않습니다. CRYPTO_SUFFIXES 는
# 빈 튜플로 축소되어 detect_asset_type 은 항상 AssetType.STOCK 을 반환합니다.
# Task 7 에서 crypto 관련 분기 전체 정리 예정.
CRYPTO_SUFFIXES: tuple[str, ...] = ()

# Claude Code 헤드리스가 지원하는 모델 alias.
# `claude --model` 이 받는 세 alias (sonnet/opus/haiku) 외의 모델 ID 도 Custom
# 으로 입력 가능. 선택지는 Task 1f #7 의 균형 조합 (deep=sonnet, quick=haiku).
_CLAUDE_MODELS = [
    ("Sonnet — Claude Sonnet 4.6 (균형, 심층 티어 권장)", "sonnet"),
    ("Opus — Claude Opus 4.7 (최대 추론 깊이)", "opus"),
    ("Haiku — Claude Haiku 4.5 (빠름, 간이 티어 권장)", "haiku"),
    ("Custom — 모델 ID 직접 입력", "custom"),
]

# Claude Code 가 받는 `--effort` 레벨.
_EFFORT_LEVELS = [
    ("High — 더 꼼꼼한 추론 (심층 티어 권장)", "high"),
    ("Medium — 균형 (간이 티어 권장)", "medium"),
    ("Low — 빠름, 덜 꼼꼼함", "low"),
    ("Xhigh — 매우 높은 추론 깊이", "xhigh"),
    ("Max — 최대 추론 깊이 (가장 느림)", "max"),
]


# 모든 선택 메뉴의 공통 스타일.
_MENU_STYLE = questionary.Style([
    ("selected", "fg:magenta noinherit"),
    ("highlighted", "fg:magenta noinherit"),
    ("pointer", "fg:magenta noinherit"),
])


def is_valid_ticker_input(value: str) -> bool:
    """`--ticker` 플래그 레벨 검증: KRX 종목코드(대문자 영숫자 6자)만 허용.

    Task 14g (#112): 대화형 `get_ticker()` 는 종목명 검색을 추가로 받지만,
    이 함수는 ``parse_ticker`` 가 호출하는 **플래그 검증**용이므로 종전처럼
    엄격하게 유지한다 — 자동화 스크립트의 결정성을 위해.
    """
    if not value.strip():
        return True
    try:
        safe_ticker_component(normalize_ticker_symbol(value))
    except ValueError:
        return False
    return True


def _is_valid_search_or_ticker(value: str) -> bool:
    """대화형 `get_ticker()` 입력 검증 — 빈 문자열, 종목코드, 또는 자유 검색어 허용.

    숫자 입력이 6자리가 아니면 거부 (오입력 가드). 비-숫자는 그대로 통과.
    """
    text = value.strip()
    if not text:
        return True
    if text.isdigit():
        return len(text) == 6
    return True


def _is_ticker_code(text: str) -> bool:
    """종목코드 모양인가. 영숫자 코드는 종목명과 구분하기 위해 숫자가 하나 이상 있어야 한다.

    DOOSAN 처럼 6자 대문자 영문 종목명은 코드가 아니라 이름 검색으로 보낸다. KRX 상장 종목
    코드 2,876개(영숫자 98개 포함)는 전부 숫자를 포함한다 (2026-11-08 FDR 목록 기준).
    """
    return bool(_TICKER_CODE_PATTERN.match(text)) and any(c.isdigit() for c in text)


def get_ticker() -> str:
    """사용자가 입력한 티커/종목명을 받아 정규화된 심볼로 반환.

    Task 14g (#112): 종목코드 입력은 기존대로 바로 티커로 통과, 그 외 문자열은
    `tradingagents.dataflows.krx_symbol_search.search` 로 부분 매칭 → 결과에
    따라 다음과 같이 처리한다:

    - 결과 0 → "검색 결과 없음" 안내 후 재프롬프트
    - 결과 1 → 자동 선택 + Y/N 확인
    - 결과 2–20 → `questionary.select` 로 번호 선택
    - 결과 > 20 → 상위 20 개 + "더 좁혀서 검색하세요" 안내 후 재프롬프트
    """
    while True:
        raw = questionary.text(
            f"KRX 종목코드 또는 종목명을 입력하세요 (예: {TICKER_INPUT_EXAMPLES}):",
            validate=lambda x: (
                _is_valid_search_or_ticker(x)
                or "숫자 코드는 6자리여야 합니다. 종목명은 자유롭게 입력하세요."
            ),
            style=questionary.Style(
                [
                    ("text", "fg:green"),
                    ("highlighted", "noinherit"),
                ]
            ),
        ).ask()

        if raw is None:
            console.print("\n[red]티커를 입력하지 않아 종료합니다.[/red]")
            exit(1)

        text = raw.strip()

        # Task 4b (#43): 빈 입력의 디폴트는 삼성전자 (005930).
        if not text:
            return "005930"

        # 종목코드 → 종전 흐름 유지 (zero-regression).
        if _is_ticker_code(text):
            return normalize_ticker_symbol(text)

        # 종목명 검색.
        resolved = _resolve_by_name(text)
        if resolved is not None:
            return resolved
        # None → 재프롬프트 (결과 없음 또는 너무 많아 좁혀야 함)


def _resolve_by_name(query: str) -> str | None:
    """검색 결과를 바탕으로 사용자 확정을 받아 티커를 돌려주거나 재프롬프트 신호 반환.

    Returns:
        정규화된 6자리 종목코드. 재프롬프트가 필요하면 ``None``.
    """
    from tradingagents.dataflows import krx_symbol_search as kss

    try:
        hits = kss.search(query, limit=20)
    except Exception as exc:  # noqa: BLE001 — 캐시/네트워크 실패는 UI 가 안내
        console.print(f"[red]종목 검색 실패: {exc}[/red]")
        return None

    if not hits:
        console.print(f"[yellow]'{query}' 로 매칭된 종목이 없습니다. 다시 입력하세요.[/yellow]")
        return None

    if len(hits) == 1:
        hit = hits[0]
        confirmed = questionary.confirm(
            f"{hit.ticker} · {hit.name} ({hit.market}) 로 진행할까요?",
            default=True,
        ).ask()
        if confirmed is None:
            console.print("\n[red]티커를 확정하지 않아 종료합니다.[/red]")
            exit(1)
        return hit.ticker if confirmed else None

    if len(hits) >= 20:
        console.print(
            "[yellow]검색 결과가 상위 20개로 잘렸습니다. 더 좁혀서 다시 검색하거나"
            " 아래 목록에서 선택하세요.[/yellow]"
        )

    choices = [
        questionary.Choice(
            title=f"{hit.ticker} · {hit.name} · {hit.market}",
            value=hit.ticker,
        )
        for hit in hits
    ]
    picked = questionary.select(
        "종목을 선택하세요:",
        choices=choices,
        style=_MENU_STYLE,
    ).ask()
    if picked is None:
        # Esc 또는 취소 → 재프롬프트
        return None
    return picked


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

    Task 4a (#42): KRX 종목코드 패턴(영숫자 6자, #181) 외의 입력은 ``ValueError`` 로 거부합니다.
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
        "분석가 팀 선택:",
        choices=[
            questionary.Choice(display, value=value, checked=value.value in (default or []))
            for display, value in ANALYST_CHOICES
            if value in available_analysts
        ],
        instruction="\n- 스페이스 키로 분석가 선택/해제\n- 'a' 키로 전체 선택/해제\n- Enter 키로 완료",
        validate=lambda x: len(x) > 0 or "분석가를 최소 1명 이상 선택해야 합니다.",
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
        console.print("\n[red]분석가가 선택되지 않아 종료합니다.[/red]")
        exit(1)

    return choices


def select_research_depth(default=None) -> int:
    """대화형으로 리서치 깊이(토론 라운드 수) 선택."""

    DEPTH_OPTIONS = [
        ("얕음 — 빠른 리서치, 토론·전략 라운드 적음", 1),
        ("중간 — 균형, 적당한 토론·전략 라운드", 3),
        ("깊음 — 종합 리서치, 심층 토론·전략 라운드", 5),
    ]

    choice = questionary.select(
        "리서치 깊이 선택:",
        choices=[
            questionary.Choice(display, value=value) for display, value in DEPTH_OPTIONS
        ],
        default=_matching_choice(DEPTH_OPTIONS, default),
        instruction="\n- 화살표 키로 이동\n- Enter 키로 선택",
        style=questionary.Style(
            [
                ("selected", "fg:yellow noinherit"),
                ("highlighted", "fg:yellow noinherit"),
                ("pointer", "fg:yellow noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print("\n[red]리서치 깊이가 선택되지 않아 종료합니다.[/red]")
        exit(1)

    return choice


def _require_text(message: str, hint: str) -> str:
    """필수 텍스트 입력. Ctrl-C/Esc 로 취소 시 깔끔히 exit."""
    response = questionary.text(
        message,
        validate=lambda x: len(x.strip()) > 0 or hint,
    ).ask()
    if response is None:
        console.print("\n[red]취소됨. 종료합니다.[/red]")
        exit(1)
    return response.strip()


def _prompt_custom_model_id() -> str:
    """사용자가 커스텀 모델 ID 를 입력하도록 유도."""
    return _require_text(
        "Claude 모델 ID 입력 (예: claude-opus-4-7, claude-sonnet-4-6):",
        "모델 ID 를 입력해 주세요.",
    )


def _select_model(mode: str, default=None) -> str:
    """Claude Code 모델 선택 (deep 또는 quick)."""
    tier_label = "심층 추론" if mode == "deep" else "간이 추론"
    choice = questionary.select(
        f"{tier_label} Claude 모델 선택:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in _CLAUDE_MODELS
        ],
        default=_matching_choice(_CLAUDE_MODELS, default),
        instruction="\n- 화살표 키로 이동\n- Enter 키로 선택",
        style=_MENU_STYLE,
    ).ask()

    if choice is None:
        console.print(f"\n[red]{tier_label} LLM 엔진이 선택되지 않아 종료합니다.[/red]")
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
    tier_label = "심층 추론" if mode == "deep" else "간이 추론"
    choice = questionary.select(
        f"{tier_label} Effort 레벨 선택:",
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
        console.print(f"\n[red]{tier_label} Effort 레벨이 선택되지 않아 종료합니다.[/red]")
        exit(1)
    return choice


def ask_output_language(default=None) -> str:
    """리포트 출력 언어 선택.

    ``default`` 는 리스트에 있는 언어일 때만 preselect — 지난 번에 입력한
    커스텀 언어는 자유 텍스트이므로 메뉴에서 preselect 할 수 없음.
    """
    choices = [
        questionary.Choice("한국어 (Korean, 기본값)", "Korean"),
        questionary.Choice("English", "English"),
        questionary.Choice("中文 (Chinese)", "Chinese"),
        questionary.Choice("日本語 (Japanese)", "Japanese"),
        questionary.Choice("हिन्दी (Hindi)", "Hindi"),
        questionary.Choice("Español (Spanish)", "Spanish"),
        questionary.Choice("Português (Portuguese)", "Portuguese"),
        questionary.Choice("Français (French)", "French"),
        questionary.Choice("Deutsch (German)", "German"),
        questionary.Choice("العربية (Arabic)", "Arabic"),
        questionary.Choice("Русский (Russian)", "Russian"),
        questionary.Choice("직접 입력 (Custom)", "custom"),
    ]
    choice = questionary.select(
        "출력 언어 선택:",
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
            "언어 이름을 입력하세요 (예: Turkish, Vietnamese, Thai, Indonesian):",
            validate=lambda x: len(x.strip()) > 0 or "언어 이름을 입력해 주세요.",
        ).ask() or "").strip() or "Korean"

    return choice
