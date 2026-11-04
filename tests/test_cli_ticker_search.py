"""Task 14g (#112): CLI 종목명 검색 플로우 테스트.

`cli.prompts.get_ticker` 가 6자리 숫자 입력은 기존대로 통과하고, 그 외
문자열은 `krx_symbol_search.search` 를 호출해 결과 수에 따라 자동/번호 선택
흐름을 밟는지 검증한다. questionary 는 모킹.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest


@dataclass
class _Ask:
    """questionary.text/select/confirm 반환을 흉내낸 래퍼."""

    value: object

    def ask(self) -> object:
        return self.value


def _fake_hit(ticker: str, name: str, market: str = "KOSPI"):
    from tradingagents.dataflows.krx_symbol_search import SymbolHit

    return SymbolHit(ticker=ticker, name=name, market=market)


@pytest.fixture
def prompts(monkeypatch: pytest.MonkeyPatch):
    import cli.prompts as module

    # questionary.Style 과 Choice 는 그대로 사용 (내부 상태 없음).
    return module


def _queue(values: list[object]) -> Iterator[object]:
    yield from values


def test_six_digit_input_skips_search(monkeypatch, prompts) -> None:
    """6자리 숫자는 search 를 부르지 않고 바로 반환."""
    search_called = []
    monkeypatch.setattr("tradingagents.dataflows.krx_symbol_search.search", lambda *a, **k: search_called.append(1) or [])
    monkeypatch.setattr(prompts.questionary, "text", lambda *a, **k: _Ask("005930"))

    assert prompts.get_ticker() == "005930"
    assert search_called == []


def test_empty_input_defaults_to_samsung(monkeypatch, prompts) -> None:
    monkeypatch.setattr(prompts.questionary, "text", lambda *a, **k: _Ask(""))
    assert prompts.get_ticker() == "005930"


def test_single_match_auto_confirms(monkeypatch, prompts) -> None:
    text_values = iter(["카카오"])
    monkeypatch.setattr(
        prompts.questionary, "text",
        lambda *a, **k: _Ask(next(text_values)),
    )
    monkeypatch.setattr(
        "tradingagents.dataflows.krx_symbol_search.search",
        lambda *a, **k: [_fake_hit("035720", "카카오")],
    )
    monkeypatch.setattr(prompts.questionary, "confirm", lambda *a, **k: _Ask(True))

    assert prompts.get_ticker() == "035720"


def test_single_match_reject_reprompts(monkeypatch, prompts) -> None:
    # 1 회차에선 거부 → 2 회차에선 6자리 직접 입력으로 종결.
    text_values = iter(["카카오", "005930"])
    search_calls = [0]

    def fake_search(*a, **k):
        search_calls[0] += 1
        return [_fake_hit("035720", "카카오")]

    monkeypatch.setattr(prompts.questionary, "text", lambda *a, **k: _Ask(next(text_values)))
    monkeypatch.setattr("tradingagents.dataflows.krx_symbol_search.search", fake_search)
    monkeypatch.setattr(prompts.questionary, "confirm", lambda *a, **k: _Ask(False))

    assert prompts.get_ticker() == "005930"
    assert search_calls[0] == 1  # 두 번째 회차는 6자리 숫자라 search 미호출


def test_multiple_matches_select(monkeypatch, prompts) -> None:
    text_values = iter(["삼성"])
    monkeypatch.setattr(prompts.questionary, "text", lambda *a, **k: _Ask(next(text_values)))
    monkeypatch.setattr(
        "tradingagents.dataflows.krx_symbol_search.search",
        lambda *a, **k: [
            _fake_hit("005930", "삼성전자"),
            _fake_hit("006400", "삼성SDI"),
            _fake_hit("028260", "삼성물산"),
        ],
    )
    monkeypatch.setattr(prompts.questionary, "select", lambda *a, **k: _Ask("006400"))

    assert prompts.get_ticker() == "006400"


def test_no_match_reprompts(monkeypatch, prompts) -> None:
    text_values = iter(["존재하지않는종목", "005930"])
    monkeypatch.setattr(prompts.questionary, "text", lambda *a, **k: _Ask(next(text_values)))
    monkeypatch.setattr("tradingagents.dataflows.krx_symbol_search.search", lambda *a, **k: [])

    assert prompts.get_ticker() == "005930"


def test_search_raising_shows_error_and_reprompts(monkeypatch, prompts, capsys) -> None:
    text_values = iter(["삼성", "005930"])
    monkeypatch.setattr(prompts.questionary, "text", lambda *a, **k: _Ask(next(text_values)))

    def exploding_search(*a, **k):
        raise RuntimeError("pykrx 네트워크 실패")

    monkeypatch.setattr("tradingagents.dataflows.krx_symbol_search.search", exploding_search)

    assert prompts.get_ticker() == "005930"


def test_cancelled_select_reprompts(monkeypatch, prompts) -> None:
    text_values = iter(["삼성", "005930"])
    monkeypatch.setattr(prompts.questionary, "text", lambda *a, **k: _Ask(next(text_values)))
    monkeypatch.setattr(
        "tradingagents.dataflows.krx_symbol_search.search",
        lambda *a, **k: [
            _fake_hit("005930", "삼성전자"),
            _fake_hit("006400", "삼성SDI"),
        ],
    )
    monkeypatch.setattr(prompts.questionary, "select", lambda *a, **k: _Ask(None))

    assert prompts.get_ticker() == "005930"


def test_is_valid_search_or_ticker_accepts_names_and_six_digit(prompts) -> None:
    assert prompts._is_valid_search_or_ticker("삼성전자") is True
    assert prompts._is_valid_search_or_ticker("kodex") is True
    assert prompts._is_valid_search_or_ticker("005930") is True
    assert prompts._is_valid_search_or_ticker("") is True


def test_is_valid_search_or_ticker_rejects_non_six_digit_numeric(prompts) -> None:
    # 전부 숫자이면서 6자리가 아닌 입력은 오입력으로 간주 (검색어가 아님).
    assert prompts._is_valid_search_or_ticker("12345") is False
    assert prompts._is_valid_search_or_ticker("1234567") is False


def test_parse_ticker_still_strict(prompts) -> None:
    """--ticker 플래그는 종전처럼 6자리 숫자만 수용 (zero-regression)."""
    assert prompts.parse_ticker("005930") == "005930"
    with pytest.raises(ValueError):
        prompts.parse_ticker("삼성전자")
    with pytest.raises(ValueError):
        prompts.parse_ticker("NVDA")
    with pytest.raises(ValueError):
        prompts.parse_ticker("")
