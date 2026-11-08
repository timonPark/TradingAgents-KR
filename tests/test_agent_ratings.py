"""#174: 에이전트별 등급 판독기.

규칙은 krx-screener 가 실제 로그 13개로 검증해 쓰던 것을 서버로 옮긴 것이다.
"""

from __future__ import annotations

import pytest

from tradingagents.agent_ratings import AGENT_REPORT_FILES, parse_agent_rating
from tradingagents.reporting import _SECTIONS


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("**등급**: 매수", "Buy"),
        ("- **등급**: 비중 확대", "Overweight"),
        ("- 등급: 비중확대", "Overweight"),
        ("**등급: 보유.**", "Hold"),
        ("### 결론\n**Rating**: Underweight", "Underweight"),
        ("**등급**: SELL", "Sell"),  # 대문자
        ("Aggressive Analyst: **등급**: 보유", "Hold"),  # 접두 라벨 뒤
        ("**투자 논리**: **등급: 보유.**", "Hold"),
        ("| **등급** | **보유** | 근거 |", "Hold"),  # 표
        ("**등급**: 보유\n\n**최종 거래 제안**: 매도", "Hold"),  # 3단계 제안은 읽지 않는다
        ("**등급**: 매수\n...\n**등급**: 매수", "Buy"),  # 같은 값이 여러 번이면 그 값
    ],
)
def test_reads_the_five_tier_rating_from_its_label(text, expected):
    assert parse_agent_rating(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "등급 없이 끝나는 글입니다.",
        "**최종 거래 제안**: 매수",  # 3단계 제안만 있는 글은 5단계 등급으로 바꿀 수 없다
        "| 최종 거래 제안 | **보유** | 근거 | — |",
        "**등급**: REDUCE",  # 5단계에 없는 값은 지어내지 않는다
        "**등급**: 보유\n\n... 조건이 바뀌면 ...\n\n**등급**: 매수",  # 서로 다른 값 = 어느 쪽인지 모른다
        "아래 등급은 펀더멘털만 반영한 것입니다.",  # 문장 속의 '등급'
        "제 등급은 비중 축소이고, 실행은 매도입니다.",  # 콜론 없는 문장
        "**등급**: 보유분을 줄입니다",  # 값 뒤에 글자가 붙으면 다른 낱말
        "**등급**:\n매수",  # 다음 줄의 값은 이 줄의 값이 아니다
        "애널리스트 컨센서스 등급: 매수 유지",  # 다른 사람의 의견
        "현재 등급: 보유 (조건 충족 시 상향)",  # 문장 속 설명
        "Operating rating: Buy",
    ],
)
def test_text_without_one_readable_rating_gives_none(text):
    assert parse_agent_rating(text) is None


def test_recommendation_label_is_read_only_for_the_research_manager():
    manager = "**추천**: 비중 축소\n\n**근거**: **추천: 비중 축소 (Underweight)**\n\n본문"
    analyst = "애널리스트 추천: 매수 유지\n\n**등급**: 보유"

    assert parse_agent_rating(manager, "research_manager") == "Underweight"
    assert parse_agent_rating(manager, "news") is None  # 다른 에이전트의 '추천' 은 등급이 아니다
    assert parse_agent_rating(analyst, "news") == "Hold"  # '추천: 매수' 가 충돌로 읽히지 않는다


def test_the_ten_agents_have_files_that_the_report_writer_produces():
    written = {f"{folder}/{filename}" for _h, folder, agents in _SECTIONS for _a, filename, _p in agents}

    assert len(AGENT_REPORT_FILES) == 10
    assert set(AGENT_REPORT_FILES.values()) <= written
    # 5단계 등급이 없는 감성 분석가·트레이더는 읽는 대상이 아니다.
    assert "1_analysts/sentiment.md" not in AGENT_REPORT_FILES.values()
    assert "3_trading/trader.md" not in AGENT_REPORT_FILES.values()
