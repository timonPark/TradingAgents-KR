"""pykrx vendor — KRX 시세·기술지표·투자자별 수급.

Task 6a (#52): Yahoo Finance / Alpha Vantage 가격·지표 vendor 를 KRX 전용
`pykrx` 로 교체.

### API 요구사항
- **OHLCV** (`get_market_ohlcv_by_date`): keyless, 공개 엔드포인트
- **투자자별 수급** (`get_market_trading_value_by_investor`): KRX 가 로그인을 요구.
  pykrx 1.0.x (pandas 3 호환) 는 로그인을 지원하지 않으므로 ``krx_session`` 이
  ``KRX_ID`` / ``KRX_PW`` 로 로그인한 세션을 pykrx 의 HTTP 요청에 붙인다 (#139).
  KRX 조회가 실패하면 네이버 증권 매매동향(수량, 비공식)으로 폴백하고, 그것도
  실패하면 원인을 밝혀 "조회 실패" 로 표시해 보고서가 수급을 추정하지 않게 한다.

### 반환 shape
상류 `yahoo.ohlcv.load_ohlcv`, `yahoo.market.get_stock_stats_indicators_window`,
`alpha_vantage.stock.get_stock`, `yahoo.snapshot.build_verified_market_snapshot`
와 **같은 shape** 을 돌려줘 router·분석가가 거의 수정 없이 pykrx 로 전환 가능.

### 컬럼 매핑 (한국어 → 영어)
pykrx 는 OHLCV 를 한국어 컬럼으로 반환하므로 upstream 과 호환되는 영어 컬럼으로
변환: 시가→Open, 고가→High, 저가→Low, 종가→Close, 거래량→Volume. 등락률은
사용하지 않음.
"""

from __future__ import annotations

import importlib.metadata
import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from dateutil.relativedelta import relativedelta
from stockstats import wrap

from tradingagents.dataflows.errors import NoMarketDataError

logger = logging.getLogger(__name__)

# ``pykrx`` 는 KRX 로그인 자격증명을 환경변수로 요구하는 API 가 있음 — 투자자별
# 수급 / 시가총액 / 기본정보 중 일부. OHLCV 는 keyless.
_KRX_LOGIN_ENV = ("KRX_ID", "KRX_PW")


def _pykrx_version() -> str:
    try:
        return importlib.metadata.version("pykrx")
    except importlib.metadata.PackageNotFoundError:
        return "미설치"


def _diagnose_investor_failure(exc: Exception) -> str:
    """수급 조회 예외를 사람이 이해할 원인 문구로.

    ``KeyError: '거래대금'`` 같은 파서 내부 예외는 그대로 보여주면 원인을 알 수 없다.
    """
    detail = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, KeyError):
        return (
            f"{detail}. KRX 응답이 pykrx {_pykrx_version()} 가 기대한 형식이 아닙니다 "
            "(로그인 세션이 없거나 만료됐거나 KRX 응답 형식이 바뀐 것으로 보입니다)"
        )
    return detail


def _window_start(as_of_dt: datetime, look_back_days: int) -> datetime:
    """``as_of_dt`` 포함 최근 ``look_back_days`` 거래일의 첫 날.

    pykrx 의 투자자별 거래실적은 **기간 합계** 라서 시작일을 정확히 잡아야 "최근 N
    거래일" 이 된다. KRX 캘린더가 안 되면 주말만 제외한 영업일로 근사한다.
    """
    n = max(1, look_back_days)
    try:
        from tradingagents.dataflows.krx_calendar import trading_days_in_range

        lo = (as_of_dt - timedelta(days=n * 2 + 14)).strftime("%Y-%m-%d")
        days = trading_days_in_range(lo, as_of_dt.strftime("%Y-%m-%d"))
        if len(days) >= n:
            return datetime.strptime(days[-n], "%Y-%m-%d")
    except Exception as exc:  # noqa: BLE001 — 캘린더 호환성 문제는 근사로 대체
        logger.warning("KRX 캘린더 사용 불가, 주말 제외 근사 (%s): %s", type(exc).__name__, exc)
    day, counted = as_of_dt, 0
    while True:
        if day.weekday() < 5:
            counted += 1
            if counted == n:
                return day
        day -= timedelta(days=1)


# pykrx 는 날짜를 YYYYMMDD 포맷으로 받음.
def _to_krx_date(date_str: str) -> str:
    """``YYYY-MM-DD`` → ``YYYYMMDD``. 포맷 틀리면 빈 문자열."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y%m%d")
    except (ValueError, TypeError):
        return ""


# 영어 OHLCV 컬럼명으로 변환하기 위한 매핑.
_PYKRX_COLUMN_MAP = {
    "시가": "Open",
    "고가": "High",
    "저가": "Low",
    "종가": "Close",
    "거래량": "Volume",
    "거래대금": "Amount",
    "등락률": "ChangePct",
}


def _normalize_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    """pykrx OHLCV 를 상류 Yahoo load_ohlcv shape 로 변환.

    - 한국어 컬럼 → 영어 컬럼 (Open/High/Low/Close/Volume 등)
    - 인덱스 (날짜) → ``Date`` 컬럼
    - 날짜 역순 정렬 → 오름차순 정렬
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    out = df.rename(columns=_PYKRX_COLUMN_MAP).copy()
    # 인덱스를 Date 컬럼으로.
    out = out.reset_index()
    index_name = df.index.name or "index"
    if index_name in out.columns:
        out = out.rename(columns={index_name: "Date"})
    elif "날짜" in out.columns:
        out = out.rename(columns={"날짜": "Date"})
    out["Date"] = pd.to_datetime(out["Date"])
    out = out.sort_values("Date").reset_index(drop=True)
    return out


def load_ohlcv(ticker: str, as_of_date: str, fill_gaps: bool = True) -> pd.DataFrame:
    """``as_of_date`` 까지의 OHLCV 를 pykrx 에서 가져와 Yahoo shape 로 반환.

    기본 look-back 5년. ``fill_gaps`` 는 상류와 호환성을 위한 placeholder — KRX
    는 영업일 기준으로 데이터를 반환하므로 공휴일 삽입은 하지 않음 (상류의 Yahoo
    는 주말/공휴일에도 간혹 빈 셀을 끼워 넣어서 gap-fill 이 필요했음).
    """
    del fill_gaps  # KRX 는 영업일 only 이라 gap-fill 불필요
    try:
        as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    except (ValueError, TypeError) as exc:
        raise NoMarketDataError(ticker, ticker, f"invalid as_of_date: {as_of_date!r}") from exc

    start_dt = as_of_dt - relativedelta(years=5)
    start_str = start_dt.strftime("%Y%m%d")
    end_str = as_of_dt.strftime("%Y%m%d")

    from pykrx import stock

    try:
        raw = stock.get_market_ohlcv_by_date(start_str, end_str, ticker)
    except Exception as exc:  # noqa: BLE001 — vendor 에러를 typed 로 전환
        raise NoMarketDataError(ticker, ticker, f"pykrx OHLCV 조회 실패: {exc}") from exc

    frame = _normalize_ohlcv_frame(raw)
    if frame.empty:
        raise NoMarketDataError(ticker, ticker, "no OHLCV rows returned by pykrx")

    # look-ahead 방지. load_ohlcv 가 as_of_date 를 넘기지 않도록 재필터.
    frame = frame[frame["Date"] <= pd.to_datetime(as_of_date)].reset_index(drop=True)
    if frame.empty:
        raise NoMarketDataError(ticker, ticker, f"no OHLCV on or before {as_of_date}")
    return frame


def get_closes(ticker: str, start_date: str, end_date: str) -> pd.Series:
    """``[start_date, end_date)`` 의 일별 종가 (Date 인덱스, Close 값).

    상류 `yahoo.market.get_closes` 와 동일 시그니처. ``end_date`` 는 **배타적**
    (상류 Yahoo 가 end 를 exclusive 로 다루기 때문). 반환이 비면 빈 Series.
    settlement 레이어가 holding window 수익률 계산에 사용.
    """
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return pd.Series(dtype=float)

    # pykrx 는 end 를 inclusive 로 쓰므로 하루 뒤로 밀어서 end_date 자체는 제외.
    pykrx_end = (end_dt - timedelta(days=1)).strftime("%Y%m%d") if end_dt > start_dt else start_dt.strftime("%Y%m%d")

    from pykrx import stock

    try:
        raw = stock.get_market_ohlcv_by_date(start_dt.strftime("%Y%m%d"), pykrx_end, ticker)
    except Exception:  # noqa: BLE001 — settlement 쪽은 ValueError 로 처리
        return pd.Series(dtype=float)
    frame = _normalize_ohlcv_frame(raw)
    if frame.empty or "Close" not in frame.columns:
        return pd.Series(dtype=float)
    series = frame.set_index("Date")["Close"]
    series.name = "Close"
    return series


def get_stock_data(ticker: str, start_date: str, end_date: str) -> str:
    """상류 `get_YFin_data_online` / `alpha_vantage.get_stock` 호환 — 지정 창의
    OHLCV 를 CSV 문자열로 반환.
    """
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except (ValueError, TypeError) as exc:
        raise NoMarketDataError(ticker, ticker, f"invalid date range: {exc}") from exc

    from pykrx import stock

    try:
        raw = stock.get_market_ohlcv_by_date(
            _to_krx_date(start_date), _to_krx_date(end_date), ticker
        )
    except Exception as exc:  # noqa: BLE001
        raise NoMarketDataError(ticker, ticker, f"pykrx OHLCV 조회 실패: {exc}") from exc

    frame = _normalize_ohlcv_frame(raw)
    if frame.empty:
        raise NoMarketDataError(ticker, ticker, f"no rows between {start_date} and {end_date}")

    # Date 컬럼을 YYYY-MM-DD 로 포맷.
    frame["Date"] = frame["Date"].dt.strftime("%Y-%m-%d")
    header = (
        f"# KRX OHLCV for {ticker} from {start_date} to {end_date}\n"
        f"# Total records: {len(frame)}\n\n"
    )
    return header + frame.to_csv(index=False)


# 지원 지표 — stockstats 가 OHLCV 로부터 계산 가능. 상류 Yahoo 와 동일한 셋.
SUPPORTED_INDICATORS: dict[str, str] = {
    "close_50_sma": "50 SMA: 중기 추세 지표. 추세 방향과 동적 지지/저항선 식별에 사용.",
    "close_200_sma": "200 SMA: 장기 추세 벤치마크. 전체 장세 확인 및 골든/데드 크로스 세팅.",
    "close_10_ema": "10 EMA: 단기 모멘텀 반응이 빠른 평균. 빠른 변화 포착.",
    "macd": "MACD: EMA 차로 모멘텀 측정. 교차/다이버전스로 추세 변화 포착.",
    "macds": "MACD Signal: MACD 라인의 EMA 평활. 라인 교차로 매매 신호.",
    "macdh": "MACD Histogram: MACD 와 Signal 의 차. 모멘텀 강도 시각화.",
    "rsi": "RSI: 과매수/과매도 측정 (0-100). 70+ 과매수, 30- 과매도.",
    "boll": "Bollinger 중간선 (20 SMA). 가격의 중심 추세.",
    "boll_ub": "Bollinger 상단 밴드. 과매수 신호.",
    "boll_lb": "Bollinger 하단 밴드. 과매수 신호.",
    "atr": "ATR: 변동성 측정. 포지션 사이징과 손절 거리에 사용.",
}


def _get_stock_stats_bulk(ticker: str, indicator: str, as_of_date: str) -> dict[str, str]:
    """하나의 OHLCV 로드로 지표를 모든 날짜에 대해 계산 → ``{date_str: value}``.

    상류 `yahoo.market._get_stock_stats_bulk` 와 같은 역할.
    """
    data = load_ohlcv(ticker, as_of_date)
    df = wrap(data.copy())
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    df[indicator]  # stockstats 가 lazy 계산을 트리거

    result: dict[str, str] = {}
    for _, row in df.iterrows():
        date_str = row["Date"]
        value = row[indicator]
        result[date_str] = "N/A" if pd.isna(value) else str(value)
    return result


def get_stock_stats_indicators_window(
    ticker: str,
    indicator: str,
    as_of_date: str,
    look_back_days: int,
) -> str:
    """지표 창 (``as_of_date`` 기준 ``look_back_days`` 뒤로) 을 Markdown 문자열로.

    상류 `yahoo.market.get_stock_stats_indicators_window` 호환.
    """
    if indicator not in SUPPORTED_INDICATORS:
        raise ValueError(
            f"Indicator {indicator} is not supported. "
            f"Choose from: {sorted(SUPPORTED_INDICATORS)}"
        )

    try:
        as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    except (ValueError, TypeError) as exc:
        raise NoMarketDataError(ticker, ticker, f"invalid as_of_date: {as_of_date}") from exc

    before = as_of_dt - relativedelta(days=look_back_days)
    indicator_data = _get_stock_stats_bulk(ticker, indicator, as_of_date)

    lines = []
    current = as_of_dt
    while current >= before:
        date_str = current.strftime("%Y-%m-%d")
        value = indicator_data.get(date_str, "N/A: 영업일 아님 (주말/공휴일)")
        lines.append(f"{date_str}: {value}")
        current = current - relativedelta(days=1)

    description = SUPPORTED_INDICATORS[indicator]
    return (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {as_of_date}:\n\n"
        + "\n".join(lines)
        + "\n\n"
        + description
    )


def get_indicator(
    ticker: str,
    indicator: str,
    curr_date: str,
    look_back_days: int = 30,
) -> str:
    """상류 `alpha_vantage.indicator.get_indicator` 호환 — 지표 창을 반환."""
    return get_stock_stats_indicators_window(ticker, indicator, curr_date, look_back_days)


_NO_ESTIMATE_NOTE = " — 수급 데이터 없음. 수급을 추정하거나 언급하지 마세요"


def _fetch_krx_investor_table(ticker: str, start_str: str, end_str: str):
    """KRX 로그인 세션으로 투자자별 거래대금(원) 기간합계 DataFrame 을 가져온다."""
    from pykrx import stock

    from tradingagents.dataflows.vendors import krx_session

    with krx_session.authenticated_pykrx():
        return stock.get_market_trading_value_by_investor(start_str, end_str, ticker)


def get_investor_net_purchases(ticker: str, trade_date: str, look_back_days: int = 5) -> str:
    """최근 ``look_back_days`` 거래일간 외국인·기관 순매수 — KRX 전용 신규 지표.

    1순위 KRX 로그인 세션(원 단위, 투자자 세부 구분) → 실패 시 네이버 증권 매매동향
    (수량, 외국인·기관·개인만) → 둘 다 실패하면 원인을 담은
    ``[KRX 수급 조회 실패: ...]`` 를 반환한다 (#139). 수급은 가격 변동 **선행 지표** 로
    분석가가 활용하되, 조회 실패 시 추정하지 않는다.

    Args:
        ticker: KRX 6자리 종목코드
        trade_date: 분석 기준일 (``YYYY-MM-DD``)
        look_back_days: 거슬러 올라갈 거래일 수 (디폴트 5)

    Returns:
        수급 요약 Markdown 문자열. 로그인 실패 / 데이터 없음 시 사람 읽기 쉬운
        안내 문자열 (분석가 run 중단 방지).
    """
    try:
        as_of_dt = datetime.strptime(trade_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return f"[KRX 수급 조회 실패: 잘못된 날짜 형식 {trade_date!r}]"

    start_dt = _window_start(as_of_dt, look_back_days)
    start_str = start_dt.strftime("%Y%m%d")
    end_str = as_of_dt.strftime("%Y%m%d")

    krx_error: str
    try:
        df = _fetch_krx_investor_table(ticker, start_str, end_str)
    except Exception as exc:  # noqa: BLE001 — 로그인·네트워크·파서 실패 모두 폴백 대상
        krx_error = _diagnose_investor_failure(exc)
        logger.warning("KRX 수급 조회 실패 (%s): %s", ticker, krx_error)
    else:
        if df is None or (hasattr(df, "empty") and df.empty):
            return "최근 수급 데이터가 없습니다."
        # 투자자별 순매수만 추출. 컬럼: 매도/매수/순매수 — 순매수 열만 사용.
        try:
            series = df["순매수"] if "순매수" in df.columns else df.iloc[:, -1]
            header = (
                f"**{trade_date} 기준 최근 {look_back_days} 거래일 순매수** "
                f"({start_dt:%Y-%m-%d} ~ {trade_date}, 단위: 원, 출처: KRX)\n\n"
            )
            return header + series.to_markdown()
        except Exception as exc:  # noqa: BLE001
            krx_error = f"포맷 실패: {exc}"

    from tradingagents.dataflows.errors import VendorError
    from tradingagents.dataflows.vendors.naver_investor import get_investor_flow

    try:
        return get_investor_flow(ticker, trade_date, look_back_days)
    except VendorError as exc:
        return (
            f"[KRX 수급 조회 실패: KRX: {krx_error}; 네이버 증권: {exc}{_NO_ESTIMATE_NOTE}]"
        )


_SNAPSHOT_INDICATORS: tuple[str, ...] = (
    "close_10_ema", "close_50_sma", "close_200_sma",
    "rsi", "boll", "boll_ub", "boll_lb",
    "macd", "macds", "macdh", "atr",
)


def _fmt(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def build_market_snapshot(
    ticker: str,
    as_of_date: str,
    look_back_days: int = 30,
) -> str:
    """상류 `yahoo.snapshot.build_verified_market_snapshot` 호환 — 검증용 스냅샷.

    최신 OHLCV 행 + 11개 지표 + 최근 종가 창을 Markdown 으로 렌더링. 분석가가
    정확한 숫자 (가격 레벨, 지표 값) 를 인용할 때 참조하는 ground truth.
    """
    try:
        frame = load_ohlcv(ticker, as_of_date, fill_gaps=False)
    except NoMarketDataError:
        raise

    stock_df = wrap(frame.copy())
    indicator_values: dict[str, str] = {}
    for name in _SNAPSHOT_INDICATORS:
        try:
            stock_df[name]
            indicator_values[name] = _fmt(stock_df.iloc[-1][name])
        except Exception as exc:  # noqa: BLE001 — 지표 하나 실패해도 전체 유지
            indicator_values[name] = f"N/A ({type(exc).__name__})"

    latest = frame.iloc[-1]
    latest_date = _fmt(latest["Date"])
    window = max(1, min(int(look_back_days), 30))
    recent = frame.tail(window)

    lines = [
        f"## 검증 시장 데이터 스냅샷 — {ticker}",
        "",
        f"- 요청 분석일: {as_of_date}",
        f"- 사용된 최근 거래일: {latest_date}",
        "- 요청 분석일 이후 행은 검증 전 제외됨.",
        "",
        "### 최근 검증 OHLCV",
        "",
        "| 항목 | 값 |",
        "|---|---:|",
    ]
    for field in ("Open", "High", "Low", "Close", "Volume"):
        lines.append(f"| {field} | {_fmt(latest.get(field))} |")

    lines += ["", "### 검증 기술지표 (최근 행 기준)", "",
              "| 지표 | 값 |", "|---|---:|"]
    for name, value in indicator_values.items():
        lines.append(f"| {name} | {value} |")

    lines += ["", f"### 최근 검증 종가 ({len(recent)}일)", "",
              "| 날짜 | 종가 |", "|---|---:|"]
    for _, row in recent.iterrows():
        lines.append(f"| {_fmt(row['Date'])} | {_fmt(row.get('Close'))} |")

    lines += [
        "",
        "이 스냅샷을 정확한 OHLCV, 가격 레벨, 지표 값 주장의 ground truth 로 "
        "사용하세요. 다른 도구 출력과 상충하면 임의로 조정하지 말고 불일치를 "
        "지적하세요. 구체적 날짜·가격을 포함한 도구 출력이 뒷받침하지 않는 "
        "역사적 검증, 지지/저항 반등, 정확한 변동률 주장은 하지 마세요.",
    ]
    return "\n".join(lines)
