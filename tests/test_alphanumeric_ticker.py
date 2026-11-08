"""#181: 영숫자 KRX 종목코드(0126Z0 삼성에피스홀딩스, 0088M0 메쥬, 00680K 우선주)를 받는다.

신규 상장 종목은 숫자 6자리가 아닌 영숫자 6자 코드를 받는다. 검증이 숫자만 받던 곳
(요청 검증·보고서 번호·종목 검색·CLI)과, 숫자가 아니면 회사명으로 오인하는 DART 조회를
같은 규칙으로 맞췄는지 검증한다.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradingagents.dataflows import krx_symbol_search as kss
from tradingagents.dataflows.symbols import KRX_TICKER_PATTERN, validate_krx_ticker
from tradingagents.dataflows.vendors import dart

ALNUM = ["0126Z0", "0088M0", "00680K"]


# ---------------------------------------------------------------------------
# 공통 규칙 (symbols.py)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", ALNUM + ["005930"])
def test_validate_krx_ticker_accepts_numeric_and_alphanumeric(code: str) -> None:
    assert validate_krx_ticker(code) == code


@pytest.mark.parametrize("bad", ["0126z0", "0126Z", "0126Z00", "0126-Z", "삼성전자", "NVDA", "BTC-USD", ""])
def test_validate_krx_ticker_rejects_other_shapes(bad: str) -> None:
    """소문자·5자·7자·기호·한글은 여전히 거부한다 (대문자 영숫자 6자만)."""
    with pytest.raises(ValueError):
        validate_krx_ticker(bad)


def test_pattern_constant_is_what_openapi_exposes() -> None:
    """클라이언트가 /openapi.json 의 RunCreate.ticker 패턴을 읽고 판단할 수 있어야 한다."""
    pytest.importorskip("fastapi")
    from api.main import create_app

    schema = create_app().openapi()["components"]["schemas"]["RunCreate"]
    assert schema["properties"]["ticker"]["pattern"] == KRX_TICKER_PATTERN


# ---------------------------------------------------------------------------
# POST /api/runs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", ALNUM)
def test_post_run_accepts_alphanumeric_ticker(monkeypatch: pytest.MonkeyPatch, code: str) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from api.main import create_app
    from api.run_store import store

    launched: list[str] = []

    async def fake_launch(request, _store) -> str:
        launched.append(request.ticker)
        return "run-1"

    store.reset()
    # 그래프를 돌리지 않는다 — 요청 검증만 본다.
    monkeypatch.setattr("api.routes.runs.launch_run", fake_launch)

    client = TestClient(create_app())
    response = client.post("/api/runs", json={"ticker": code, "trade_date": "2024-01-05"})
    store.reset()
    assert response.status_code == 201, response.text
    assert launched == [code]


@pytest.mark.parametrize("bad", ["0126z0", "ABCDE", "0126Z00", "0126Z!"])
def test_post_run_rejects_malformed_ticker(bad: str) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from api.main import create_app

    client = TestClient(create_app())
    response = client.post("/api/runs", json={"ticker": bad, "trade_date": "2024-01-05"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 보고서 번호 (reports_store / /api/reports)
# ---------------------------------------------------------------------------


@pytest.fixture
def results_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setitem(DEFAULT_CONFIG, "results_dir", str(tmp_path))
    return tmp_path


def _seed_report(root: Path, report_id: str) -> None:
    base = root / "reports" / report_id
    base.mkdir(parents=True)
    (base / "complete_report.md").write_text("# 분석 보고서\n- 등급: Buy\n", encoding="utf-8")


def test_alphanumeric_report_is_listed_and_readable(results_root: Path) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from api.main import create_app

    _seed_report(results_root, "0126Z0_20261104_083000")
    _seed_report(results_root, "005930_20261103_083000")
    client = TestClient(create_app())

    ids = [r["report_id"] for r in client.get("/api/reports").json()]
    assert ids == ["0126Z0_20261104_083000", "005930_20261103_083000"]

    by_ticker = client.get("/api/reports?ticker=0126Z0").json()
    assert [r["report_id"] for r in by_ticker] == ["0126Z0_20261104_083000"]

    single = client.get("/api/reports/0126Z0_20261104_083000")
    assert single.status_code == 200
    assert single.json()["ticker"] == "0126Z0"
    assert client.get("/api/reports/0126Z0_20261104_083000/download?format=md").status_code == 200


def test_malformed_report_ids_are_still_rejected(results_root: Path) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from api.main import create_app

    client = TestClient(create_app())
    assert client.get("/api/reports/0126z0_20261104_083000").status_code == 400
    assert client.get("/api/reports/0126Z_20261104_083000").status_code == 400


# ---------------------------------------------------------------------------
# 종목 검색 (코드 정확 매칭)
# ---------------------------------------------------------------------------

_HITS = [
    kss.SymbolHit(ticker="0126Z0", name="삼성에피스홀딩스", market="KOSPI"),
    kss.SymbolHit(ticker="0088M0", name="메쥬", market="KOSDAQ"),
    kss.SymbolHit(ticker="005930", name="삼성전자", market="KOSPI"),
    kss.SymbolHit(ticker="000150", name="DOOSAN", market="KOSPI"),
]


@pytest.fixture
def listing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kss, "_load_all", lambda as_of=None: _HITS)


def test_search_exact_alphanumeric_code(listing) -> None:
    hits = kss.search("0126Z0")
    assert [h.name for h in hits] == ["삼성에피스홀딩스"]


def test_search_unknown_alphanumeric_code_returns_empty(listing) -> None:
    assert kss.search("0999Z9") == []


def test_search_six_letter_name_still_found_by_name(listing) -> None:
    """6자 대문자 영문 종목명(DOOSAN)은 코드 패턴에 걸려도 이름으로 찾아야 한다."""
    assert [h.ticker for h in kss.search("DOOSAN")] == ["000150"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class _Ask:
    def __init__(self, value: object) -> None:
        self.value = value

    def ask(self) -> object:
        return self.value


def test_cli_flag_accepts_alphanumeric_code() -> None:
    import cli.prompts as prompts

    assert prompts.parse_ticker("0126Z0") == "0126Z0"
    assert prompts.is_valid_ticker_input("0088M0") is True


def test_cli_interactive_alphanumeric_code_skips_search(monkeypatch: pytest.MonkeyPatch) -> None:
    import cli.prompts as prompts

    searched: list[str] = []
    answers = iter(["0126Z0"])  # 코드로 인식 못 해 재프롬프트하면 StopIteration 으로 바로 실패

    monkeypatch.setattr(kss, "search", lambda *a, **k: searched.append("x") or [])
    monkeypatch.setattr(prompts.questionary, "text", lambda *a, **k: _Ask(next(answers)))

    assert prompts.get_ticker() == "0126Z0"
    assert searched == []


def test_cli_interactive_six_letter_name_goes_to_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """숫자가 하나도 없는 6자 대문자(DOOSAN)는 코드가 아니라 종목명 검색으로 보낸다."""
    import cli.prompts as prompts

    searched: list[str] = []
    answers = iter(["DOOSAN", "005930"])  # 검색 결과 0 → 재프롬프트 → 코드 입력

    monkeypatch.setattr(kss, "search", lambda q, **k: searched.append(q) or [])
    monkeypatch.setattr(prompts.questionary, "text", lambda *a, **k: _Ask(next(answers)))

    assert prompts.get_ticker() == "005930"
    assert searched == ["DOOSAN"]


# ---------------------------------------------------------------------------
# DART — OpenDartReader 는 숫자가 아닌 문자열을 회사명으로 본다
# ---------------------------------------------------------------------------

_CORP_CODES = pd.DataFrame(
    {
        "corp_code": ["00126380", "01965324", "01780608"],
        "corp_name": ["삼성전자", "삼성에피스홀딩스", "메쥬"],
        "stock_code": ["005930", "0126Z0", "0088M0"],
    }
)


@pytest.fixture
def fake_reader(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    reader = MagicMock()
    reader.corp_codes = _CORP_CODES
    monkeypatch.setattr(dart, "_dart", lambda: reader)
    return reader


def test_dart_company_profile_uses_corp_code_for_alphanumeric_ticker(fake_reader: MagicMock) -> None:
    fake_reader.company.return_value = {"corp_name": "삼성에피스홀딩스", "corp_cls": "Y"}

    profile = dart.get_company_profile("0126Z0")

    fake_reader.company.assert_called_once_with("01965324")
    assert profile["longName"] == "삼성에피스홀딩스"


def test_dart_numeric_ticker_is_passed_through_unchanged(fake_reader: MagicMock) -> None:
    fake_reader.company.return_value = {"corp_name": "삼성전자", "corp_cls": "Y"}

    dart.get_company_profile("005930")

    fake_reader.company.assert_called_once_with("005930")


def test_dart_unknown_alphanumeric_ticker_is_passed_through(fake_reader: MagicMock) -> None:
    """코드표에 없으면 그대로 넘겨 라이브러리가 기존 방식으로 실패하게 둔다 (지어내지 않는다)."""
    fake_reader.company.side_effect = ValueError('could not find "00680K"')

    assert dart.get_company_profile("00680K") == {}
    fake_reader.company.assert_called_once_with("00680K")


def test_dart_other_calls_also_translate_alphanumeric_ticker(fake_reader: MagicMock) -> None:
    fake_reader.finstate_all.return_value = None
    fake_reader.list.return_value = pd.DataFrame()

    dart._fetch_finstate("0126Z0", 2025, "11011")
    dart.get_recent_disclosures("0126Z0", "2026-11-06")

    assert fake_reader.finstate_all.call_args.args[0] == "01965324"
    assert fake_reader.list.call_args.args[0] == "01965324"
