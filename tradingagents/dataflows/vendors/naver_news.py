"""네이버 증권 뉴스 vendor — KRX 종목·시장 뉴스.

Task 7a (#62): 상류 Yahoo/Alpha Vantage 뉴스 vendor 를 네이버 금융 뉴스로 교체.
API 키 없이 공개 경로에서 뉴스 헤드라인/날짜/출처/URL 을 추출.

### 엔드포인트 (#138 갱신)
- 종목별 뉴스: ``https://m.stock.naver.com/api/news/stock/{ticker}?pageSize=N&page=P``
  (JSON, 최신순, 비공식 경로). 기존 ``finance.naver.com/item/news_news.naver`` 는
  2026-11 현재 HTTP 410 으로 폐지됐다.
- 주요뉴스: ``https://m.stock.naver.com/api/news/list?category=mainnews&pageSize=N&page=P``
  (JSON, 최신순, 비공식 경로, #189). 기존 ``finance.naver.com/news/mainnews.naver`` 는
  ``stock.naver.com`` 으로 리다이렉트되어 폐지됐다. 날짜 파라미터는 무시되므로
  최신순으로 페이지를 넘기며 기준일 창에 닿을 때까지 읽는다.

### 실패 처리
"뉴스 0건" 과 "수집 실패" 를 구분한다. HTTP 오류·폐지(410)·리다이렉트·JSON 이
아닌 응답은 ``VendorUnavailableError`` 로 올려 라우터가 ``DATA_UNAVAILABLE`` 로
보고하게 한다. 정상 응답이 비어 있을 때만 "뉴스 없음".

### 반환 shape
상류 ``yahoo.news.get_news`` / ``alpha_vantage.news.get_news`` 와 동일하게
사람이 읽기 쉬운 Markdown 문자열. 분석가가 바로 프롬프트에 주입 가능.

### 네트워크 호출
유닛 테스트는 `requests.get` 을 전부 mock 함. 통합 테스트는 ``-m integration``.
"""

from __future__ import annotations

import html as _html
import logging
from datetime import datetime, timedelta
from typing import Any

import requests

from tradingagents.dataflows.errors import VendorUnavailableError

logger = logging.getLogger(__name__)

_MAIN_NEWS_API = "https://m.stock.naver.com/api/news/list"
_MAIN_NEWS_PAGE_SIZE = 20  # 100 은 비-JSON 응답을 돌려준다
_MAIN_NEWS_MAX_PAGES = 60  # 하루 7~8쪽 → 약 1주일 분량
_STOCK_NEWS_API = "https://m.stock.naver.com/api/news/stock"
_STOCK_NEWS_PAGE_SIZE = 20
_STOCK_NEWS_MAX_PAGES = 5
_HEADERS = {
    # 네이버 금융은 User-Agent 가 없으면 가끔 403 을 돌려줌. 일반 브라우저 UA 로.
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.5,en;q=0.3",
}
_REQUEST_TIMEOUT = 10  # 초

# 노이즈 제거 — 광고/반복/묶음 기사 패턴
_NOISE_KEYWORDS = (
    "[부고]",
    "[인사]",
    "[동정]",
    "[포토]",
    "[사진]",
    "[속보]일정",
    "증시요약",  # 전종목 묶음 요약은 특정 종목 분석에 노이즈
)


def _get_json_list(url: str, params: dict[str, Any]) -> list[Any]:
    """네이버 증권 JSON(리스트) GET + 공통 에러 처리. 실패·구조 불일치는 ``VendorUnavailableError``.

    "수집 실패" 를 빈 결과("뉴스 없음") 로 위장하지 않는다 (#138): 폐지된 URL 의
    410, 리다이렉트로 인한 HTML 응답 모두 호출자가 알 수 있어야 한다.
    """
    try:
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"네이버 증권 요청 실패 ({type(exc).__name__})") from None
    if resp.status_code != 200:
        raise VendorUnavailableError(f"네이버 증권 HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError:
        raise VendorUnavailableError("네이버 증권 응답이 JSON 이 아닙니다") from None
    if not isinstance(payload, list):
        raise VendorUnavailableError("네이버 증권 응답 구조가 예상과 다릅니다")
    return payload


def _fetch_stock_news_json(ticker: str, page: int) -> list[dict[str, Any]]:
    """네이버 증권 종목 뉴스 JSON 한 페이지 → 평탄화된 기사 dict 리스트.

    응답은 ``[{"total": N, "items": [...]}, ...]`` 형태(클러스터 리스트).
    실패하거나 구조가 다르면 ``VendorUnavailableError``.
    """
    payload = _get_json_list(
        f"{_STOCK_NEWS_API}/{ticker}",
        {"pageSize": _STOCK_NEWS_PAGE_SIZE, "page": page},
    )
    items: list[dict[str, Any]] = []
    for cluster in payload:
        if isinstance(cluster, dict):
            items.extend(i for i in cluster.get("items") or [] if isinstance(i, dict))
    return items


def _parse_stock_news_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    """증권 JSON 기사 → ``{title, source, date, url}``. 제목이 없으면 None."""
    title = _html.unescape(str(raw.get("titleFull") or raw.get("title") or "")).strip()
    if not title:
        return None
    date = None
    stamp = str(raw.get("datetime") or "")
    try:
        date = datetime.strptime(stamp, "%Y%m%d%H%M")
    except ValueError:
        date = None
    return {
        "title": title,
        "source": str(raw.get("officeName") or ""),
        "date": date,
        "url": str(raw.get("mobileNewsUrl") or ""),
    }


def _parse_ymd(date_str: str) -> datetime | None:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _is_noise(title: str) -> bool:
    """노이즈 (광고/묶음/인사) 기사 걸러내기."""
    t = title.strip()
    return any(k in t for k in _NOISE_KEYWORDS)


def _parse_main_news_item(raw: Any) -> dict[str, Any] | None:
    """주요뉴스 JSON 기사 → ``{title, source, date, url}``. 제목·시각이 없으면 None."""
    if not isinstance(raw, dict):
        return None
    title = _html.unescape(str(raw.get("tit") or "")).strip()
    if not title:
        return None
    try:
        date = datetime.strptime(str(raw.get("dt") or ""), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    oid, aid = raw.get("oid"), raw.get("aid")
    return {
        "title": title,
        "source": str(raw.get("ohnm") or ""),
        "date": date,
        "url": f"https://n.news.naver.com/mnews/article/{oid}/{aid}" if oid and aid else "",
    }


def _format_news_markdown(ticker: str, start: str, end: str, items: list[dict[str, Any]]) -> str:
    """추출된 뉴스를 분석가 프롬프트용 Markdown 으로 포맷."""
    header = f"## {ticker} 뉴스 ({start} ~ {end})\n\n"
    if not items:
        return header + "해당 기간 뉴스가 없습니다.\n"
    lines = []
    for item in items:
        date_str = item["date"].strftime("%Y-%m-%d %H:%M") if item["date"] else "날짜 미상"
        source = item.get("source") or "출처 미상"
        title = item["title"]
        url = item.get("url") or ""
        line = f"- **{date_str}** | {source} | {title}"
        if url:
            line += f"\n  - {url}"
        lines.append(line)
    return header + "\n".join(lines) + "\n"


def _in_date_range(item_date: datetime | None, start: datetime, end: datetime) -> bool:
    """날짜 필터 — 날짜 없으면 보존 (분석가가 볼 수 있도록)."""
    if item_date is None:
        return True
    return start <= item_date <= end


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """KRX 종목의 지정 기간 뉴스를 네이버 증권에서 가져와 Markdown 으로.

    상류 ``get_news(ticker, start_date, end_date)`` 와 shape 호환.
    종목 뉴스는 최신 순으로 반환되므로 날짜 범위를 벗어나면 조기 종료.
    수집 실패는 ``VendorUnavailableError`` — "뉴스 없음" 으로 위장하지 않는다.
    """
    start_dt = _parse_ymd(start_date)
    end_dt = _parse_ymd(end_date)
    if not (start_dt and end_dt):
        return f"[네이버뉴스 조회 실패: 잘못된 날짜 형식 {start_date!r} ~ {end_date!r}]"
    # 종일 포함
    end_dt = end_dt.replace(hour=23, minute=59)

    all_items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in range(1, _STOCK_NEWS_MAX_PAGES + 1):
        raw_items = _fetch_stock_news_json(ticker, page)
        if not raw_items:
            break
        parsed = [p for p in (_parse_stock_news_item(r) for r in raw_items) if p]
        for item in parsed:
            if _is_noise(item["title"]) or item["title"] in seen:
                continue
            if not _in_date_range(item["date"], start_dt, end_dt):
                continue
            seen.add(item["title"])
            all_items.append(item)
        # 가장 오래된 아이템이 start 보다 이전이면 조기 종료
        oldest = min((i["date"] for i in parsed if i["date"]), default=None)
        if oldest is not None and oldest < start_dt:
            break

    all_items.sort(key=lambda i: i["date"] or datetime.min, reverse=True)
    return _format_news_markdown(ticker, start_date, end_date, all_items)


def get_global_news(as_of_date: str, look_back_days: int | None = None, limit: int | None = None) -> str:
    """시장 전체 주요뉴스를 네이버 금융 주요뉴스에서.

    상류 ``get_global_news(as_of_date, look_back_days, limit)`` 와 호환.
    ``look_back_days`` 가 None 이면 1일 (당일 주요뉴스), ``limit`` 가 None 이면 20.
    """
    as_of_dt = _parse_ymd(as_of_date)
    if not as_of_dt:
        return f"[네이버 주요뉴스 조회 실패: 잘못된 날짜 형식 {as_of_date!r}]"
    look_back = max(1, int(look_back_days or 1))
    cap = max(1, int(limit or 20))
    window_start = as_of_dt - timedelta(days=look_back - 1)
    window_end = as_of_dt + timedelta(days=1)  # 기준일 당일 포함 (배타적 상한)

    # 날짜 파라미터가 없는 최신순 목록이라, 기준일보다 새로운 기사는 건너뛰고
    # 창 시작보다 오래된 기사가 나오면 멈춘다.
    all_items: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    reached_window = False
    for page in range(1, _MAIN_NEWS_MAX_PAGES + 1):
        payload = _get_json_list(
            _MAIN_NEWS_API,
            {"category": "mainnews", "pageSize": _MAIN_NEWS_PAGE_SIZE, "page": page},
        )
        if not payload:
            break  # 더 이상 기사가 없음
        done = False
        for raw in payload:
            item = _parse_main_news_item(raw)
            if item is None or item["date"] >= window_end:
                continue
            reached_window = True
            if item["date"] < window_start:
                done = True
                break
            if _is_noise(item["title"]) or item["title"] in seen_titles:
                continue
            seen_titles.add(item["title"])
            all_items.append(item)
            if len(all_items) >= cap:
                done = True
                break
        if done:
            break
    if not reached_window and payload:
        raise VendorUnavailableError(
            f"네이버 주요뉴스가 조회 한도({_MAIN_NEWS_MAX_PAGES}쪽) 안에서 기준일 "
            f"{as_of_date} 에 닿지 못했습니다 (너무 과거 기준일)"
        )

    header = f"## 주요뉴스 ({as_of_date}, 최근 {look_back}일)\n\n"
    if not all_items:
        return header + "주요뉴스가 없습니다.\n"
    lines = []
    for item in all_items[:cap]:
        date_str = item["date"].strftime("%Y-%m-%d %H:%M") if item["date"] else "날짜 미상"
        source = item.get("source") or "출처 미상"
        title = item["title"]
        url = item.get("url") or ""
        line = f"- **{date_str}** | {source} | {title}"
        if url:
            line += f"\n  - {url}"
        lines.append(line)
    return header + "\n".join(lines) + "\n"
