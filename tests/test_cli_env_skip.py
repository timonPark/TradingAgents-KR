"""Tests for env-driven CLI behavior.

The config-layer override (TRADINGAGENTS_* → DEFAULT_CONFIG) is covered by
test_env_overrides.py. These tests cover the CLI layer: an env-configured
model/language/effort must skip its interactive prompt and use the value.

Task 2 (#21) removed provider-selection prompts (claude-code is fixed) and
provider-specific reasoning/thinking configuration. The remaining skippable
prompts are: output language, research depth, think-model (deep/quick), and
effort (deep/quick).
"""

import os
import unittest
from unittest import mock

import pytest

import cli.selections as cli_selections


@pytest.mark.unit
class TestCliSkipsPromptsFromEnv(unittest.TestCase):
    def test_env_config_skips_llm_prompts(self):
        env = {
            "TRADINGAGENTS_DEEP_THINK_LLM": "opus",
            "TRADINGAGENTS_QUICK_THINK_LLM": "haiku",
            "TRADINGAGENTS_OUTPUT_LANGUAGE": "Japanese",
            "TRADINGAGENTS_EFFORT": "max",
            "TRADINGAGENTS_QUICK_EFFORT": "low",
        }
        fake_cfg = dict(cli_selections.DEFAULT_CONFIG)
        fake_cfg.update({
            "quick_think_llm": "haiku",
            "deep_think_llm": "opus",
            "output_language": "Japanese",
            "effort": "max",
            "quick_effort": "low",
        })

        with mock.patch.dict(os.environ, env, clear=False), \
             mock.patch.object(cli_selections, "DEFAULT_CONFIG", fake_cfg), \
             mock.patch.object(cli_selections.updates, "enabled", return_value=False), \
             mock.patch.object(cli_selections, "get_ticker", return_value="005930"), \
             mock.patch.object(cli_selections, "get_analysis_date", return_value="2026-05-29"), \
             mock.patch.object(cli_selections, "select_analysts", return_value=[]), \
             mock.patch.object(cli_selections, "select_research_depth", return_value=1), \
             mock.patch.object(cli_selections, "ask_output_language") as prompt_lang, \
             mock.patch.object(cli_selections, "select_shallow_thinking_agent") as prompt_quick, \
             mock.patch.object(cli_selections, "select_deep_thinking_agent") as prompt_deep, \
             mock.patch.object(cli_selections, "ask_effort") as prompt_effort:
            sel = cli_selections.get_user_selections()

        # 환경변수가 설정된 프롬프트는 전부 skip 되어야 함.
        prompt_lang.assert_not_called()
        prompt_quick.assert_not_called()
        prompt_deep.assert_not_called()
        prompt_effort.assert_not_called()

        # 환경변수 값이 selections 로 흘러감 (provider 는 하드코딩 claude-code).
        self.assertEqual(sel["llm_provider"], "claude-code")
        self.assertEqual(sel["quick_think_llm"], "haiku")
        self.assertEqual(sel["deep_think_llm"], "opus")
        self.assertEqual(sel["output_language"], "Japanese")
        self.assertEqual(sel["effort"], "max")
        self.assertEqual(sel["quick_effort"], "low")


@pytest.mark.unit
class TestResearchDepthSkippedFromEnv(unittest.TestCase):
    def test_both_round_envs_skip_depth_prompt(self):
        env = {
            "TRADINGAGENTS_MAX_DEBATE_ROUNDS": "2",
            "TRADINGAGENTS_MAX_RISK_ROUNDS": "4",
        }
        fake_cfg = dict(cli_selections.DEFAULT_CONFIG)
        fake_cfg.update({"max_debate_rounds": 2, "max_risk_discuss_rounds": 4})

        with mock.patch.dict(os.environ, env, clear=False), \
             mock.patch.object(cli_selections, "DEFAULT_CONFIG", fake_cfg), \
             mock.patch.object(cli_selections.updates, "enabled", return_value=False), \
             mock.patch.object(cli_selections, "get_ticker", return_value="005930"), \
             mock.patch.object(cli_selections, "get_analysis_date", return_value="2026-05-29"), \
             mock.patch.object(cli_selections, "select_analysts", return_value=[]), \
             mock.patch.object(cli_selections, "select_research_depth") as prompt_depth, \
             mock.patch.object(cli_selections, "ask_output_language", return_value="Korean"), \
             mock.patch.object(cli_selections, "select_shallow_thinking_agent", return_value="haiku"), \
             mock.patch.object(cli_selections, "select_deep_thinking_agent", return_value="sonnet"), \
             mock.patch.object(cli_selections, "ask_effort", return_value="high"):
            sel = cli_selections.get_user_selections()

        # Research depth 프롬프트는 skip 되고 env 값이 사용됨.
        prompt_depth.assert_not_called()
        self.assertEqual(sel["research_depth"], 2)


@pytest.mark.unit
class TestEffortSkippedFromEnv(unittest.TestCase):
    """TRADINGAGENTS_EFFORT 와 TRADINGAGENTS_QUICK_EFFORT 가 각각 독립적으로 skip."""

    def test_deep_effort_env_skips_prompt(self):
        env = {"TRADINGAGENTS_EFFORT": "high"}
        fake_cfg = dict(cli_selections.DEFAULT_CONFIG)
        fake_cfg["effort"] = "high"

        with mock.patch.dict(os.environ, env, clear=False), \
             mock.patch.object(cli_selections, "DEFAULT_CONFIG", fake_cfg), \
             mock.patch.object(cli_selections.updates, "enabled", return_value=False), \
             mock.patch.object(cli_selections, "get_ticker", return_value="005930"), \
             mock.patch.object(cli_selections, "get_analysis_date", return_value="2026-05-29"), \
             mock.patch.object(cli_selections, "select_analysts", return_value=[]), \
             mock.patch.object(cli_selections, "select_research_depth", return_value=1), \
             mock.patch.object(cli_selections, "ask_output_language", return_value="Korean"), \
             mock.patch.object(cli_selections, "select_shallow_thinking_agent", return_value="haiku"), \
             mock.patch.object(cli_selections, "select_deep_thinking_agent", return_value="sonnet"), \
             mock.patch.object(cli_selections, "ask_effort", return_value="medium") as prompt_effort:
            sel = cli_selections.get_user_selections()

        # deep tier effort 는 env 로 skip; quick 는 여전히 묻는다.
        tiers_asked = [c.args[0] for c in prompt_effort.call_args_list if c.args]
        self.assertNotIn("deep", tiers_asked)
        self.assertIn("quick", tiers_asked)
        self.assertEqual(sel["effort"], "high")

    def test_quick_effort_env_skips_prompt(self):
        env = {"TRADINGAGENTS_QUICK_EFFORT": "low"}
        fake_cfg = dict(cli_selections.DEFAULT_CONFIG)
        fake_cfg["quick_effort"] = "low"

        with mock.patch.dict(os.environ, env, clear=False), \
             mock.patch.object(cli_selections, "DEFAULT_CONFIG", fake_cfg), \
             mock.patch.object(cli_selections.updates, "enabled", return_value=False), \
             mock.patch.object(cli_selections, "get_ticker", return_value="005930"), \
             mock.patch.object(cli_selections, "get_analysis_date", return_value="2026-05-29"), \
             mock.patch.object(cli_selections, "select_analysts", return_value=[]), \
             mock.patch.object(cli_selections, "select_research_depth", return_value=1), \
             mock.patch.object(cli_selections, "ask_output_language", return_value="Korean"), \
             mock.patch.object(cli_selections, "select_shallow_thinking_agent", return_value="haiku"), \
             mock.patch.object(cli_selections, "select_deep_thinking_agent", return_value="sonnet"), \
             mock.patch.object(cli_selections, "ask_effort", return_value="medium") as prompt_effort:
            sel = cli_selections.get_user_selections()

        # quick tier effort 는 env 로 skip; deep 는 여전히 묻는다.
        tiers_asked = [c.args[0] for c in prompt_effort.call_args_list if c.args]
        self.assertNotIn("quick", tiers_asked)
        self.assertIn("deep", tiers_asked)
        self.assertEqual(sel["quick_effort"], "low")


if __name__ == "__main__":
    unittest.main()
