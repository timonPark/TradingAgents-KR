"""CLI config precedence (#976, #977).

An explicit environment override for the debate/risk round counts, or the
checkpoint flag, must win over the interactive research-depth selection — the CLI
must not clobber an env-configured value back to a prompt/flag default.
"""

from unittest import mock

import pytest

import cli.main as m
import cli.run as cli_run

# Minimal selections dict shaped like get_user_selections()'s return value.
# Task 2 (#21): provider 는 claude-code 고정, backend_url/provider-specific
# effort 키 제거, effort/quick_effort 로 통일.
SELECTIONS = {
    "research_depth": 5,
    "quick_think_llm": "haiku",
    "deep_think_llm": "sonnet",
    "llm_provider": "claude-code",
    "effort": "high",
    "quick_effort": "medium",
    "output_language": "Korean",
}


def test_research_depth_sets_both_rounds_without_env(monkeypatch):
    for var in ("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "TRADINGAGENTS_MAX_RISK_ROUNDS"):
        monkeypatch.delenv(var, raising=False)
    cfg = cli_run._build_run_config(SELECTIONS, checkpoint=None)
    assert cfg["max_debate_rounds"] == 5
    assert cfg["max_risk_discuss_rounds"] == 5


def test_env_round_counts_win_over_selection(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "2")
    monkeypatch.setenv("TRADINGAGENTS_MAX_RISK_ROUNDS", "4")
    # DEFAULT_CONFIG already reflects the env (applied at import); emulate that.
    patched = dict(cli_run.DEFAULT_CONFIG, max_debate_rounds=2, max_risk_discuss_rounds=4)
    with mock.patch.object(cli_run, "DEFAULT_CONFIG", patched):
        cfg = cli_run._build_run_config(SELECTIONS, checkpoint=None)
    assert cfg["max_debate_rounds"] == 2  # env value, not research_depth=5
    assert cfg["max_risk_discuss_rounds"] == 4


def test_partial_env_only_overrides_that_count(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "2")
    monkeypatch.delenv("TRADINGAGENTS_MAX_RISK_ROUNDS", raising=False)
    patched = dict(cli_run.DEFAULT_CONFIG, max_debate_rounds=2)
    with mock.patch.object(cli_run, "DEFAULT_CONFIG", patched):
        cfg = cli_run._build_run_config(SELECTIONS, checkpoint=None)
    assert cfg["max_debate_rounds"] == 2  # env wins
    assert cfg["max_risk_discuss_rounds"] == 5  # falls through to research_depth


def test_checkpoint_none_preserves_env_default():
    patched = dict(cli_run.DEFAULT_CONFIG, checkpoint_enabled=True)  # e.g. env-enabled
    with mock.patch.object(cli_run, "DEFAULT_CONFIG", patched):
        cfg = cli_run._build_run_config(SELECTIONS, checkpoint=None)
    assert cfg["checkpoint_enabled"] is True  # not clobbered back to False


@pytest.mark.parametrize("flag", [True, False])
def test_checkpoint_flag_overrides_env(flag):
    patched = dict(cli_run.DEFAULT_CONFIG, checkpoint_enabled=not flag)
    with mock.patch.object(cli_run, "DEFAULT_CONFIG", patched):
        cfg = cli_run._build_run_config(SELECTIONS, checkpoint=flag)
    assert cfg["checkpoint_enabled"] is flag


# test_glm_resolves_to_the_endpoint_its_key_belongs_to 는 Task 2 (#21) 에서
# 삭제되었습니다 — GLM/Zhipu 지역 provider 는 하드 포크로 제거되었고 Claude Code
# 는 로컬 CLI 호출이라 백엔드 URL 자체가 없습니다.


@pytest.mark.unit
def test_a_half_set_round_count_says_which_value_won(capsys, monkeypatch):
    """With only one of the two round-count variables set, the depth prompt is
    still shown but half the answer is discarded; the user was never told."""

    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "1")
    monkeypatch.delenv("TRADINGAGENTS_MAX_RISK_ROUNDS", raising=False)
    printed = []
    monkeypatch.setattr(m.console, "print", lambda *a, **k: printed.append(str(a[0]) if a else ""))

    config = cli_run._build_run_config({
        "ticker": "005930", "analysis_date": "2026-09-01", "asset_type": "stock",
        "analysts": [], "research_depth": 5, "llm_provider": "claude-code",
        "quick_think_llm": "haiku", "deep_think_llm": "sonnet",
        "effort": "high", "quick_effort": "medium", "output_language": "Korean",
    }, None)

    assert config["max_risk_discuss_rounds"] == 5
    assert any("TRADINGAGENTS_MAX_DEBATE_ROUNDS" in line for line in printed), printed


# test_a_tier_s_thinking_setting_survives_a_main_provider_that_has_none 는
# Task 2 (#21) 에서 삭제되었습니다 — provider-specific thinking/reasoning 설정
# (google_thinking_level, openai_reasoning_effort, anthropic_effort) 은 전부
# 제거되었고 Claude Code 의 effort/quick_effort 로 통일되었습니다.
