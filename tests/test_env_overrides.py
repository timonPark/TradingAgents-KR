"""Tests for TRADINGAGENTS_* env-var overlay onto DEFAULT_CONFIG."""

from __future__ import annotations

import os

import pytest

import tradingagents.default_config as default_config_module


def _config_with_env(monkeypatch, **overrides):
    """The defaults as the environment given here would set them."""
    for key in list(default_config_module._ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    for key, val in overrides.items():
        monkeypatch.setenv(key, val)
    return default_config_module.build_default_config()


def test_no_env_uses_built_in_defaults(monkeypatch):
    config = _config_with_env(monkeypatch)
    # Task 1f (#7) + ADR-0001: Claude Code 헤드리스가 하드 포크의 기본 백엔드.
    assert config["llm_provider"] == "claude-code"
    assert config["deep_think_llm"] == "sonnet"
    assert config["quick_think_llm"] == "haiku"
    assert config["effort"] == "high"
    assert config["quick_effort"] == "medium"
    assert config["max_debate_rounds"] == 1
    assert config["checkpoint_enabled"] is False


def test_string_overrides(monkeypatch):
    # Task 2 (#21): LLM_PROVIDER / LLM_BACKEND_URL env 매핑은 제거되었음 —
    # provider 는 claude-code 고정 (ADR-0001).
    config = _config_with_env(
        monkeypatch,
        TRADINGAGENTS_DEEP_THINK_LLM="opus",
        TRADINGAGENTS_QUICK_THINK_LLM="sonnet",
        TRADINGAGENTS_OUTPUT_LANGUAGE="Chinese",
    )
    assert config["deep_think_llm"] == "opus"
    assert config["quick_think_llm"] == "sonnet"
    assert config["output_language"] == "Chinese"


def test_int_coercion(monkeypatch):
    config = _config_with_env(
        monkeypatch,
        TRADINGAGENTS_MAX_DEBATE_ROUNDS="3",
        TRADINGAGENTS_MAX_RISK_ROUNDS="2",
    )
    assert config["max_debate_rounds"] == 3
    assert isinstance(config["max_debate_rounds"], int)
    assert config["max_risk_discuss_rounds"] == 2
    assert isinstance(config["max_risk_discuss_rounds"], int)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", True), ("True", True), ("1", True), ("yes", True), ("on", True),
        ("false", False), ("False", False), ("0", False), ("no", False), ("off", False),
    ],
)
def test_bool_coercion(monkeypatch, raw, expected):
    config = _config_with_env(monkeypatch, TRADINGAGENTS_CHECKPOINT_ENABLED=raw)
    assert config["checkpoint_enabled"] is expected


def test_effort_overrides(monkeypatch):
    """Claude Code `--effort` 티어별 env 로 설정 가능 (TRADINGAGENTS_EFFORT /
    TRADINGAGENTS_QUICK_EFFORT). provider-specific thinking/reasoning 노브는
    Task 2 (#21) 로 전부 제거됨."""
    config = _config_with_env(
        monkeypatch,
        TRADINGAGENTS_EFFORT="low",
        TRADINGAGENTS_QUICK_EFFORT="xhigh",
    )
    assert config["effort"] == "low"
    assert config["quick_effort"] == "xhigh"


def test_empty_env_value_is_passthrough(monkeypatch):
    """Empty TRADINGAGENTS_* values must not clobber the built-in default."""
    config = _config_with_env(
        monkeypatch,
        TRADINGAGENTS_EFFORT="",
        TRADINGAGENTS_MAX_DEBATE_ROUNDS="",
    )
    assert config["effort"] == "high"
    assert config["max_debate_rounds"] == 1


def test_empty_path_value_keeps_the_default_path(monkeypatch):
    """.env.example lists the path variables blank; uncommenting one made the
    path empty, and the graph failed creating its directories."""
    config = _config_with_env(
        monkeypatch,
        TRADINGAGENTS_RESULTS_DIR="",
        TRADINGAGENTS_CACHE_DIR="",
        TRADINGAGENTS_MEMORY_LOG_PATH="",
    )
    home = default_config_module._TRADINGAGENTS_HOME
    assert config["results_dir"] == os.path.join(home, "logs")
    assert config["data_cache_dir"] == os.path.join(home, "cache")
    assert config["memory_log_path"] == os.path.join(home, "memory", "trading_memory.md")


def test_invalid_int_raises(monkeypatch):
    """Garbage int values should surface a ValueError at import, not silently misconfigure."""
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "not-a-number")
    with pytest.raises(ValueError, match="TRADINGAGENTS_MAX_DEBATE_ROUNDS"):
        default_config_module.build_default_config()


@pytest.mark.parametrize("bad", ["treu", "flase", "maybe", "2", "enabled"])
def test_invalid_bool_raises(monkeypatch, bad):
    """A misspelled boolean must fail loudly (like ints) instead of silently False."""
    monkeypatch.setenv("TRADINGAGENTS_CHECKPOINT_ENABLED", bad)
    with pytest.raises(ValueError, match="TRADINGAGENTS_CHECKPOINT_ENABLED"):
        default_config_module.build_default_config()


def test_unknown_env_var_is_ignored(monkeypatch):
    """Env vars outside _ENV_OVERRIDES must not bleed into DEFAULT_CONFIG."""
    config = _config_with_env(
        monkeypatch,
        TRADINGAGENTS_NONEXISTENT_KEY="oops",
    )
    assert "nonexistent_key" not in config
