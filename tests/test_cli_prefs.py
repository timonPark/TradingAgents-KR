"""The CLI remembers what you chose last time and offers it back.

Prefill only: every prompt still appears, so a run never starts on a choice the
user did not see. Environment variables keep skipping their step outright and
win over anything remembered. Remembered values are validated against the
current choices each time, since models come and go between versions and a
stale one must not be offered.

Task 2 (#21): provider 와 backend_url 저장이 제거되었습니다 — provider 는
claude-code 로 고정이고 backend_url 은 로컬 CLI 호출이라 N/A. deep/quick
모델과 effort 만 저장됩니다.
"""

from __future__ import annotations

from unittest import mock

import pytest

import cli.selections as cli_selections
from cli.models import AnalystType
from cli.prefs import load_last_run, sanitize, save_last_run

SAVED = {
    "output_language": "Korean",
    "analysts": ["market", "fundamentals"],
    "research_depth": 3,
    "quick_think_llm": "haiku",
    "deep_think_llm": "sonnet",
    "effort": "high",
    "quick_effort": "medium",
}


@pytest.mark.unit
def test_round_trip():
    save_last_run(SAVED)
    assert load_last_run() == SAVED


@pytest.mark.unit
def test_missing_file_is_not_an_error():
    assert load_last_run() == {}


@pytest.mark.unit
def test_a_corrupt_file_degrades_to_no_memory(tmp_path):
    (tmp_path / "cli_prefs.json").write_text("{not json")
    assert load_last_run() == {}


@pytest.mark.unit
def test_a_half_written_file_cannot_be_observed(tmp_path):
    """두 run 이 동시에 끝나도 torn 파일이 남으면 안 됨."""
    save_last_run(SAVED)
    save_last_run({**SAVED, "research_depth": 5})
    assert load_last_run()["research_depth"] == 5
    assert list(tmp_path.glob("*.tmp*")) == []


# --- 현재 선택지와 비교해 유효성 검증 -----------------------------------------


@pytest.mark.unit
def test_a_custom_model_id_is_preserved():
    """Custom Claude 모델 ID 는 free-text 로 입력되므로 그대로 유지."""
    kept = sanitize({**SAVED, "quick_think_llm": "claude-sonnet-4-6"}, "stock")
    assert kept["quick_think_llm"] == "claude-sonnet-4-6"


@pytest.mark.unit
def test_an_unknown_effort_is_dropped():
    """effort 는 알려진 레벨만 유지. 알 수 없는 값은 drop."""
    kept = sanitize({**SAVED, "effort": "ultra"}, "stock")
    assert "effort" not in kept
    assert kept["quick_effort"] == "medium"  # 유효한 sibling 유지


@pytest.mark.unit
def test_analysts_are_narrowed_to_the_asset_type():
    kept = sanitize(SAVED, "crypto")
    assert AnalystType.FUNDAMENTALS.value not in kept["analysts"]
    assert AnalystType.MARKET.value in kept["analysts"]


@pytest.mark.unit
def test_junk_values_are_dropped_rather_than_offered():
    kept = sanitize({"research_depth": 99, "analysts": ["astrology"], "output_language": 5}, "stock")
    assert kept == {}


# --- wiring ------------------------------------------------------------------


def _answer_every_prompt(monkeypatch):
    """실제 selection 흐름을 돌려 각 프롬프트에 고정 값 응답."""
    monkeypatch.setattr(cli_selections.updates, "enabled", lambda: False)
    monkeypatch.setattr(cli_selections, "get_ticker", lambda: "005930")
    monkeypatch.setattr(cli_selections, "get_analysis_date", lambda: "2026-09-01")
    monkeypatch.setattr(cli_selections, "ask_output_language", lambda default=None: "Korean")
    monkeypatch.setattr(cli_selections, "select_analysts", lambda asset_type, default=None: [AnalystType.MARKET])
    monkeypatch.setattr(cli_selections, "select_research_depth", lambda default=None: 3)
    monkeypatch.setattr(cli_selections, "select_shallow_thinking_agent", lambda default=None: "haiku")
    monkeypatch.setattr(cli_selections, "select_deep_thinking_agent", lambda default=None: "sonnet")
    monkeypatch.setattr(cli_selections, "ask_effort", lambda mode, default=None: "high" if mode == "deep" else "medium")


@pytest.mark.unit
def test_selections_are_remembered_after_a_run(monkeypatch):
    """실제 흐름을 돌림: stubbed selections dict 는 키 미스매치를 가립니다."""
    _answer_every_prompt(monkeypatch)

    cli_selections.get_user_selections()

    remembered = load_last_run()
    assert remembered["analysts"] == ["market"]
    assert remembered["quick_think_llm"] == "haiku"
    assert remembered["deep_think_llm"] == "sonnet"
    assert remembered["effort"] == "high"
    assert remembered["quick_effort"] == "medium"
    assert "ticker" not in remembered  # 매번 바뀜; 저장 안 함
    assert "analysis_date" not in remembered  # 오래된 날짜 제시 방지
    assert "llm_provider" not in remembered  # claude-code 고정, 저장 불필요


@pytest.mark.unit
def test_a_custom_language_is_remembered_without_breaking_the_next_run():
    """free-text 응답은 menu 선택지가 아니라 questionary 가 default 를 찾지 못하면
    기동 시 crash. 그러므로 preselect 하지 않고 그대로 저장만 함."""
    from cli.prompts import ask_output_language

    save_last_run({"output_language": "Turkish"})
    with mock.patch("cli.prompts.questionary.select") as select:
        select.return_value.ask.return_value = "Korean"
        ask_output_language(load_last_run()["output_language"])
    assert select.call_args.kwargs["default"] is None
