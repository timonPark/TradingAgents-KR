import unittest

from tradingagents.graph.analyst_execution import (
    build_analyst_execution_plan,
)


class AnalystExecutionPlanTests(unittest.TestCase):
    def test_build_plan_preserves_selected_order(self):
        plan = build_analyst_execution_plan(["news", "market"])

        self.assertEqual([spec.key for spec in plan.specs], ["news", "market"])
        self.assertEqual(plan.specs[0].agent_node, "News Analyst")
        self.assertEqual(plan.specs[0].report_key, "news_report")
        self.assertFalse(hasattr(plan.specs[0], "clear_node"))

    def test_rejects_unknown_analyst_keys(self):
        with self.assertRaises(ValueError):
            build_analyst_execution_plan(["market", "macro"])

    def test_social_key_displays_as_sentiment_analyst(self):
        # The wire key stays "social" for saved-config back-compat, but the
        # user-visible agent_node label must match the v0.2.5 rename so the
        # wall-time summary and any future consumer of agent_node says
        # "Sentiment Analyst" rather than the legacy "Social Analyst".
        plan = build_analyst_execution_plan(["social"])
        spec = plan.specs[0]
        self.assertEqual(spec.key, "social")
        self.assertEqual(spec.agent_node, "Sentiment Analyst")
        self.assertEqual(spec.report_key, "sentiment_report")


class AnalystChartDataTests(unittest.TestCase):
    """#151: 보고서 차트의 원본 데이터가 분석가 서브그래프를 통과해 부모 상태까지 올라온다.

    분석가는 서브그래프의 ``output_schema`` 에 있는 키만 부모에 내보낸다. 키를 빠뜨리면 노드는
    값을 반환해도 최종 상태에는 없다 — 단위 테스트가 상태를 직접 만들면 놓치는 결함.
    """

    def test_specs_name_the_chart_data_each_analyst_keeps(self):
        keys = {s.key: s.data_key for s in build_analyst_execution_plan(
            ["market", "social", "news", "fundamentals"]).specs}
        self.assertEqual(keys["market"], "market_data")
        self.assertEqual(keys["news"], "macro_data")
        self.assertIsNone(keys["social"])

    def test_chart_data_survives_the_analyst_subgraph(self):
        from tradingagents.graph.setup import _analyst_graph

        for analyst in ("market", "news"):
            spec = build_analyst_execution_plan([analyst]).specs[0]

            def node(state, spec=spec):
                return {spec.report_key: "리포트", spec.data_key: {"k": "v"}}

            out = _analyst_graph(spec, node).invoke({"messages": []})
            self.assertEqual(out[spec.report_key], "리포트", analyst)
            self.assertEqual(out[spec.data_key], {"k": "v"}, analyst)

    def test_analyst_without_chart_data_exports_only_its_report(self):
        from tradingagents.graph.setup import _analyst_graph

        spec = build_analyst_execution_plan(["social"]).specs[0]
        out = _analyst_graph(spec, lambda state: {spec.report_key: "리포트"}).invoke({"messages": []})
        self.assertEqual(out[spec.report_key], "리포트")
        self.assertNotIn("market_data", out)
