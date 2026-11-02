from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class AnalystNodeSpec:
    key: str
    agent_node: str
    report_key: str
    tools: tuple = ()


@dataclass(frozen=True)
class AnalystExecutionPlan:
    specs: list[AnalystNodeSpec]


ANALYST_NODE_SPECS: dict[str, AnalystNodeSpec] = {
    "market": AnalystNodeSpec(
        # Task 3a (#33): 사전조회 패턴으로 전환되어 ToolNode 바인딩 불필요.
        # analyst 내부에서 Python 이 데이터를 선조회하고 단일 LLM 호출로 완결.
        key="market",
        agent_node="Market Analyst",
        report_key="market_report",
    ),
    "social": AnalystNodeSpec(
        # Saved configs select this analyst as "social". It fetches its
        # sources before calling the model, so it has no tools.
        key="social",
        agent_node="Sentiment Analyst",
        report_key="sentiment_report",
    ),
    "news": AnalystNodeSpec(
        # Task 3c (#35): 사전조회 패턴으로 전환되어 ToolNode 바인딩 불필요.
        key="news",
        agent_node="News Analyst",
        report_key="news_report",
    ),
    "fundamentals": AnalystNodeSpec(
        # Task 3b (#34): 사전조회 패턴으로 전환되어 ToolNode 바인딩 불필요.
        key="fundamentals",
        agent_node="Fundamentals Analyst",
        report_key="fundamentals_report",
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


