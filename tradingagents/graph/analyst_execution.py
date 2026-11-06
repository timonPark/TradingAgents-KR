from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class AnalystNodeSpec:
    key: str
    agent_node: str
    report_key: str
    # 보고서 차트의 원본 데이터 키 (#144). 분석가 서브그래프는 output_schema 에 있는 키만
    # 부모 상태로 내보내므로, 여기에 이름을 올려야 최종 상태까지 남는다.
    data_key: str | None = None
    # 같은 이유로 최종 상태까지 내보낼 추가 키 (#166: 뉴스 분석가의 핵심 이슈)
    extra_data_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalystExecutionPlan:
    specs: list[AnalystNodeSpec]


# Task 3 (#32): 모든 분석가가 사전조회 패턴으로 전환되어 ToolNode 바인딩이 완전
# 제거됨 (ADR-0002). spec 의 `tools` 필드도 함께 삭제.
ANALYST_NODE_SPECS: dict[str, AnalystNodeSpec] = {
    "market": AnalystNodeSpec(
        key="market",
        agent_node="Market Analyst",
        report_key="market_report",
        data_key="market_data",
    ),
    "social": AnalystNodeSpec(
        # Saved configs select this analyst as "social". Pre-fetches its sources
        # (News + StockTwits + Reddit) before calling the model.
        key="social",
        agent_node="Sentiment Analyst",
        report_key="sentiment_report",
    ),
    "news": AnalystNodeSpec(
        key="news",
        agent_node="News Analyst",
        report_key="news_report",
        data_key="macro_data",
        extra_data_keys=("company_issues",),
    ),
    "fundamentals": AnalystNodeSpec(
        key="fundamentals",
        agent_node="Fundamentals Analyst",
        report_key="fundamentals_report",
        data_key="fundamentals_data",
    ),
}


def build_analyst_execution_plan(
    selected_analysts: Iterable[str],
) -> AnalystExecutionPlan:
    specs: list[AnalystNodeSpec] = []
    for analyst_key in selected_analysts:
        spec = ANALYST_NODE_SPECS.get(analyst_key)
        if spec is None:
            raise ValueError(f"unknown analyst key: {analyst_key}")
        specs.append(spec)

    if not specs:
        raise ValueError("at least one analyst must be selected")

    return AnalystExecutionPlan(specs=specs)
