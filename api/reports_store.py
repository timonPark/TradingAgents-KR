"""Task 14f (#111): 디스크 리포트 트리 조회.

``{results_dir}/reports/{ticker}_{YYYYMMDD_HHMMSS}/`` 아래 저장된 완료 run 의
리포트를 스캔/읽어온다. 프로세스 수명과 무관한 **디스크** 가 소스 오브 트루스.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from tradingagents.agent_ratings import AGENT_REPORT_FILES, parse_agent_rating
from tradingagents.agents.rating import canonical_rating

logger = logging.getLogger(__name__)

# `ticker_YYYYMMDD_HHMMSS` 디렉터리명 (영숫자 6자 한국 종목코드 + stamp).
# 종목코드 부분은 symbols.KRX_TICKER_PATTERN 과 같은 문자 집합 (#181).
_REPORT_ID_PATTERN = re.compile(r"^([0-9A-Z]{6})_(\d{8})_(\d{6})$")

# 리포트 파일명은 섹션(폴더) 또는 complete_report 중 하나만. 임의 파일 접근 차단.
_ALLOWED_FOLDERS = frozenset({"analysts", "research", "trading", "risk", "portfolio"})
_SECTION_FILE_PATTERN = re.compile(r"^[a-z_]+\.md$")

# 등급 파싱용: "- 등급: 비중 축소" / "- 등급: Underweight" 형태의 라인에서 등급 추출.
# 헤더는 한국어 표기(#145)로 쓰지만 이전에 저장된 보고서는 영어 값이라 둘 다 읽는다.
_RATING_PATTERN = re.compile(r"^-\s*등급\s*:\s*(\S.*)$")


# 헤더의 "- 분석일: 2026-11-05" 라인. 분석을 돌린 시각(report_id 의 stamp)과 다르다 (#174).
_TRADE_DATE_PATTERN = re.compile(r"^-\s*분석일\s*:\s*(\d{4}-\d{2}-\d{2})\s*$")


def rating_from_header_line(line: str) -> str | None:
    """헤더 라인에서 내부 등급 값(``Underweight`` 등)을 읽는다. 없으면 None."""
    match = _RATING_PATTERN.match(line.strip())
    return canonical_rating(match.group(1)) if match else None


@dataclass(frozen=True)
class ReportSummary:
    """사이드바 이력 항목."""

    report_id: str
    ticker: str
    stamp: str  # ISO datetime (분석을 돌려 저장한 시각)
    decision: str | None
    trade_date: str | None = None  # 분석 기준일. 헤더에 없으면 None (#174)
    agent_ratings: dict[str, str] = field(default_factory=dict)  # 에이전트 → 내부 등급 값 (#174)


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


def _read_header(complete_report_path: Path) -> tuple[str | None, str | None]:
    """``complete_report.md`` 헤더에서 (최종 등급, 분석 기준일). 못 읽은 쪽은 None."""
    try:
        text = complete_report_path.read_text(encoding="utf-8")
    except OSError:
        return None, None
    decision: str | None = None
    trade_date: str | None = None
    for line in text.splitlines()[:20]:
        decision = decision or rating_from_header_line(line)
        if trade_date is None and (m := _TRADE_DATE_PATTERN.match(line.strip())):
            trade_date = m.group(1)
    return decision, trade_date


def _read_agent_ratings(report_dir: Path) -> dict[str, str]:
    """에이전트별 섹션 파일에서 등급을 읽는다 (#174). 읽지 못한 에이전트는 빠진다.

    리포트 트리가 소스 오브 트루스라서 서버를 다시 켜도 같고, 이 기능 이전에 저장된
    리포트도 읽힌다. 파일이 없거나 등급이 없거나 엇갈리면 그 에이전트만 비운다.
    """
    ratings: dict[str, str] = {}
    for agent, relative in AGENT_REPORT_FILES.items():
        try:
            text = (report_dir / relative).read_text(encoding="utf-8")
        except OSError:
            continue
        rating = parse_agent_rating(text, agent)
        if rating is not None:
            ratings[agent] = rating
    return ratings


def read_report_meta(results_dir: str | Path, report_id: str) -> tuple[str | None, dict[str, str]]:
    """한 리포트의 (분석 기준일, 에이전트별 등급). ``report_id`` 는 이미 검증된 값이어야 한다."""
    report_dir = _results_root(results_dir) / report_id
    return _read_header(report_dir / "complete_report.md")[1], _read_agent_ratings(report_dir)


def list_reports(
    results_dir: str | Path,
    limit: int = 50,
    *,
    ticker: str | None = None,
    trade_date: str | None = None,
) -> list[ReportSummary]:
    """``results_dir/reports/`` 아래 리포트 디렉터리를 최근 순으로 반환.

    ``ticker``/``trade_date`` 를 주면 **먼저 거른 뒤** ``limit`` 을 적용한다 (#174).
    에이전트별 등급은 남은 ``limit`` 개만 읽는다.
    """
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
        report_ticker = match.group(1)
        if ticker is not None and report_ticker != ticker:
            continue
        stamp_raw = f"{match.group(2)}_{match.group(3)}"
        decision, report_date = _read_header(child / "complete_report.md")
        if trade_date is not None and report_date != trade_date:
            continue
        summaries.append(
            ReportSummary(
                report_id=child.name,
                ticker=report_ticker,
                stamp=_parse_stamp(stamp_raw),
                decision=decision,
                trade_date=report_date,
            )
        )

    summaries.sort(key=lambda s: s.stamp, reverse=True)
    return [
        replace(s, agent_ratings=_read_agent_ratings(root / s.report_id))
        for s in summaries[:limit]
    ]


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
