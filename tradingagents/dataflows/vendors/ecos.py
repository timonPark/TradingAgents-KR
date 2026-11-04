"""한국은행 ECOS (경제통계시스템) 거시지표 vendor.

Task 7b (#63): 상류 FRED (미국 St. Louis Fed) vendor 를 한국은행 ECOS Open API 로
교체. 상류 ``fred.get_macro_data`` 와 **동일 시그니처** 로 router 가 vendor 교체만
하면 작동하도록 설계.

### 인증
무료 API 키 (https://ecos.bok.or.kr/) → ``ECOS_API_KEY`` 환경변수. 없으면
``EcosNotConfiguredError`` 를 올려 라우팅 레이어가 "unavailable" 로 처리.

### 지표 매핑
``MACRO_SERIES`` dict 가 사람 친화적 alias → ``(STAT_CODE, CYCLE, ITEM_CODE)``
튜플을 매핑. 사이클은 ECOS 코드 (``A`` 연간 / ``S`` 반기 / ``Q`` 분기 / ``M`` 월
/ ``D`` 일) 에 맞춤.

### 응답 처리
ECOS 는 ``RESULT.CODE`` 로 에러를 반환 (HTTP 200 유지). 성공 시 ``StatisticSearch
.row`` 리스트. ``DATA_VALUE`` 는 문자열이라 숫자 변환 후 포맷.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from tradingagents.dataflows.errors import VendorNotConfiguredError
from tradingagents.dataflows.net import get_scrubbed

logger = logging.getLogger(__name__)

ECOS_API_BASE = "https://ecos.bok.or.kr/api"
REQUEST_TIMEOUT = 30
DEFAULT_LOOKBACK_DAYS = 365
MAX_ROWS = 40
# 요청 행 상한. ECOS 는 구간의 오래된 쪽부터 행을 주므로 상한이 작으면 일별
# 시계열의 최근값이 잘린다 (#137). 구간 전체를 받고 표시 단계에서 자른다.
FETCH_ROW_LIMIT = 10000

# ECOS 통계 사이클 코드
CYCLE_DAILY = "D"
CYCLE_MONTHLY = "M"
CYCLE_QUARTERLY = "Q"
CYCLE_ANNUAL = "A"


# 사람 친화적 alias → (STAT_CODE, CYCLE, ITEM_CODE 또는 None).
# ITEM_CODE 가 None 이면 STAT_CODE 전체에서 첫 레코드만 추출.
MACRO_SERIES: dict[str, tuple[str, str, str | None]] = {
    # 정책금리 및 시장금리
    "base_rate": ("722Y001", CYCLE_DAILY, "0101000"),            # 한국은행 기준금리
    "policy_rate": ("722Y001", CYCLE_DAILY, "0101000"),
    "call_rate": ("722Y001", CYCLE_DAILY, "0010100"),            # 콜금리 (익일물)
    "cd_rate_91": ("722Y001", CYCLE_DAILY, "0101000"),            # 양도성예금증서 (91일)
    "treasury_3y": ("817Y002", CYCLE_DAILY, "010190000"),         # 국고채 3년
    "treasury_10y": ("817Y002", CYCLE_DAILY, "010210000"),        # 국고채 10년
    # 인플레이션
    "cpi": ("901Y009", CYCLE_MONTHLY, "0"),                        # 소비자물가지수
    "core_cpi": ("901Y009", CYCLE_MONTHLY, "QA"),                  # 근원물가지수 (농산물·석유류제외)
    "ppi": ("404Y014", CYCLE_MONTHLY, "*AA"),                      # 생산자물가지수
    # 성장·생산
    "real_gdp": ("200Y001", CYCLE_QUARTERLY, "10101"),            # 실질 GDP
    "gdp": ("200Y001", CYCLE_QUARTERLY, "10101"),
    "industrial_production": ("901Y033", CYCLE_MONTHLY, "A00"),    # 산업생산지수
    # 통화
    "m2": ("101Y003", CYCLE_MONTHLY, "BBHS00"),                   # 광의통화 M2
    "money_supply": ("101Y003", CYCLE_MONTHLY, "BBHS00"),
    "m1": ("101Y003", CYCLE_MONTHLY, "BBHA00"),                   # 협의통화 M1
    # 환율
    "usd_krw": ("731Y001", CYCLE_DAILY, "0000001"),               # 원/미국달러 매매기준율
    "exchange_rate": ("731Y001", CYCLE_DAILY, "0000001"),
    "jpy_krw": ("731Y001", CYCLE_DAILY, "0000002"),               # 원/일본엔 (100엔)
    "eur_krw": ("731Y001", CYCLE_DAILY, "0000003"),               # 원/유로
    "cny_krw": ("731Y001", CYCLE_DAILY, "0000053"),               # 원/위안
    # 노동
    "unemployment_rate": ("901Y027", CYCLE_MONTHLY, "I61E"),       # 실업률
    "unemployment": ("901Y027", CYCLE_MONTHLY, "I61E"),
    "employment_rate": ("901Y027", CYCLE_MONTHLY, "I61A"),         # 고용률
    # 심리
    "consumer_sentiment": ("511Y002", CYCLE_MONTHLY, "FME"),       # 소비자심리지수 CSI
    "business_sentiment": ("512Y014", CYCLE_MONTHLY, "AX1AA"),     # 기업경기실사지수 BSI (제조업)
}


class EcosNotConfiguredError(VendorNotConfiguredError):
    """``ECOS_API_KEY`` 환경변수가 없을 때. VendorNotConfiguredError 를 상속해
    라우팅 레이어가 "vendor unavailable" 로 처리하도록."""


def get_api_key() -> str:
    """``ECOS_API_KEY`` 환경변수 조회."""
    key = os.getenv("ECOS_API_KEY")
    if not key:
        raise EcosNotConfiguredError(
            "ECOS_API_KEY 환경변수가 설정되지 않았습니다. "
            "https://ecos.bok.or.kr/ 에서 무료 인증키 발급 후 .env 에 추가하세요."
        )
    return key


def _resolve_series(indicator: str) -> tuple[str, str, str | None]:
    """사람 친화적 alias → (STAT_CODE, CYCLE, ITEM_CODE).

    매핑에 없으면 ``ValueError`` — LLM 이 설명 문구를 넘겼을 가능성이 높아 명확히 안내.
    """
    key = indicator.strip().lower().replace(" ", "_").replace("-", "_")
    if key not in MACRO_SERIES:
        raise ValueError(
            f"'{indicator}' 은 지원되는 ECOS 지표 alias 가 아닙니다. "
            f"예: 'base_rate', 'cpi', 'unemployment_rate', 'usd_krw', 'real_gdp'. "
            f"전체 목록은 ``MACRO_SERIES`` 참조."
        )
    return MACRO_SERIES[key]


def _format_period(dt: datetime, cycle: str) -> str:
    """datetime → ECOS 기간 포맷. cycle 별로:
    - ``D``: YYYYMMDD
    - ``M``: YYYYMM
    - ``Q``: YYYYQn
    - ``A``: YYYY
    """
    if cycle == CYCLE_DAILY:
        return dt.strftime("%Y%m%d")
    if cycle == CYCLE_MONTHLY:
        return dt.strftime("%Y%m")
    if cycle == CYCLE_QUARTERLY:
        return f"{dt.year}Q{(dt.month - 1) // 3 + 1}"
    if cycle == CYCLE_ANNUAL:
        return dt.strftime("%Y")
    raise ValueError(f"Unknown ECOS cycle: {cycle!r}")


def _parse_period(text: str, cycle: str) -> datetime | None:
    """ECOS TIME 필드 → datetime. 포맷 실패 시 None."""
    try:
        if cycle == CYCLE_DAILY:
            return datetime.strptime(text, "%Y%m%d")
        if cycle == CYCLE_MONTHLY:
            return datetime.strptime(text, "%Y%m")
        if cycle == CYCLE_QUARTERLY:
            year, _, q = text.partition("Q")
            return datetime(int(year), (int(q) - 1) * 3 + 1, 1)
        if cycle == CYCLE_ANNUAL:
            return datetime.strptime(text, "%Y")
    except (ValueError, TypeError):
        return None
    return None


def _fetch(stat_code: str, cycle: str, start_period: str, end_period: str,
           item_code: str | None) -> list[dict]:
    """ECOS StatisticSearch 호출 → row 리스트. 에러 시 raise."""
    api_key = get_api_key()
    # URL 세그먼트 조립: /StatisticSearch/{KEY}/json/kr/1/{LIMIT}/{STAT}/{CYCLE}/{START}/{END}/{ITEM1}/
    segments = [
        "StatisticSearch", api_key, "json", "kr",
        "1", str(FETCH_ROW_LIMIT),
        stat_code, cycle, start_period, end_period,
    ]
    if item_code:
        segments.append(item_code)
    url = ECOS_API_BASE + "/" + "/".join(segments) + "/"
    # ECOS 는 키·조회조건을 URL 경로에 넣으므로 쿼리 파라미터가 없다.
    response = get_scrubbed(url, params={}, timeout=REQUEST_TIMEOUT, secret=api_key)
    if response.status_code != 200:
        raise RuntimeError(f"ECOS HTTP {response.status_code}: {response.text[:200]}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"ECOS JSON 파싱 실패: {exc}") from exc
    # ECOS 는 에러를 RESULT.CODE 로 반환 (HTTP 200 유지)
    if "RESULT" in payload:
        code = payload["RESULT"].get("CODE", "?")
        message = payload["RESULT"].get("MESSAGE", "")
        raise RuntimeError(f"ECOS 에러 {code}: {message}")
    rows = payload.get("StatisticSearch", {}).get("row", [])
    return rows or []


def _format_value(raw: str) -> str:
    """DATA_VALUE 문자열을 숫자로 변환해 보기 좋게 포맷. 실패 시 원문."""
    try:
        value = float(raw)
    except (ValueError, TypeError):
        return str(raw)
    if abs(value) >= 1e6:
        return f"{value:,.0f}"
    if abs(value) >= 100:
        return f"{value:,.2f}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def get_macro_data(
    indicator: str,
    as_of_date: str,
    look_back_days: int | None = None,
) -> str:
    """ECOS 거시 시계열을 Markdown 리포트로 반환.

    상류 ``fred.get_macro_data`` 와 동일 시그니처 — router 가 vendor 교체만으로
    작동.

    Args:
        indicator: ``MACRO_SERIES`` 의 alias (예: ``"base_rate"``, ``"cpi"``,
            ``"usd_krw"``).
        as_of_date: 분석 기준일 (``YYYY-MM-DD``). 이 날짜까지의 관측치만 반환.
        look_back_days: 뒤로 몇 일. ``None`` 은 ``DEFAULT_LOOKBACK_DAYS``.

    Returns:
        Markdown 리포트: 지표명, 사이클, 단위, 최신값, 변화량, 관측 표.
    """
    if look_back_days is None:
        look_back_days = DEFAULT_LOOKBACK_DAYS
    try:
        end_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return f"[ECOS 조회 실패: 잘못된 날짜 형식 {as_of_date!r}]"
    start_dt = end_dt - timedelta(days=look_back_days)

    try:
        stat_code, cycle, item_code = _resolve_series(indicator)
    except ValueError as exc:
        return f"[ECOS 조회 실패: {exc}]"

    start_period = _format_period(start_dt, cycle)
    end_period = _format_period(end_dt, cycle)

    try:
        rows = _fetch(stat_code, cycle, start_period, end_period, item_code)
    except EcosNotConfiguredError as exc:
        return f"[ECOS 조회 실패: {exc}]"
    except Exception as exc:  # noqa: BLE001 — 분석가 중단 방지
        return f"[ECOS 조회 실패: {exc}]"

    if not rows:
        return (
            f"## ECOS 거시지표: {indicator}\n\n"
            f"조회 기간 ({start_period} ~ {end_period}) 내 데이터가 없습니다.\n"
        )

    # ECOS 는 시간 역순으로 반환될 수 있으므로 명시적으로 TIME 오름차순 정렬.
    rows.sort(key=lambda r: r.get("TIME", ""))

    first = rows[0]
    last = rows[-1]
    title = last.get("STAT_NAME") or last.get("ITEM_NAME1") or indicator
    unit = last.get("UNIT_NAME", "")
    item_name = last.get("ITEM_NAME1", "")

    first_value = _format_value(first.get("DATA_VALUE", ""))
    last_value = _format_value(last.get("DATA_VALUE", ""))

    # 변화량/변화율 계산 (가능한 경우)
    try:
        first_f = float(first.get("DATA_VALUE", ""))
        last_f = float(last.get("DATA_VALUE", ""))
        delta = last_f - first_f
        pct = (delta / first_f * 100) if first_f else None
        change_line = (
            f"- **변화**: {_format_value(str(delta))}"
            + (f" ({pct:+.2f}%)" if pct is not None else "")
        )
    except (ValueError, TypeError):
        change_line = ""

    lines = [
        f"## {title} ({indicator})",
        "",
        f"- **지표 코드**: {stat_code}" + (f" / {item_code}" if item_code else ""),
        f"- **단위**: {unit or '—'}",
        f"- **사이클**: {cycle}",
        f"- **최근값** ({last.get('TIME', '')}): {last_value}",
        f"- **기간 시작** ({first.get('TIME', '')}): {first_value}",
    ]
    if change_line:
        lines.append(change_line)
    if item_name:
        lines.append(f"- **항목명**: {item_name}")

    lines += ["", "### 관측 데이터", "", "| 기간 | 값 |", "|---|---:|"]
    # 가장 최근 MAX_ROWS 만 표시 (오래된 쪽부터 자름)
    display = rows[-MAX_ROWS:]
    for row in display:
        lines.append(f"| {row.get('TIME', '')} | {_format_value(row.get('DATA_VALUE', ''))} |")

    return "\n".join(lines)
