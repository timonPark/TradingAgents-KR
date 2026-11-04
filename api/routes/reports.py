"""Task 14f (#111): 리포트 열람 엔드포인트."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from api.reports_store import get_report, list_reports
from tradingagents.default_config import DEFAULT_CONFIG

router = APIRouter()


class ReportSummaryOut(BaseModel):
    report_id: str
    ticker: str
    name: str | None = None  # 14a 공통 검색으로 lookup; 실패 시 null
    stamp: str
    decision: str | None = None


class ReportFileOut(BaseModel):
    path: str
    content: str


class ReportTreeOut(BaseModel):
    report_id: str
    ticker: str
    name: str | None = None
    stamp: str
    decision: str | None = None
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
def list_all(limit: int = 50) -> list[ReportSummaryOut]:
    summaries = list_reports(DEFAULT_CONFIG["results_dir"], limit=limit)
    return [
        ReportSummaryOut(
            report_id=s.report_id,
            ticker=s.ticker,
            name=_lookup_name(s.ticker),
            stamp=s.stamp,
            decision=s.decision,
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
            from api.reports_store import _RATING_PATTERN

            for line in f.content.splitlines()[:20]:
                match = _RATING_PATTERN.match(line.strip())
                if match:
                    decision = match.group(1)
                    break
            break

    return ReportTreeOut(
        report_id=report_id,
        ticker=ticker,
        name=_lookup_name(ticker),
        stamp=_parse_stamp(stamp_raw),
        decision=decision,
        files=[ReportFileOut(path=f.path, content=f.content) for f in files],
    )
