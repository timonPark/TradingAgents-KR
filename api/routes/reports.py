"""Task 14f (#111): 리포트 열람 엔드포인트."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from api.reports_store import (
    _REPORT_ID_PATTERN,
    _results_root,
    get_report,
    list_reports,
    read_report_meta,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.report_html import prepare_html_for_pdf

router = APIRouter()


class ReportSummaryOut(BaseModel):
    report_id: str
    ticker: str
    name: str | None = None  # 14a 공통 검색으로 lookup; 실패 시 null
    stamp: str  # 분석을 돌려 저장한 시각
    decision: str | None = None
    # #174: 분석 기준일 (헤더에 없으면 null), 에이전트 이름 → 5단계 등급(내부 값, 예 "Buy").
    # 읽지 못한 에이전트는 빠진다. 이름은 market, news, fundamentals, bull, bear,
    # research_manager, aggressive, conservative, neutral, portfolio_manager.
    trade_date: str | None = None
    agent_ratings: dict[str, str] = Field(default_factory=dict)


class ReportFileOut(BaseModel):
    path: str
    content: str


class ReportTreeOut(BaseModel):
    report_id: str
    ticker: str
    name: str | None = None
    stamp: str
    decision: str | None = None
    trade_date: str | None = None
    agent_ratings: dict[str, str] = Field(default_factory=dict)
    files: list[ReportFileOut] = Field(default_factory=list)


def _lookup_name(ticker: str) -> str | None:
    """14a 공통 검색으로 종목명 lookup. 실패해도 리포트 열람은 이어진다."""
    try:
        from tradingagents.dataflows import krx_symbol_search as kss

        hits = kss.search(ticker, limit=1)
        if hits:
            return hits[0].name
    except Exception as exc:  # noqa: BLE001 — pykrx 네트워크/캐시 실패 격리
        import logging

        logging.getLogger(__name__).warning("ticker name lookup failed for %s: %s", ticker, exc)
    return None


@router.get("", response_model=list[ReportSummaryOut])
def list_all(
    limit: int = 50, ticker: str | None = None, trade_date: str | None = None
) -> list[ReportSummaryOut]:
    # #174: ticker/trade_date 로 먼저 거른 뒤 limit. 조건을 안 주면 지금과 같다.
    summaries = list_reports(
        DEFAULT_CONFIG["results_dir"], limit=limit, ticker=ticker, trade_date=trade_date
    )
    return [
        ReportSummaryOut(
            report_id=s.report_id,
            ticker=s.ticker,
            name=_lookup_name(s.ticker),
            stamp=s.stamp,
            decision=s.decision,
            trade_date=s.trade_date,
            agent_ratings=s.agent_ratings,
        )
        for s in summaries
    ]


@router.get("/{report_id}", response_model=ReportTreeOut)
def get_single(report_id: str) -> ReportTreeOut:
    try:
        files = get_report(DEFAULT_CONFIG["results_dir"], report_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    ticker = report_id.split("_")[0]
    stamp_raw = report_id[7:]
    from api.reports_store import _parse_stamp

    # decision 은 리스트에서 다시 계산 (단일 조회 시 효율 낮지만 복제 피함)
    decision: str | None = None
    for f in files:
        if f.path == "complete_report.md":
            from api.reports_store import rating_from_header_line

            for line in f.content.splitlines()[:20]:
                decision = rating_from_header_line(line)
                if decision:
                    break
            break

    trade_date, agent_ratings = read_report_meta(DEFAULT_CONFIG["results_dir"], report_id)
    return ReportTreeOut(
        report_id=report_id,
        ticker=ticker,
        name=_lookup_name(ticker),
        stamp=_parse_stamp(stamp_raw),
        decision=decision,
        trade_date=trade_date,
        agent_ratings=agent_ratings,
        files=[ReportFileOut(path=f.path, content=f.content) for f in files],
    )


# ---------------------------------------------------------------------------
# #128: 다운로드 엔드포인트 (md / html / pdf)
# ---------------------------------------------------------------------------

DownloadFormat = Literal["md", "html", "pdf"]


def _safe_report_dir(report_id: str) -> Path:
    if not _REPORT_ID_PATTERN.match(report_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"invalid report_id: {report_id!r}"
        )
    root = _results_root(DEFAULT_CONFIG["results_dir"])
    report_dir = (root / report_id).resolve()
    try:
        report_dir.relative_to(root)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"report_id escapes results root: {report_id!r}",
        ) from exc
    if not report_dir.is_dir():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"report not found: {report_id}"
        )
    return report_dir


def _attachment(filename: str) -> str:
    # ASCII 범위 filename 만 쓰므로 RFC 5987 encoding 생략해도 안전.
    return f'attachment; filename="{filename}"'


@router.get("/{report_id}/download")
def download_report(report_id: str, format: DownloadFormat = "md") -> Response:
    """통합 리포트를 파일로 다운로드.

    - ``md``:   ``complete_report.md`` 원본
    - ``html``: ``complete_report.html`` 원본 (브라우저에서 바로 열람)
    - ``pdf``:  ``complete_report.html`` 을 WeasyPrint 로 PDF 변환
    """
    report_dir = _safe_report_dir(report_id)
    base = f"trading_report_{report_id}"

    if format == "md":
        src = report_dir / "complete_report.md"
        if not src.is_file():
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "complete_report.md not found"
            )
        return Response(
            content=src.read_bytes(),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": _attachment(f"{base}.md")},
        )

    if format == "html":
        src = report_dir / "complete_report.html"
        if not src.is_file():
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "complete_report.html not found"
            )
        return Response(
            content=src.read_bytes(),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": _attachment(f"{base}.html")},
        )

    # pdf — WeasyPrint 로 complete_report.html 변환.
    src = report_dir / "complete_report.html"
    if not src.is_file():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "complete_report.html not found (PDF source)"
        )
    pdf_bytes = _render_pdf(src)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _attachment(f"{base}.pdf")},
    )


def _render_pdf(html_path: Path) -> bytes:
    """WeasyPrint 로 complete_report.html → PDF 바이너리.

    weasyprint 는 ``[web]`` extra. 미설치 시 503 Service Unavailable 로 명확한
    안내. base_url 을 리포트 디렉터리로 지정해 상대경로 이미지도 처리.
    """
    try:
        from weasyprint import HTML  # noqa: PLC0415 — optional dep, lazy import
    except ImportError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "PDF 변환에 weasyprint 가 필요합니다. "
            'pip install -e ".[web]" 로 설치하세요.',
        ) from exc
    # WeasyPrint 는 페이지 CSS 를 인라인 SVG 에 적용하지 않아 차트가 검정으로 나온다 (#161).
    # 각 <svg> 안에 literal 색 규칙 등을 넣어서 변환한다 (브라우저용 HTML 파일은 그대로).
    html = prepare_html_for_pdf(html_path.read_text(encoding="utf-8"))
    return HTML(string=html, base_url=str(html_path.parent)).write_pdf()
