"""에이전트별 5단계 등급 판독기 (#174).

리포트의 에이전트별 섹션 글(``1_analysts/market.md`` 등)에서 그 에이전트가 낸
5단계 등급을 읽는다. 클라이언트(krx-screener)가 에이전트 등급의 평균으로 점수를
내므로, 글 모양을 해석하는 규칙을 서버가 한곳에서 갖고 API 로 준다.

- 섹션 파일이 에이전트를 정한다. 글의 줄 순서로 짐작하지 않는다.
  감성 분석가와 트레이더의 글에는 5단계 등급이 없어 읽지 않는다 (그래서 에이전트는 10개다).
- 라벨은 ``등급`` (리서치 매니저는 ``추천`` 도 쓴다), 영어 ``Rating``. 라벨은 줄 머리이거나
  ``접두 라벨: `` 바로 뒤에 올 때만 라벨이다. 문장 속의 "컨센서스 등급: 매수" 는 다른 사람의
  의견이라서 읽지 않는다.
- 값은 5단계 등급의 한국어·영어 표기뿐이다 (대소문자 무시). ``REDUCE`` 같은 다른 값은 읽지 않는다.
- ``최종 거래 제안`` 은 읽지 않는다. 등급을 3단계(BUY/HOLD/SELL)로 뭉갠 값이라서
  (비중 축소 → 매도) 5단계 등급 대신 쓰면 점수가 한쪽으로 치우친다. ``rating.extract_rating`` 은
  그 라벨도 읽으므로 여기서는 쓰지 않는다.
- 한 글에 서로 다른 값이 나오면 어느 쪽이 그 에이전트의 등급인지 알 수 없으므로 비워 둔다
  (같은 값이 여러 번이면 그 값이다). 읽지 못해도 오류가 아니라 그 에이전트만 빈다.
"""

from __future__ import annotations

import re

from tradingagents.agents.rating import RATING_KO, RATINGS_5_TIER

# 에이전트 → 리포트 트리 안의 섹션 파일. ``reporting._SECTIONS`` 의 파일과 같아야 한다
# (tests/test_agent_ratings.py 가 확인한다).
AGENT_REPORT_FILES: dict[str, str] = {
    "market": "1_analysts/market.md",
    "news": "1_analysts/news.md",
    "fundamentals": "1_analysts/fundamentals.md",
    "bull": "2_research/bull.md",
    "bear": "2_research/bear.md",
    "research_manager": "2_research/manager.md",
    "aggressive": "4_risk/aggressive.md",
    "conservative": "4_risk/conservative.md",
    "neutral": "4_risk/neutral.md",
    "portfolio_manager": "5_portfolio/decision.md",
}

_DEFAULT_LABELS = ("등급", "Rating")
_AGENT_LABELS: dict[str, tuple[str, ...]] = {"research_manager": ("등급", "추천", "Rating")}

# 5단계 등급의 표기 → 내부 값. 한국어는 공백을 없앤 꼴로 비교한다 ("비중 확대" = "비중확대").
_BY_NAME = {ko.replace(" ", ""): rating for rating, ko in RATING_KO.items()}
_BY_NAME.update({rating.lower(): rating for rating in RATINGS_5_TIER})

_NAMES = "|".join(
    sorted(
        {ko.replace(" ", r"[ \t]*") for ko in RATING_KO.values()} | set(RATINGS_5_TIER),
        key=len,
        reverse=True,
    )
)
# 값 바로 뒤에 글자가 붙으면 다른 낱말이다 (보유분, Buyback)
_VALUE = rf"({_NAMES})(?![가-힣A-Za-z])"
_SPACE = r"[ \t]*"  # 줄을 넘지 않는다: 다음 줄의 값은 이 줄의 값이 아니다


def _patterns(labels: tuple[str, ...]) -> tuple[re.Pattern[str], re.Pattern[str]]:
    label = "(?:" + "|".join(re.escape(x) for x in labels) + ")"
    # 문장 속 낱말이 아니라 라벨이어야 한다: 줄 머리(목록·제목 기호 허용)이거나 `접두 라벨: ` 바로 뒤.
    # `**등급**: 매수`, `- **등급**: 매수`, `Aggressive Analyst: **등급**: 보유`, `**투자 논리**: **등급: 보유.**`
    head = rf"(?:^|[:：]){_SPACE}(?:(?:[-•>]|#+|\d+\.){_SPACE})*\**{_SPACE}"
    inline = re.compile(
        rf"{head}{label}{_SPACE}\**{_SPACE}[:：]{_SPACE}\**{_SPACE}{_VALUE}", re.IGNORECASE | re.MULTILINE
    )
    # 표의 한 줄: `| **등급** | **보유** | … |`
    table = re.compile(rf"\|{_SPACE}\**{_SPACE}{label}{_SPACE}\**{_SPACE}\|{_SPACE}\**{_SPACE}{_VALUE}", re.IGNORECASE)
    return inline, table


_PATTERNS = {labels: _patterns(labels) for labels in {_DEFAULT_LABELS, *_AGENT_LABELS.values()}}


def parse_agent_rating(text: str, agent: str | None = None) -> str | None:
    """한 에이전트의 글에서 내부 등급 값(``Buy`` 등)을 읽는다. 읽지 못하거나 값이 엇갈리면 None."""
    found: set[str] = set()
    for pattern in _PATTERNS[_AGENT_LABELS.get(agent or "", _DEFAULT_LABELS)]:
        for match in pattern.finditer(text):
            found.add(_BY_NAME[re.sub(r"\s+", "", match.group(1)).lower()])
    return found.pop() if len(found) == 1 else None
