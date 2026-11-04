"""NAVER API HUB 뉴스 검색 vendor — KRX 종목 뉴스 (#138).

네이버 검색 오픈 API 는 2026-07-31 부터 개발자센터 신규 신청이 막히고 NCP 의
NAVER API HUB 로 이관됐다. 요청 URL·인증 헤더가 개발자센터 버전과 다르다.

- 요청: ``GET https://naverapihub.apigw.ntruss.com/search/v1/news``
- 인증 헤더: ``X-NCP-APIGW-API-KEY-ID`` / ``X-NCP-APIGW-API-KEY``
- 환경변수: ``NAVER_API_HUB_CLIENT_ID`` / ``NAVER_API_HUB_CLIENT_SECRET``

### 종목 매칭
검색은 회사명 키워드 기반이라 본문에 회사명이 스쳐 지나간 무관 기사가 섞인다.
다음 중 하나를 만족하는 기사만 남긴다.

- 제목에 회사명이 있다
- 제목 또는 요약에 6자리 종목코드가 있다 (예: ``금호전기(001210)`` 공시성 기사)

### 실패 처리
"0건" 과 "수집 실패" 를 구분한다. 키 없음·인증 실패는
``VendorNotConfiguredError``, 한도 초과·서버 오류·네트워크 오류는
``VendorUnavailableError`` 로 올려 라우터가 다음 vendor(네이버 증권)로 넘기거나
``DATA_UNAVAILABLE`` 로 보고하게 한다. 정상 응답이 비어 있을 때만 "뉴스 없음".
"""

from __future__ import annotations

import html
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import requests

from tradingagents.dataflows.errors import VendorNotConfiguredError, VendorUnavailableError
from tradingagents.dataflows.vendors.naver_news import (
    _format_news_markdown,
    _is_noise,
    _parse_ymd,
)

logger = logging.getLogger(__name__)

API_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
REQUEST_TIMEOUT = 10  # 초
PAGE_SIZE = 100
MAX_PAGES = 5
MAX_ITEMS = 30  # 프롬프트 길이 상한

_KST = timezone(timedelta(hours=9))
_TAG_RE = re.compile(r"<[^>]+>")


def get_credentials() -> tuple[str, str]:
    """(client_id, client_secret). 없으면 ``VendorNotConfiguredError``."""
    client_id = os.environ.get("NAVER_API_HUB_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NAVER_API_HUB_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise VendorNotConfiguredError(
            "NAVER_API_HUB_CLIENT_ID / NAVER_API_HUB_CLIENT_SECRET 환경변수가 필요합니다 "
            "(NCP 콘솔 > NAVER API HUB > Application > 인증 정보)."
        )
    return client_id, client_secret


def _clean(text: str) -> str:
    """검색어 강조 태그 제거 + HTML 엔티티 복원."""
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def _parse_pub_date(text: str) -> datetime | None:
    """RFC 822 ``pubDate`` → KST naive datetime."""
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(_KST).replace(tzinfo=None)
    return dt


def _resolve_company_name(ticker: str) -> str:
    """종목코드 → 종목명. 조회 실패 시 ``VendorUnavailableError``."""
    from tradingagents.dataflows import krx_symbol_search

    try:
        hits = krx_symbol_search.search(ticker, limit=1)
    except Exception as exc:  # noqa: BLE001 — 외부 종목 리스트 실패 흡수
        raise VendorUnavailableError(f"종목명 조회 실패 ({type(exc).__name__}): {ticker}") from None
    if not hits:
        raise VendorUnavailableError(f"종목명을 찾을 수 없습니다: {ticker}")
    return hits[0].name


def _matches_company(title: str, description: str, name: str, ticker: str) -> bool:
    if name and name in title:
        return True
    return ticker in title or ticker in description


def _request(query: str, start: int, client_id: str, client_secret: str) -> dict[str, Any]:
    headers = {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret,
    }
    params = {"query": query, "display": PAGE_SIZE, "start": start, "sort": "date"}
    try:
        resp = requests.get(API_URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        # 예외 메시지에는 URL 만 담기고 키(헤더)는 담기지 않는다. 체인은 끊는다.
        raise VendorUnavailableError(f"API HUB 네트워크 오류: {type(exc).__name__}") from None
    if resp.status_code in (401, 403):
        raise VendorNotConfiguredError(
            f"API HUB 인증 실패 (HTTP {resp.status_code}) — 키 또는 Application 의 "
            "'NAVER 검색 > 뉴스' 사용 설정을 확인하세요."
        )
    if resp.status_code == 429:
        raise VendorUnavailableError("API HUB 호출 한도 초과 (HTTP 429)")
    if resp.status_code != 200:
        raise VendorUnavailableError(f"API HUB HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError:
        raise VendorUnavailableError("API HUB 응답이 JSON 이 아닙니다") from None
    if not isinstance(payload, dict) or "items" not in payload:
        code = payload.get("errorCode") if isinstance(payload, dict) else None
        raise VendorUnavailableError(f"API HUB 비정상 응답 (errorCode={code})")
    return payload


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """KRX 종목의 지정 기간 뉴스를 API HUB 에서 가져와 Markdown 으로.

    상류 ``get_news(ticker, start_date, end_date)`` 와 shape 호환.
    """
    start_dt = _parse_ymd(start_date)
    end_dt = _parse_ymd(end_date)
    if not (start_dt and end_dt):
        return f"[네이버뉴스 조회 실패: 잘못된 날짜 형식 {start_date!r} ~ {end_date!r}]"
    end_dt = end_dt.replace(hour=23, minute=59)

    client_id, client_secret = get_credentials()
    name = _resolve_company_name(ticker)
    query = f'"{name}"'

    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in range(MAX_PAGES):
        payload = _request(query, 1 + page * PAGE_SIZE, client_id, client_secret)
        raw_items = payload.get("items") or []
        if not raw_items:
            break
        oldest: datetime | None = None
        for raw in raw_items:
            date = _parse_pub_date(raw.get("pubDate", ""))
            if date is not None and (oldest is None or date < oldest):
                oldest = date
            title = _clean(raw.get("title", ""))
            description = _clean(raw.get("description", ""))
            if not title or _is_noise(title) or title in seen:
                continue
            if date is not None and not (start_dt <= date <= end_dt):
                continue
            if not _matches_company(title, description, name, ticker):
                continue
            seen.add(title)
            link = raw.get("originallink") or raw.get("link") or ""
            host = urlparse(link).netloc.removeprefix("www.")
            collected.append({"title": title, "source": host, "date": date, "url": link})
        # 최신순이므로 가장 오래된 기사가 시작일 이전이면 더 볼 필요 없음
        if oldest is not None and oldest < start_dt:
            break
        if len(raw_items) < PAGE_SIZE:
            break

    collected.sort(key=lambda i: i["date"] or datetime.min, reverse=True)
    return _format_news_markdown(ticker, start_date, end_date, collected[:MAX_ITEMS])
