"""지난 번 run 의 선택을 다음 번 run 의 디폴트로 제시.

대화형 흐름은 매번 같은 질문을 하고, 그 중 일부만 환경변수로 skip 할 수
있습니다 (analyst set 은 환경변수가 없음). 저장된 답은 프롬프트를 pre-fill
해서 Enter 로 수락할 수 있게 하지만 단계를 skip 하지는 않습니다 — 사용자가
한 번은 선택지를 봅니다.

run 사이에 안정적인 답만 저장합니다. 티커와 분석 날짜는 매번 바뀌므로 저장
하지 않습니다 (오래된 날짜가 조용히 제시되는 사고 방지).

저장된 값은 되돌릴 때 현재 선택지와 비교해 걸러집니다 — 더 이상 제공되지
않는 모델은 preselect 되지 않고 그냥 drop 됩니다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from cli.models import AnalystType, AssetType
from cli.prompts import filter_analysts_for_asset_type
from tradingagents.dataflows.files import replace_file

_PREFS_PATH = Path(os.path.expanduser("~")) / ".tradingagents" / "cli_prefs.json"

# Task 2 (#21) 로 llm_provider 와 backend_url 저장은 의미 없어졌음 — provider 가
# claude-code 로 고정이고 백엔드 URL 은 로컬 CLI 호출이라 N/A. deep/quick 모델
# 과 effort 선택만 저장.
REMEMBERED = (
    "output_language", "analysts", "research_depth",
    "quick_think_llm", "deep_think_llm", "effort", "quick_effort",
)

# Claude Code 가 받는 모델 alias (claude --model). cli/prompts.py 의
# _CLAUDE_MODELS 와 일치해야 함. Custom 모델 ID 는 자유 텍스트이므로 저장할 때
# 그대로 받아들임.
_KNOWN_CLAUDE_MODELS = frozenset({"sonnet", "opus", "haiku"})

# Claude Code `--effort` 가 받는 레벨.
_KNOWN_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})


def load_last_run() -> dict:
    """지난 번 run 의 답. 읽을 수 없거나 손상되면 빈 dict (fail-open)."""
    try:
        data = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_last_run(selections: dict) -> None:
    """다음에 제시할 가치가 있는 답만 기록. 실패는 치명적이지 않음."""
    kept = {k: v for k, v in selections.items() if k in REMEMBERED and v not in (None, "", [])}
    kept["analysts"] = [getattr(a, "value", a) for a in kept.get("analysts", [])] or None
    kept = {k: v for k, v in kept.items() if v is not None}
    try:
        _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        # 동시 run 은 둘 중 하나의 파일을 읽는다.
        replace_file(_PREFS_PATH, lambda temp: Path(temp).write_text(json.dumps(kept, indent=2), encoding="utf-8"))
    except OSError:
        return


def sanitize(prefs: dict, asset_type) -> dict:
    """현재도 선택 가능한 답만 유지."""
    kept: dict = {}
    if isinstance(prefs.get("output_language"), str):
        kept["output_language"] = prefs["output_language"]
    if prefs.get("research_depth") in (1, 3, 5):
        kept["research_depth"] = prefs["research_depth"]

    known_analysts = {a.value for a in AnalystType}
    analysts = [a for a in prefs.get("analysts") or [] if a in known_analysts]
    allowed = filter_analysts_for_asset_type([AnalystType(a) for a in analysts], AssetType(asset_type))
    if allowed:
        kept["analysts"] = [a.value for a in allowed]

    # Claude 모델 ID: 알려진 alias (sonnet/opus/haiku) 또는 임의 문자열
    # (Custom ID 로 입력된 경우) 는 그대로 유지. 비문자열은 drop.
    for field in ("quick_think_llm", "deep_think_llm"):
        value = prefs.get(field)
        if isinstance(value, str) and value.strip():
            kept[field] = value

    for field in ("effort", "quick_effort"):
        value = prefs.get(field)
        if isinstance(value, str) and value in _KNOWN_EFFORTS:
            kept[field] = value

    return kept
