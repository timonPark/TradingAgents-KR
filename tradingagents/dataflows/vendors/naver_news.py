"""네이버 증권 뉴스 vendor — KRX 종목·시장 뉴스.

Task 7a (#62): 상류 Yahoo/Alpha Vantage 뉴스 vendor 를 네이버 금융 뉴스로 교체.
API 키 없이 공개 경로에서 뉴스 헤드라인/날짜/출처/URL 을 추출.

### 엔드포인트 (#138 갱신)
- 종목별 뉴스: ``https://m.stock.naver.com/api/news/stock/{ticker}?pageSize=N&page=P``
  (JSON, 최신순, 비공식 경로). 기존 ``finance.naver.com/item/news_news.naver`` 는
  2026-11 현재 HTTP 410 으로 폐지됐다. 날짜 파라미터가 없고 종목당 최신 2000건까지만
  읽을 수 있어, 기사량이 많은 종목은 며칠 전 기사에 닿지 못한다 (#188).
- 주요뉴스: ``https://m.stock.naver.com/api/news/list?category=mainnews&pageSize=N&page=P``
  (JSON, 최신순, 비공식 경로, #189). 기존 ``finance.naver.com/news/mainnews.naver`` 는
  ``stock.naver.com`` 으로 리다이렉트되어 폐지됐다. 날짜 파라미터는 무시되므로
  최신순으로 페이지를 넘기며 기준일 창에 닿을 때까지 읽는다.

### 실패 처리
"뉴스 0건" 과 "수집 실패" 를 구분한다. HTTP 오류·폐지(410)·리다이렉트·JSON 이
아닌 응답은 ``VendorUnavailableError`` 로 올려 라우터가 ``DATA_UNAVAILABLE`` 로
보고하게 한다. 정상 응답이 비어 있을 때만 "뉴스 없음".

종목 뉴스는 최대 100쪽을 읽어 일시적 5xx 에 자주 노출된다 (#194). 5xx·네트워크
오류는 같은 쪽을 다시 부르고, 그래도 실패하면 기간 안 기사를 이미 읽은 경우에
한해 "일부만 조회됨" 경고와 함께 읽은 만큼 반환한다.

이 API 는 HTTP 200 + 빈 목록을 쪽 중간에 돌려줄 수 있다 (#198). 빈 쪽 하나를
"기사 끝" 으로 믿으면 수집 실패가 "뉴스 없음" 으로 위장되므로, 같은 쪽을 한 번 더
부르고 그래도 비면 다음 쪽까지 본 뒤 둘 다 비었을 때만 끝으로 본다.

### 반환 shape
상류 ``yahoo.news.get_news`` / ``alpha_vantage.news.get_news`` 와 동일하게
사람이 읽기 쉬운 Markdown 문자열. 분석가가 바로 프롬프트에 주입 가능.

### 네트워크 호출
유닛 테스트는 `requests.get` 을 전부 mock 함. 통합 테스트는 ``-m integration``.
"""

from __future__ import annotations

import html as _html
import logging
import time
from datetime import datetime, timedelta
from typing import Any

import requests

from tradingagents.dataflows.errors import VendorUnavailableError

logger = logging.getLogger(__name__)

_MAIN_NEWS_API = "https://m.stock.naver.com/api/news/list"
_MAIN_NEWS_PAGE_SIZE = 20  # 100 은 비-JSON 응답을 돌려준다
_MAIN_NEWS_MAX_PAGES = 60  # 하루 7~8쪽 → 약 1주일 분량
_STOCK_NEWS_API = "https://m.stock.naver.com/api/news/stock"
# pageSize 100 은 비-JSON 응답, 50 은 쪽 사이에 빈 구간·중복이 생겨 쓸 수 없다.
# 20 은 끊김 없이 이어지고 101쪽에서 HTTP 400 → 서버 상한 2000건 (20 × 100).
_STOCK_NEWS_PAGE_SIZE = 20
_STOCK_NEWS_MAX_PAGES = 100
_STOCK_NEWS_MAX_ITEMS = 30  # 프롬프트 길이 상한 (naver_api_hub.MAX_ITEMS 와 동일)
# 일시적 5xx·네트워크 오류 시 같은 쪽 재시도 대기(초). 2026-11-19 장애 때 같은 쪽을
# 다시 부르면 대개 성공했다 (502,200,502,200 …) (#194).
_STOCK_NEWS_RETRY_DELAYS = (0.5, 1.0)
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


class _TransientVendorError(VendorUnavailableError):
    """다시 부르면 성공할 수 있는 실패 (5xx·네트워크 오류)."""


def _get_json_list(url: str, params: dict[str, Any]) -> list[Any]:
    """네이버 증권 JSON(리스트) GET + 공통 에러 처리. 실패·구조 불일치는 ``VendorUnavailableError``.

    "수집 실패" 를 빈 결과("뉴스 없음") 로 위장하지 않는다 (#138): 폐지된 URL 의
    410, 리다이렉트로 인한 HTML 응답 모두 호출자가 알 수 있어야 한다.
    """
    try:
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise _TransientVendorError(f"네이버 증권 요청 실패 ({type(exc).__name__})") from None
    if resp.status_code >= 500:
        raise _TransientVendorError(f"네이버 증권 HTTP {resp.status_code}")
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


def _fetch_stock_news_json_with_retry(ticker: str, page: int) -> list[dict[str, Any]]:
    """``_fetch_stock_news_json`` + 일시적 오류 재시도. 재시도 후에도 실패하면 마지막 오류."""
    for delay in _STOCK_NEWS_RETRY_DELAYS:
        try:
            return _fetch_stock_news_json(ticker, page)
        except _TransientVendorError as exc:
            logger.warning("네이버 증권 뉴스 %s %d쪽 재시도 (%s)", ticker, page, exc)
            time.sleep(delay)
    return _fetch_stock_news_json(ticker, page)


def _recheck_empty_stock_page(ticker: str, page: int) -> tuple[list[dict[str, Any]], int]:
    """빈 쪽 재확인 (#198). 같은 쪽을 한 번 더, 그래도 비면 다음 쪽을 본다.

    반환: (기사, 그 기사를 읽은 쪽 번호). 둘 다 비었으면 기사가 빈 리스트 — 진짜 끝.
    마지막 허용 쪽에서는 다음 쪽을 부르지 않는다 (서버 상한 밖은 HTTP 400).
    """
    time.sleep(_STOCK_NEWS_RETRY_DELAYS[0])
    items = _fetch_stock_news_json_with_retry(ticker, page)
    if items:
        logger.warning("네이버 증권 뉴스 %s %d쪽이 빈 응답 후 재조회에서 기사 반환", ticker, page)
        return items, page
    if page >= _STOCK_NEWS_MAX_PAGES:
        return [], page
    items = _fetch_stock_news_json_with_retry(ticker, page + 1)
    if items:
        logger.warning("네이버 증권 뉴스 %s %d쪽이 비었지만 %d쪽에 기사가 있음", ticker, page, page + 1)
    return items, page + 1


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


def _format_news_markdown(
    ticker: str, start: str, end: str, items: list[dict[str, Any]], note: str = "",
) -> str:
    """추출된 뉴스를 분석가 프롬프트용 Markdown 으로 포맷.

    ``note`` 는 헤더 아래에 덧붙이는 주의 문구 (예: 조회 한도로 일부 기간만 조회됨).
    """
    header = f"## {ticker} 뉴스 ({start} ~ {end})\n\n"
    if note:
        header += f"> ⚠ {note}\n\n"
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
    oldest: datetime | None = None  # 지금까지 읽은 가장 오래된 기사
    reached_window = False  # 기간 끝(end) 이전 기사에 닿았는가
    covered = False  # 기간 시작(start) 이전까지(또는 기사 끝까지) 읽었는가
    failure: VendorUnavailableError | None = None  # 재시도 후에도 실패한 쪽의 사유
    page = 0
    while page < _STOCK_NEWS_MAX_PAGES:
        page += 1
        try:
            raw_items = _fetch_stock_news_json_with_retry(ticker, page)
            if not raw_items:
                raw_items, page = _recheck_empty_stock_page(ticker, page)
        except _TransientVendorError as exc:
            # 기간 안 기사를 이미 읽었으면 버리지 않고 부분 결과로 (#194). 아니면 실패.
            if not reached_window:
                raise
            failure = exc
            break
        if not raw_items:
            covered = True  # 재확인 후에도 비었음 — 더 읽을 기사가 없음
            break
        parsed = [p for p in (_parse_stock_news_item(r) for r in raw_items) if p]
        for item in parsed:
            if item["date"] is not None and item["date"] <= end_dt:
                reached_window = True
            if _is_noise(item["title"]) or item["title"] in seen:
                continue
            if not _in_date_range(item["date"], start_dt, end_dt):
                continue
            seen.add(item["title"])
            all_items.append(item)
        # 최신순이라 앞쪽 N건이 곧 반환분 — 채웠으면 더 읽지 않는다 (기간 커버리지도 무관).
        if len(all_items) >= _STOCK_NEWS_MAX_ITEMS:
            covered = True
            break
        page_oldest = min((i["date"] for i in parsed if i["date"]), default=None)
        if page_oldest is not None and (oldest is None or page_oldest < oldest):
            oldest = page_oldest
        # 가장 오래된 아이템이 start 보다 이전이면 기간을 모두 덮은 것
        if page_oldest is not None and page_oldest < start_dt:
            covered = True
            break
        if len(raw_items) < _STOCK_NEWS_PAGE_SIZE:
            covered = True  # 마지막 쪽
            break

    note = ""
    if failure is not None:
        note = (
            f"{failure} 로 {oldest:%Y-%m-%d %H:%M} 이후 기사만 조회됨 — 요청 기간 "
            f"{start_date} ~ {end_date} 중 앞쪽 일부는 확인하지 못했습니다. "
            "기사 없음으로 해석하지 마세요."
        )
    elif not covered:
        # 조회 한도(최신 N건)에 걸려 기간 시작까지 못 갔다. "무보도" 로 위장하지 않는다 (#188).
        if not reached_window:
            oldest_text = f"{oldest:%Y-%m-%d %H:%M}" if oldest else "날짜 미상"
            raise VendorUnavailableError(
                f"네이버 증권 뉴스 조회 한도(최신 {_STOCK_NEWS_PAGE_SIZE * _STOCK_NEWS_MAX_PAGES}건, "
                f"가장 오래된 기사 {oldest_text}) 안에서 {start_date} ~ {end_date} "
                f"기간에 닿지 못했습니다: {ticker}"
            )
        note = (
            f"조회 한도(최신 {_STOCK_NEWS_PAGE_SIZE * _STOCK_NEWS_MAX_PAGES}건)로 "
            f"{oldest:%Y-%m-%d} 이후 기사만 조회됨 — 요청 기간 {start_date} ~ {end_date} 중 "
            "앞쪽 일부는 확인하지 못했습니다. 기사 없음으로 해석하지 마세요."
        )

    all_items.sort(key=lambda i: i["date"] or datetime.min, reverse=True)
    return _format_news_markdown(
        ticker, start_date, end_date, all_items[:_STOCK_NEWS_MAX_ITEMS], note,
    )


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
