"""회사 소속 테마 추출 (#165) — 조회된 공시 발췌에 근거한 것만 남긴다.

모델이 사업 개요(DART 사업보고서 "사업의 개요" 발췌)를 읽고 테마 후보를 고르되, 각 테마마다
**발췌에서 그대로 옮긴 근거 문장**을 함께 내게 한다. 코드가 그 문장이 실제로 발췌에 있는지
검사해서 없는 테마는 버린다 — 모델이 학습 지식으로 테마를 지어내도 보고서까지 올라가지 못한다.

결과는 ``{"status", "themes", "reason"}`` 사전이다. ``status``:
``ok`` (테마 있음) / ``none`` (근거 있는 테마 없음) / ``error`` (호출 실패) /
``unavailable`` (발췌가 없거나 모델이 구조화 출력을 지원하지 않음).
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from tradingagents.agents.structured import NO_EXTERNAL_TOOLS, invoke_structured

MAX_THEMES = 3
_MIN_EVIDENCE_CHARS = 12   # 너무 짧은 근거("바이오")는 아무 데나 맞으므로 인정하지 않는다
_MAX_NAME_CHARS = 20
_WHITESPACE = re.compile(r"\s+")


class Theme(BaseModel):
    name: str = Field(description="테마 이름. 투자자가 부르는 짧은 명사구 (예: 바이오 플랫폼, 2차전지 소재).")
    evidence: str = Field(
        description="이 테마의 근거가 되는 문장. 사업 개요 발췌에서 한 글자도 바꾸지 않고 그대로 옮긴 부분.")


class ThemeList(BaseModel):
    themes: list[Theme] = Field(
        default_factory=list,
        description="최대 3개. 발췌만으로 근거를 댈 수 있는 테마만. 근거가 없으면 빈 목록.")


def squash(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def verify_themes(themes: list[Theme], source: str) -> list[dict[str, str]]:
    """발췌에 실제로 있는 근거를 가진 테마만, 최대 ``MAX_THEMES`` 개."""
    haystack = squash(source)
    kept: list[dict[str, str]] = []
    seen: set[str] = set()
    for theme in themes:
        name = squash(theme.name)
        evidence = squash(theme.evidence).strip("\"'“”‘’")
        if not name or len(name) > _MAX_NAME_CHARS or name in seen:
            continue
        if len(evidence) < _MIN_EVIDENCE_CHARS or evidence not in haystack:
            continue
        seen.add(name)
        kept.append({"name": name, "evidence": evidence})
        if len(kept) == MAX_THEMES:
            break
    return kept


def _overview_text(business: str) -> str:
    """``get_business_overview`` 결과(JSON)의 발췌 본문. 읽을 수 없으면 빈 문자열."""
    try:
        data = json.loads(business)
    except (ValueError, TypeError):
        return ""
    overview = data.get("overview") if isinstance(data, dict) else ""
    return overview if isinstance(overview, str) else ""


def _prompt(overview: str) -> str:
    return (
        "아래는 한 상장회사의 사업보고서 \"사업의 개요\" 발췌입니다. 이 회사가 속한 **테마**를 "
        f"최대 {MAX_THEMES}개 고르세요. 테마는 투자자가 종목을 묶어 부르는 이름입니다 "
        "(예: 바이오 플랫폼, 제형 변경, 2차전지 소재).\n\n"
        "규칙:\n"
        "- 발췌만 근거로 삼으세요. 발췌에 나오지 않는 사업·제품·고객을 학습 지식으로 덧붙이지 마세요.\n"
        "- 각 테마의 `evidence` 에는 발췌에서 그 테마를 뒷받침하는 문장(또는 구절)을 **한 글자도 바꾸지 말고 "
        "그대로** 옮기세요. 요약·번역·말바꿈 금지. 그대로 옮기지 못하면 그 테마는 빼세요.\n"
        "- 근거를 댈 수 있는 테마가 없으면 빈 목록을 돌려주세요.\n\n"
        f"{NO_EXTERNAL_TOOLS}\n\n"
        f"## 사업 개요 발췌\n{overview}\n"
    )


def extract_themes(structured_llm: Any | None, business: str) -> dict[str, Any]:
    """공시 발췌에서 근거 있는 테마를 뽑는다. 실패해도 예외를 내지 않는다 (분석가를 멈추지 않는다)."""
    overview = _overview_text(business)
    if not overview:
        return {"status": "unavailable", "themes": [], "reason": "회사 개요(공시 발췌)가 없어 테마를 정하지 않았습니다."}
    if structured_llm is None:
        return {"status": "unavailable", "themes": [], "reason": "모델이 구조화 출력을 지원하지 않아 테마를 정하지 않았습니다."}
    # invoke_structured 는 호출 실패를 삼키고 None 을 돌려준다 — 테마 실패가 재무 보고서를 막지 않는다.
    result = invoke_structured(structured_llm, _prompt(overview), "Company Themes")
    if result is None:
        return {"status": "error", "themes": [], "reason": "테마 추출 호출이 실패했습니다."}
    themes = verify_themes(result.themes, overview)
    if not themes:
        return {"status": "none", "themes": [], "reason": "공시 발췌에서 근거를 확인할 수 있는 테마가 없습니다."}
    return {"status": "ok", "themes": themes, "reason": ""}
