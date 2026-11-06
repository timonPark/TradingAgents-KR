"""회사 현재 핵심 이슈 추출 (#166) — 조회한 뉴스·공시에 근거한 것만 남긴다.

뉴스 분석가가 사전조회한 종목 뉴스(헤드라인)와 DART 최근 공시 제목에 번호(N1.., D1..)를 붙여
모델에 주고, 핵심 이슈 최대 3개를 **근거 번호 + 그 헤드라인에서 그대로 옮긴 인용구**와 함께 내게 한다.
코드가 (1) 번호가 실제 조회한 자료인지, (2) 인용구가 인용한 자료의 제목에 있는지 검사하고, 통과한
이슈에만 **조회 데이터의 제목·링크**를 출처로 붙인다 — 링크는 모델이 쓰지 않는다.

이슈의 요약 문장(``summary``)은 모델이 쓴다. 인용구가 헤드라인에서 확인되고 출처가 함께 보이므로
독자가 대조할 수 있지만, 요약 문장 자체가 기계 검증되지는 않는다.

결과는 ``{"status", "issues", "reason"}``: ``ok`` / ``none`` / ``error`` / ``unavailable``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from tradingagents.agents.analysts.company_themes import squash
from tradingagents.agents.structured import NO_EXTERNAL_TOOLS, invoke_structured

MAX_ISSUES = 3
MAX_NEWS = 25
_MIN_EVIDENCE_CHARS = 8
_MAX_TITLE_CHARS = 40
_MAX_SUMMARY_CHARS = 200
_ELLIPSIS = re.compile(r"\s*(?:\.{2,}|…)\s*$")
_NEWS_ITEM = re.compile(
    r"^- \*\*(?P<when>[^*]+)\*\*\s*\|\s*(?P<source>[^|\n]*?)\s*\|\s*(?P<title>[^\n]+?)\s*\n\s+- (?P<url>https?://\S+)",
    re.MULTILINE,
)


class Issue(BaseModel):
    title: str = Field(description="이슈를 한 줄로 (40자 이내). 예: 합병 증권신고서 정정 요구, 분기 최대 실적.")
    summary: str = Field(description="이 이슈가 무엇이고 왜 지금 주가에 중요한지 한 문장. 인용한 자료에 있는 사실만.")
    source_ids: list[str] = Field(description="근거로 삼은 자료 번호 (예: N3, D1). 하나 이상.")
    evidence: str = Field(
        description="근거 자료의 제목에서 한 글자도 바꾸지 않고 그대로 옮긴 구절 (8자 이상).")


class IssueList(BaseModel):
    issues: list[Issue] = Field(
        default_factory=list,
        description="최대 3개. 조회된 자료로 근거를 댈 수 있는 이슈만. 없으면 빈 목록.")


def parse_news(text: str) -> list[dict[str, str]]:
    """``get_news`` 의 Markdown 목록을 항목으로. 읽을 수 있는 항목이 없으면 빈 목록."""
    items = []
    for m in _NEWS_ITEM.finditer(text or ""):
        items.append({"kind": "news", "date": m["when"].strip()[:10], "source": m["source"].strip(),
                      "title": m["title"].strip(), "url": m["url"].strip()})
        if len(items) == MAX_NEWS:
            break
    return items


def parse_disclosures(text: str) -> list[dict[str, str]]:
    """``get_recent_disclosures`` JSON 을 항목으로. 읽을 수 없으면(실패 문구) 빈 목록."""
    try:
        data = json.loads(text)
        rows = data["items"]
    except (ValueError, TypeError, KeyError):
        return []
    return [{"kind": "disclosure", "date": r.get("date", ""), "source": r.get("filer", "") or "DART",
             "title": r.get("title", ""), "url": r.get("url", "")}
            for r in rows if isinstance(r, dict) and r.get("title")]


def numbered_sources(news: list[dict[str, str]], disclosures: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    """``{"N1": 기사, ..., "D1": 공시, ...}`` — 모델이 인용할 번호와 조회한 원자료."""
    out = {f"N{i}": item for i, item in enumerate(news, 1)}
    out.update({f"D{i}": item for i, item in enumerate(disclosures, 1)})
    return out


def _core(title: str) -> str:
    """헤드라인에서 줄임표를 뗀 본문 — 줄여진 제목의 인용 비교용."""
    return squash(_ELLIPSIS.sub("", title))


def verify_issues(issues: list[Issue], sources: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    """번호가 실재하고 인용구가 인용한 자료 제목에 있는 이슈만 (최대 ``MAX_ISSUES``), 출처는 조회 데이터로."""
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    for issue in issues:
        title, summary = squash(issue.title), squash(issue.summary)
        evidence = squash(issue.evidence).strip("\"'“”‘’")
        if not title or len(title) > _MAX_TITLE_CHARS or title in seen:
            continue
        if not summary or len(summary) > _MAX_SUMMARY_CHARS:
            continue
        ids = [i for i in dict.fromkeys(squash(x).upper() for x in issue.source_ids) if i in sources]
        if not ids or len(evidence) < _MIN_EVIDENCE_CHARS:
            continue
        if not any(evidence in _core(sources[i]["title"]) for i in ids):
            continue
        seen.add(title)
        kept.append({"title": title, "summary": summary, "evidence": evidence,
                     "sources": [{"id": i, **sources[i]} for i in ids]})
        if len(kept) == MAX_ISSUES:
            break
    return kept


def _prompt(instrument_context: str, sources: dict[str, dict[str, str]]) -> str:
    lines = "\n".join(
        f"[{sid}] {s['date']} · {s['source']} · {s['title']}" for sid, s in sources.items())
    return (
        f"{instrument_context}\n\n"
        "아래는 이 종목에 대해 조회한 최근 뉴스 헤드라인(N)과 DART 공시 제목(D)입니다. "
        f"지금 이 종목에 영향을 주는 **핵심 이슈**를 최대 {MAX_ISSUES}개 고르세요.\n\n"
        "규칙:\n"
        "- 아래 자료만 근거로 삼으세요. 자료에 없는 사건·수치·원인을 학습 지식으로 덧붙이지 마세요.\n"
        "- 이 종목 자체에 관한 이슈만. 시장 전체 시황(지수 급락·사이드카 등)은 이 종목이 직접 언급된 자료일 때만 쓰세요.\n"
        "- 각 이슈에 근거 자료 번호(source_ids)와, 그 자료의 **제목에서 한 글자도 바꾸지 않고 그대로 옮긴 구절**"
        "(evidence)을 쓰세요. 요약·말바꿈·'...' 포함 금지. 그대로 옮기지 못하면 그 이슈는 빼세요.\n"
        "- summary 는 한 문장, 인용한 자료에 있는 사실만. 전문 용어(마일스톤, 증권신고서 등)는 짧게 풀어 쓰세요.\n"
        "- 근거를 댈 수 있는 이슈가 없으면 빈 목록을 돌려주세요.\n\n"
        f"{NO_EXTERNAL_TOOLS}\n\n## 조회된 자료\n{lines}\n"
    )


def extract_issues(
    structured_llm: Any | None, instrument_context: str, news_text: str, disclosures_text: str,
) -> dict[str, Any]:
    """뉴스·공시에서 근거 있는 핵심 이슈를 뽑는다. 실패해도 예외를 내지 않는다 (분석가를 멈추지 않는다)."""
    sources = numbered_sources(parse_news(news_text), parse_disclosures(disclosures_text))
    if not sources:
        return {"status": "unavailable", "issues": [], "reason": "조회된 뉴스·공시가 없어 핵심 이슈를 정하지 않았습니다."}
    if structured_llm is None:
        return {"status": "unavailable", "issues": [], "reason": "모델이 구조화 출력을 지원하지 않아 핵심 이슈를 정하지 않았습니다."}
    result = invoke_structured(structured_llm, _prompt(instrument_context, sources), "Company Issues")
    if result is None:
        return {"status": "error", "issues": [], "reason": "핵심 이슈 추출 호출이 실패했습니다."}
    issues = verify_issues(result.issues, sources)
    if not issues:
        return {"status": "none", "issues": [], "reason": "조회한 뉴스·공시에서 근거를 확인할 수 있는 핵심 이슈가 없습니다."}
    return {"status": "ok", "issues": issues, "reason": ""}
