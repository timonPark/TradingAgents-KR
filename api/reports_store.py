"""Task 14f (#111): 디스크 리포트 트리 조회.

``{results_dir}/reports/{ticker}_{YYYYMMDD_HHMMSS}/`` 아래 저장된 완료 run 의
리포트를 스캔/읽어온다. 프로세스 수명과 무관한 **디스크** 가 소스 오브 트루스.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# `ticker_YYYYMMDD_HHMMSS` 디렉터리명 (6자리 한국 종목코드 + stamp).
_REPORT_ID_PATTERN = re.compile(r"^(\d{6})_(\d{8})_(\d{6})$")

# 리포트 파일명은 섹션(폴더) 또는 complete_report 중 하나만. 임의 파일 접근 차단.
_ALLOWED_FOLDERS = frozenset({"analysts", "research", "trading", "risk", "portfolio"})
_SECTION_FILE_PATTERN = re.compile(r"^[a-z_]+\.md$")

# 등급 파싱용: "- 등급: BUY" 형태의 라인에서 등급 추출.
_RATING_PATTERN = re.compile(r"^-\s*등급\s*:\s*([A-Za-z]+)")


@dataclass(frozen=True)
class ReportSummary:
    """사이드바 이력 항목."""

    report_id: str
    ticker: str
    stamp: str  # ISO datetime
    decision: str | None


@dataclass(frozen=True)
class ReportFile:
    """리포트 트리 내 단일 파일."""

    path: str  # "complete_report.md" or "analysts/market.md"
    content: str


def _results_root(results_dir: str | Path) -> Path:
    return Path(results_dir).expanduser().resolve() / "reports"


def _parse_stamp(raw: str) -> str:
    """``YYYYMMDD_HHMMSS`` → ISO 8601 (초 단위)."""
    try:
        dt = datetime.strptime(raw, "%Y%m%d_%H%M%S")
    except ValueError:
        return raw
    return dt.isoformat()


def _extract_decision(complete_report_path: Path) -> str | None:
    try:
        text = complete_report_path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines()[:20]:
        match = _RATING_PATTERN.match(line.strip())
        if match:
            return match.group(1)
    return None


def list_reports(results_dir: str | Path, limit: int = 50) -> list[ReportSummary]:
    """``results_dir/reports/`` 아래 리포트 디렉터리를 최근 순으로 반환."""
    root = _results_root(results_dir)
    if not root.exists():
        return []

    summaries: list[ReportSummary] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        match = _REPORT_ID_PATTERN.match(child.name)
        if not match:
            continue
        ticker = match.group(1)
        stamp_raw = f"{match.group(2)}_{match.group(3)}"
        decision = _extract_decision(child / "complete_report.md")
        summaries.append(
            ReportSummary(
                report_id=child.name,
                ticker=ticker,
                stamp=_parse_stamp(stamp_raw),
                decision=decision,
            )
        )

    summaries.sort(key=lambda s: s.stamp, reverse=True)
    return summaries[:limit]


def get_report(results_dir: str | Path, report_id: str) -> list[ReportFile]:
    """단일 리포트 트리의 마크다운 파일 전체를 돌려준다.

    Raises:
        ValueError: ``report_id`` 가 패턴에 맞지 않음.
        FileNotFoundError: 디렉터리가 없음.
    """
    if not _REPORT_ID_PATTERN.match(report_id):
        raise ValueError(f"invalid report_id: {report_id!r}")

    root = _results_root(results_dir)
    report_dir = (root / report_id).resolve()
    try:
        report_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"report_id escapes results root: {report_id!r}") from exc

    if not report_dir.is_dir():
        raise FileNotFoundError(f"report not found: {report_id}")

    files: list[ReportFile] = []

    complete = report_dir / "complete_report.md"
    if complete.is_file():
        files.append(ReportFile(path="complete_report.md", content=complete.read_text(encoding="utf-8")))

    for folder in sorted(_ALLOWED_FOLDERS):
        folder_dir = report_dir / folder
        if not folder_dir.is_dir():
            continue
        for md in sorted(folder_dir.iterdir()):
            if not md.is_file():
                continue
            if not _SECTION_FILE_PATTERN.match(md.name):
                continue
            files.append(
                ReportFile(
                    path=f"{folder}/{md.name}",
                    content=md.read_text(encoding="utf-8"),
                )
            )

    return files
