"""네이버 증권 투자자별 매매동향 — KRX 로그인 수급의 폴백 (#139).

``GET https://m.stock.naver.com/api/stock/{종목코드}/trend`` (JSON, 비공식 경로,
키 불필요). 최근 10거래일의 외국인·기관·개인 순매수 **수량(주)** 과 외국인 보유율을
준다.

KRX 투자자별 거래실적(원 단위, 기관 세부 구분)과 다른 점:
- 금액(원)이 아니라 **수량(주)**
- 기관 세부(연기금·투신·사모 등)와 기타법인 구분이 없다
- 최근 10거래일만 제공 — 기준일이 그보다 과거면 조회할 수 없다

실패는 ``VendorUnavailableError`` 로 올린다 ("수급 없음" 으로 위장하지 않는다).
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from tradingagents.dataflows.errors import VendorUnavailableError

logger = logging.getLogger(__name__)

_TREND_URL = "https://m.stock.naver.com/api/stock/{ticker}/trend"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}
_REQUEST_TIMEOUT = 10


def _to_int(text: Any) -> int | None:
    """``'+9,822'`` / ``'-21,196'`` / ``'0'`` → int. 해석 불가면 None."""
    try:
        return int(str(text).replace(",", "").replace("+", "").strip())
    except ValueError:
        return None


def _fetch_trend(ticker: str) -> list[dict[str, Any]]:
    try:
        resp = requests.get(
            _TREND_URL.format(ticker=ticker), headers=_HEADERS, timeout=_REQUEST_TIMEOUT
        )
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"네이버 증권 수급 요청 실패 ({type(exc).__name__})") from None
    if resp.status_code != 200:
        raise VendorUnavailableError(f"네이버 증권 수급 HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError:
        raise VendorUnavailableError("네이버 증권 수급 응답이 JSON 이 아닙니다") from None
    if not isinstance(payload, list):
        raise VendorUnavailableError("네이버 증권 수급 응답 구조가 예상과 다릅니다")
    return [row for row in payload if isinstance(row, dict)]


def get_investor_flow(ticker: str, trade_date: str, look_back_days: int = 5) -> str:
    """기준일(``trade_date``, ``YYYY-MM-DD``) 이전 최근 ``look_back_days`` 거래일 순매수.

    기준일 이후 데이터는 제외한다 (룩어헤드 방지).

    Raises:
        VendorUnavailableError: 요청 실패·비정상 응답, 또는 기준일 이전 데이터가 없음
            (기준일이 최근 10거래일 밖).
    """
    cutoff = trade_date.replace("-", "")
    rows = [r for r in _fetch_trend(ticker) if str(r.get("bizdate", "")) and str(r["bizdate"]) <= cutoff]
    rows.sort(key=lambda r: str(r["bizdate"]), reverse=True)
    rows = rows[: max(1, look_back_days)]
    parsed = []
    for r in rows:
        foreign = _to_int(r.get("foreignerPureBuyQuant"))
        organ = _to_int(r.get("organPureBuyQuant"))
        individual = _to_int(r.get("individualPureBuyQuant"))
        if None in (foreign, organ, individual):
            continue
        parsed.append((str(r["bizdate"]), foreign, organ, individual, str(r.get("foreignerHoldRatio", ""))))
    if not parsed:
        raise VendorUnavailableError(
            f"네이버 증권 수급: {trade_date} 이전 데이터가 없습니다 (최근 10거래일만 제공)"
        )

    total_f = sum(p[1] for p in parsed)
    total_o = sum(p[2] for p in parsed)
    total_i = sum(p[3] for p in parsed)
    lines = [
        f"**{trade_date} 기준 최근 {len(parsed)} 거래일 순매수** (단위: 주, 출처: 네이버 증권)",
        "",
        "| 일자 | 외국인 | 기관 | 개인 | 외국인 보유율 |",
        "|---|---:|---:|---:|---:|",
    ]
    for day, f, o, i, ratio in parsed:
        lines.append(f"| {day[:4]}-{day[4:6]}-{day[6:]} | {f:+,} | {o:+,} | {i:+,} | {ratio} |")
    lines.append(f"| **합계** | **{total_f:+,}** | **{total_o:+,}** | **{total_i:+,}** | |")
    lines.append("")
    lines.append(
        "※ 금액(원)이 아니라 수량(주)입니다. 기관 세부(연기금·투신 등)와 기타법인은 구분되지 않습니다."
    )
    return "\n".join(lines) + "\n"
