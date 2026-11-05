"""Shared 5-tier rating vocabulary and a deterministic heuristic parser.

The same five-tier scale (Buy, Overweight, Hold, Underweight, Sell) is used by:
- The Research Manager (investment plan recommendation)
- The Portfolio Manager (final position decision; its free-text fallback is read here)
- The memory log (rating tag stored alongside each decision entry)

Centralising it here avoids drift between those call sites.

``extract_rating`` returns ``None`` when no rating can be found, and every
caller turns that into ``REVIEW`` rather than a tradeable position: a decision
nobody can read is not a Hold, and a Hold recorded in its place is quoted back to
the next run as a call that was never made (#1170).

Task 9b (#81): KRX 하드 포크 (ADR-0003) 에 따라 한국어 라벨 ("등급", "최종 거래
제안") 도 수용. 값 (BUY/SELL/HOLD) 은 영어 유지라 값 추출 로직 불변.
"""

from __future__ import annotations

import re
import unicodedata

# Canonical, ordered 5-tier scale (most bullish to most bearish).
RATINGS_5_TIER: tuple[str, ...] = (
    "Buy", "Overweight", "Hold", "Underweight", "Sell",
)

# Signal emitted when the model's decision has no recognizable rating. It is not
# a tradeable position: it flags output that needs a human/re-run rather than
# silently degrading to Hold. Callers that map the signal onto the 5-tier enum
# (e.g. ``PortfolioRating(signal)``) should guard with ``is_review`` first.
RATING_REVIEW = "REVIEW"

_RATING_SET = {r.lower() for r in RATINGS_5_TIER}

# #145: 화면에 보이는 한국어 표기. 내부 값(파서·백테스트·메모리 로그)은 영어 그대로 두고
# 표시 계층에서만 바꾼다. 파서는 한국어 표기도 같은 등급으로 읽는다.
RATING_KO: dict[str, str] = {
    "Buy": "매수", "Overweight": "비중 확대", "Hold": "보유",
    "Underweight": "비중 축소", "Sell": "매도",
}
_KO_TO_RATING = {ko.replace(" ", ""): en for en, ko in RATING_KO.items()}
# 값 자리에 올 수 있는 토큰. 두 단어짜리 한국어 표기("비중 확대")를 \w+ 보다 먼저 시도한다.
_VALUE = r"(비중\s*확대|비중\s*축소|\w+)"


def display_rating(rating: str) -> str:
    """내부 등급 값의 한국어 표기. 알 수 없는 값(예: ``REVIEW``)은 그대로 돌려준다."""
    return RATING_KO.get(rating, rating)


def _canonical(value: str) -> str | None:
    """영어 값 또는 한국어 표기를 내부 등급 값(``Buy`` 등)으로. 등급이 아니면 None."""
    if value.lower() in _RATING_SET:
        return value.capitalize()
    return _KO_TO_RATING.get(re.sub(r"\s+", "", value))

# 라벨 토큰: 영어 ("rating\b", 단어 경계 필수) + 한국어 ("등급" / "최종 거래 제안",
# 자연 경계). "최종 거래 제안" 은 공백 / 가운뎃점 (·) 구분자 수용.
_LABEL_TOKEN = r"(?:rating\b|등급|최종[\s·]*거래[\s·]*제안)"

# Matches "Rating: X" / "rating - X" / "Rating — **X**" / "등급: X" /
# "최종 거래 제안: X" — tolerates markdown bold wrappers and any dash or colon
# a model writes as the separator. "rating" 영어는 단어 경계 (lookbehind +
# `\b`) 로 "Operating margin: Sell-side" 를 걸러냄.
_RATING_LABEL_RE = re.compile(
    r"(?<![a-z])" + _LABEL_TOKEN + r"[^:\-‐-―]*[:\-‐-―][\s*]*" + _VALUE,
    re.IGNORECASE,
)

# The decision's own rating line, in the shape the Portfolio Manager is asked to
# open with ("- **Rating**: X", "**Final Rating**: X", "## Our rating - X",
# "**등급**: X", "**최종 등급**: X", "- **최종 거래 제안**: X"): an optional
# list marker, emphasis and heading marks, and only words naming the decision
# itself before the label. "Consensus rating: Buy" ("합의 등급: Buy") 는 다른
# 당사자의 것이라 수식어 리스트에서 제외.
_OWN_QUALIFIER = (
    r"(?:(?:final|our|overall|my|recommended|updated|revised|new|current|"
    r"최종|우리|전체|권장|수정|갱신|신규|현재)\s*)*"
)
_RATING_LINE_RE = re.compile(
    r"\s*(?P<item>(?:[-+*•]|\d+[.)])\s+)?[\s*_#]*" + _OWN_QUALIFIER
    + _LABEL_TOKEN + r"[^\w:\-‐-―]*[:\-‐-―][\s*]*(?P<value>비중\s*확대|비중\s*축소|\w+)",
    re.IGNORECASE,
)

# A line presenting the scale rather than a decision ("Rating Scale: Buy, ...",
# "등급 척도: Buy, ..."): 스케일/옵션/범례 라인은 결정이 아니라 모델이 복붙한 범례.
_RATING_SCALE_RE = re.compile(
    r"(?:rating\s*(scale|options|legend)|등급\s*(?:척도|옵션|범례))",
    re.IGNORECASE,
)

def canonical_rating(value: str) -> str | None:
    """영어 값·한국어 표기·``REVIEW`` 를 내부 값으로. 해석 불가면 None (#145)."""
    value = value.strip()
    return value if value == RATING_REVIEW else _canonical(value)


def extract_rating(text: str) -> str | None:
    """Extract a 5-tier rating from its label, or ``None`` if there is none.

    Reads an explicit "Rating: X" / "등급: X" / "최종 거래 제안: X" label
    (tolerant of markdown bold) in the NFKC-normalized text, so fullwidth
    punctuation like ``Rating：Overweight`` matches as ASCII does: the decision's
    opening rating line, else its own rating lines or, failing those, every
    label, when they agree.
    """
    if not text:
        return None
    norm = unicodedata.normalize("NFKC", text)

    # The decision is asked to open with its rating, so a first line (after any
    # headings) in that shape is the call. A list item there may also be a quote
    # heading a list of other parties' ratings, so it counts with the decision's
    # other rating lines, which leave out list items; failing those, every label
    # counts. Either way they must agree: ratings that differ, with nothing
    # marking which one is the call, are no call (#1170). Lines presenting the
    # scale itself are a legend the model echoed, not a call.
    lines = [line for line in norm.splitlines() if line.strip() and not _RATING_SCALE_RE.search(line)]
    first = next((line for line in lines if not line.lstrip().startswith("#")
                  or _RATING_LINE_RE.match(line)), "")
    m = _RATING_LINE_RE.match(first)
    opening = m if m and _canonical(m.group("value")) else None
    if opening and not opening.group("item"):
        return _canonical(opening.group("value"))

    own = [_canonical(opening.group("value"))] if opening else []
    labels = []
    for line in lines:
        m = _RATING_LINE_RE.match(line)
        if m and not m.group("item") and _canonical(m.group("value")):
            own.append(_canonical(m.group("value")))
        labels += [c for v in _RATING_LABEL_RE.findall(line) if (c := _canonical(v))]
    # Without a label there is no call to read: a rating word in the prose may be
    # one the text argues against ("not a Sell"), and reading it reports a
    # direction nobody decided.
    found = own or labels
    return found[0] if found and len(set(found)) == 1 else None


def parse_rating(text: str, default: str = RATING_REVIEW) -> str:
    """Extract a 5-tier rating, or ``REVIEW`` when the decision has none.

    For callers that need a string for every decision, such as the memory log's
    entry tag. The default is the review sentinel, never a tradeable rating.
    """
    rating = extract_rating(text)
    return rating if rating is not None else default


def run_rating(final_state: dict) -> str:
    """A finished run's rating: the Portfolio Manager's own, else read from its decision.

    The fallback serves a state without ``final_rating``, such as a run an older
    version completed and a checkpoint hands back unchanged.
    """
    return final_state.get("final_rating") or parse_rating(final_state.get("final_trade_decision", ""))


def is_review(signal: str) -> bool:
    """Whether a signal is the non-tradeable REVIEW sentinel (#1170)."""
    return signal == RATING_REVIEW
