"""Task 14f (#111): `/api/reports` 라우트 테스트.

임시 디렉터리에 가짜 리포트 트리를 만들고 라우트가 올바로 파싱/직렬화하는지,
경로 traversal 공격을 거부하는지 검증한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from api.main import create_app  # noqa: E402


def _seed(results_dir: Path, report_id: str, decision: str | None, extras: dict[str, str] | None = None) -> None:
    """``results_dir/reports/<report_id>/`` 아래에 모의 리포트 생성."""
    base = results_dir / "reports" / report_id
    base.mkdir(parents=True, exist_ok=True)
    header_lines = [f"# 분석 보고서: {report_id.split('_')[0]}"]
    if decision is not None:
        header_lines.append(f"- 등급: {decision}")
    (base / "complete_report.md").write_text("\n".join(header_lines) + "\n", encoding="utf-8")

    (base / "analysts").mkdir(exist_ok=True)
    (base / "analysts" / "market.md").write_text("## 시장\n내용", encoding="utf-8")

    for rel, text in (extras or {}).items():
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


@pytest.fixture
def results_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """DEFAULT_CONFIG['results_dir'] 를 tmp 로 교체."""
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setitem(DEFAULT_CONFIG, "results_dir", str(tmp_path))
    return tmp_path


def test_list_returns_recent_reports_newest_first(results_root: Path) -> None:
    _seed(results_root, "005930_20261101_120000", "Buy")
    _seed(results_root, "005930_20261104_083000", "Hold")
    _seed(results_root, "035720_20261103_150000", "Sell")

    client = TestClient(create_app())
    response = client.get("/api/reports")
    assert response.status_code == 200
    items = response.json()
    assert [i["report_id"] for i in items] == [
        "005930_20261104_083000",
        "035720_20261103_150000",
        "005930_20261101_120000",
    ]
    decisions = {i["report_id"]: i["decision"] for i in items}
    assert decisions["005930_20261104_083000"] == "Hold"


def test_list_skips_non_matching_dirs(results_root: Path) -> None:
    (results_root / "reports").mkdir(parents=True, exist_ok=True)
    (results_root / "reports" / "not_a_report").mkdir()
    (results_root / "reports" / "005930_bad_stamp").mkdir()
    _seed(results_root, "005930_20261104_083000", "Hold")

    client = TestClient(create_app())
    items = client.get("/api/reports").json()
    assert len(items) == 1
    assert items[0]["report_id"] == "005930_20261104_083000"


def test_list_empty_when_no_reports(results_root: Path) -> None:
    client = TestClient(create_app())
    assert client.get("/api/reports").json() == []


def test_get_single_returns_all_md_files(results_root: Path) -> None:
    _seed(
        results_root,
        "005930_20261104_083000",
        "Buy",
        extras={"research/bull.md": "불", "trading/trader.md": "트레이더"},
    )

    client = TestClient(create_app())
    response = client.get("/api/reports/005930_20261104_083000")
    assert response.status_code == 200
    body = response.json()
    assert body["report_id"] == "005930_20261104_083000"
    assert body["ticker"] == "005930"
    assert body["decision"] == "Buy"
    paths = sorted(f["path"] for f in body["files"])
    assert paths == [
        "analysts/market.md",
        "complete_report.md",
        "research/bull.md",
        "trading/trader.md",
    ]


def test_get_single_404_for_missing(results_root: Path) -> None:
    client = TestClient(create_app())
    assert client.get("/api/reports/005930_20261104_083000").status_code == 404


def test_get_single_400_for_invalid_pattern(results_root: Path) -> None:
    client = TestClient(create_app())
    assert client.get("/api/reports/nope").status_code == 400
    assert client.get("/api/reports/005930_20261104").status_code == 400
    assert client.get("/api/reports/ABCDEF_20261104_083000").status_code == 400


def test_get_single_rejects_path_traversal(results_root: Path) -> None:
    """패턴 regex 만으로는 안 통해도, 혹시 모를 ../ 를 추가로 막는지."""
    client = TestClient(create_app())
    # FastAPI 가 URL 파싱 단계에서 거부 — 400 또는 404 나올 수 있음.
    # 어느 쪽이든 200/파일 내용은 안 됨.
    resp = client.get("/api/reports/..%2Fsomething_20261104_083000")
    assert resp.status_code in {400, 404}


def test_get_single_skips_non_whitelisted_folder(results_root: Path) -> None:
    """``secrets/`` 같은 폴더는 트리에 보이지 않아야 한다."""
    _seed(results_root, "005930_20261104_083000", "Buy", extras={"secrets/token.md": "비밀"})
    client = TestClient(create_app())
    files = client.get("/api/reports/005930_20261104_083000").json()["files"]
    paths = {f["path"] for f in files}
    assert "secrets/token.md" not in paths


# ---------------------------------------------------------------------------
# #128: 다운로드 엔드포인트
# ---------------------------------------------------------------------------


def test_download_md_returns_complete_report_as_attachment(results_root: Path) -> None:
    _seed(results_root, "005930_20261104_083000", "Buy")
    client = TestClient(create_app())
    resp = client.get("/api/reports/005930_20261104_083000/download?format=md")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "attachment" in resp.headers["content-disposition"]
    assert "trading_report_005930_20261104_083000.md" in resp.headers["content-disposition"]
    assert "# 분석 보고서" in resp.content.decode("utf-8")


def test_download_html_returns_complete_report_html(results_root: Path) -> None:
    _seed(
        results_root,
        "005930_20261104_083000",
        "Buy",
        extras={"complete_report.html": "<html><body>HI</body></html>"},
    )
    client = TestClient(create_app())
    resp = client.get("/api/reports/005930_20261104_083000/download?format=html")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "attachment" in resp.headers["content-disposition"]
    assert "HI" in resp.content.decode("utf-8")


def test_download_zip_packs_full_report_tree(results_root: Path) -> None:
    import io
    import zipfile

    _seed(
        results_root,
        "005930_20261104_083000",
        "Buy",
        extras={
            "complete_report.html": "<html>...</html>",
            "research/bull.md": "불",
            "trading/trader.md": "트레이더",
        },
    )
    client = TestClient(create_app())
    resp = client.get("/api/reports/005930_20261104_083000/download?format=zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "trading_report_005930_20261104_083000.zip" in resp.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = set(zf.namelist())
    assert "complete_report.md" in names
    assert "complete_report.html" in names
    assert "analysts/market.md" in names
    assert "research/bull.md" in names
    assert "trading/trader.md" in names


def test_download_zip_skips_non_whitelisted_folder(results_root: Path) -> None:
    import io
    import zipfile

    _seed(
        results_root,
        "005930_20261104_083000",
        "Buy",
        extras={"secrets/token.md": "비밀"},
    )
    client = TestClient(create_app())
    resp = client.get("/api/reports/005930_20261104_083000/download?format=zip")
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = set(zf.namelist())
    assert "secrets/token.md" not in names


def test_download_rejects_invalid_report_id(results_root: Path) -> None:
    client = TestClient(create_app())
    assert client.get("/api/reports/not-a-report/download?format=md").status_code == 400
    assert client.get("/api/reports/ABCDEF_20261104_083000/download?format=md").status_code == 400


def test_download_404_when_report_missing(results_root: Path) -> None:
    client = TestClient(create_app())
    resp = client.get("/api/reports/005930_20261104_083000/download?format=md")
    assert resp.status_code == 404


def test_download_rejects_unknown_format(results_root: Path) -> None:
    _seed(results_root, "005930_20261104_083000", "Buy")
    client = TestClient(create_app())
    assert client.get(
        "/api/reports/005930_20261104_083000/download?format=pdf"
    ).status_code == 422


def test_download_md_404_when_complete_missing(results_root: Path) -> None:
    # 섹션 파일만 있고 complete_report.md 가 없는 상황
    (results_root / "reports" / "005930_20261104_083000" / "analysts").mkdir(parents=True)
    (results_root / "reports" / "005930_20261104_083000" / "analysts" / "market.md").write_text("x", encoding="utf-8")
    client = TestClient(create_app())
    assert client.get(
        "/api/reports/005930_20261104_083000/download?format=md"
    ).status_code == 404
