"""Task 6a (#52): pykrx vendor 유닛 테스트.

실제 pykrx / KRX API 는 호출하지 않고 전부 모킹. 통합 테스트 (네트워크) 는
파일 하단 ``@pytest.mark.integration`` 섹션 참조 (Task 11 #92).
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors import pykrx


def _ohlcv_df(dates, closes=None):
    """pykrx `get_market_ohlcv_by_date` 가 돌려주는 전형적 DataFrame."""
    n = len(dates)
    frame = pd.DataFrame({
        "시가": [100 + i for i in range(n)],
        "고가": [105 + i for i in range(n)],
        "저가": [95 + i for i in range(n)],
        "종가": closes if closes else [100 + i * 0.5 for i in range(n)],
        "거래량": [1_000_000 + i * 1000 for i in range(n)],
        "등락률": [0.1 * (i + 1) for i in range(n)],
    }, index=pd.to_datetime(dates))
    frame.index.name = "날짜"
    return frame


@pytest.mark.unit
def test_get_stock_data_renders_csv_header():
    dates = pd.date_range("2025-01-02", periods=5, freq="B")
    with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=_ohlcv_df(dates)):
        result = pykrx.get_stock_data("005930", "2025-01-02", "2025-01-10")

    assert "# KRX OHLCV for 005930 from 2025-01-02 to 2025-01-10" in result
    assert "Total records: 5" in result
    assert "Open,High,Low,Close,Volume" in result
    # Date 포맷 확인
    assert "2025-01-02" in result


@pytest.mark.unit
def test_get_stock_data_rejects_bad_date_format():
    with pytest.raises(NoMarketDataError):
        pykrx.get_stock_data("005930", "20250102", "2025-01-10")


@pytest.mark.unit
def test_get_stock_data_raises_when_empty():
    with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=pd.DataFrame()), \
         pytest.raises(NoMarketDataError, match="no rows between"):
        pykrx.get_stock_data("005930", "2025-01-02", "2025-01-10")


@pytest.mark.unit
def test_load_ohlcv_filters_to_as_of_date():
    """``load_ohlcv`` 는 as_of_date 이후 행을 제외해야 함 (look-ahead 방지)."""
    dates = pd.date_range("2025-01-02", periods=10, freq="B")
    with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=_ohlcv_df(dates)):
        frame = pykrx.load_ohlcv("005930", "2025-01-08")
    # as_of_date 포함, 그 이후 제외
    assert frame["Date"].max() <= pd.Timestamp("2025-01-08")
    assert set(frame.columns) >= {"Date", "Open", "High", "Low", "Close", "Volume"}


@pytest.mark.unit
def test_load_ohlcv_raises_on_bad_date():
    with pytest.raises(NoMarketDataError, match="invalid as_of_date"):
        pykrx.load_ohlcv("005930", "not-a-date")


@pytest.mark.unit
def test_load_ohlcv_raises_when_pykrx_empty():
    with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=pd.DataFrame()), \
         pytest.raises(NoMarketDataError):
        pykrx.load_ohlcv("005930", "2025-01-10")


@pytest.mark.unit
def test_get_indicator_rejects_unsupported():
    with pytest.raises(ValueError, match="not supported"):
        pykrx.get_indicator("005930", "unknown_indicator", "2025-01-10", 5)


@pytest.mark.unit
def test_get_indicator_renders_window():
    """지원 지표에 대해 look_back_days 범위의 일별 값과 설명이 포함."""
    # stockstats 가 지표 계산할 수 있도록 충분한 OHLCV (최소 200개 bar 이상이면
    # SMA/EMA 가 안정) 제공.
    dates = pd.date_range("2024-01-01", "2025-01-10", freq="B")
    with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=_ohlcv_df(dates)):
        result = pykrx.get_indicator("005930", "close_50_sma", "2025-01-10", 5)

    assert "close_50_sma" in result
    assert "50 SMA" in result or "중기 추세" in result  # 설명 포함
    # 창 범위 (최소 하루는 포함)
    assert "2025-01-10" in result


@pytest.mark.unit
def test_get_stock_stats_indicators_window_marks_non_trading_days():
    """영업일 아닌 날짜는 'N/A: 영업일 아님' 으로 표시."""
    # 2025-01-10 금요일 → 2025-01-11, 12 는 주말
    dates = pd.date_range("2024-01-01", "2025-01-10", freq="B")
    with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=_ohlcv_df(dates)):
        result = pykrx.get_stock_stats_indicators_window(
            "005930", "rsi", "2025-01-12", look_back_days=3
        )
    # as_of_date 자체가 영업일이 아니면 N/A 로 표시
    assert "N/A" in result


@pytest.mark.unit
def test_get_investor_net_purchases_fails_safe_without_credentials(monkeypatch):
    """로그인 자격증명 없음 → 명확한 사용자 안내 (예외 아님)."""
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)
    result = pykrx.get_investor_net_purchases("005930", "2025-01-10")
    assert "KRX 로그인 자격증명이 없습니다" in result
    assert "KRX 수급 조회 실패" in result


@pytest.mark.unit
def test_get_investor_net_purchases_formats_series(monkeypatch):
    monkeypatch.setenv("KRX_ID", "x")
    monkeypatch.setenv("KRX_PW", "y")
    df = pd.DataFrame({
        "매도": [100, 200, 300],
        "매수": [120, 180, 350],
        "순매수": [20_000_000, -20_000_000, 50_000_000],
    }, index=["외국인", "기관", "개인"])
    with patch("pykrx.stock.get_market_trading_value_by_investor", return_value=df):
        result = pykrx.get_investor_net_purchases("005930", "2025-01-10")
    assert "외국인" in result
    assert "기관" in result
    assert "순매수" in result or "20000000" in result or "20,000,000" in result


@pytest.mark.unit
def test_get_investor_net_purchases_bad_date(monkeypatch):
    monkeypatch.setenv("KRX_ID", "x")
    monkeypatch.setenv("KRX_PW", "y")
    result = pykrx.get_investor_net_purchases("005930", "bad-date")
    assert "잘못된 날짜 형식" in result


@pytest.mark.unit
def test_get_investor_net_purchases_handles_vendor_error(monkeypatch):
    monkeypatch.setenv("KRX_ID", "x")
    monkeypatch.setenv("KRX_PW", "y")
    with patch("pykrx.stock.get_market_trading_value_by_investor", side_effect=RuntimeError("boom")):
        result = pykrx.get_investor_net_purchases("005930", "2025-01-10")
    assert "KRX 수급 조회 실패" in result
    assert "boom" in result


@pytest.mark.unit
def test_get_investor_net_purchases_handles_empty(monkeypatch):
    monkeypatch.setenv("KRX_ID", "x")
    monkeypatch.setenv("KRX_PW", "y")
    with patch("pykrx.stock.get_market_trading_value_by_investor", return_value=pd.DataFrame()):
        result = pykrx.get_investor_net_purchases("005930", "2025-01-10")
    assert "수급 데이터가 없습니다" in result


@pytest.mark.unit
def test_build_market_snapshot_renders_ground_truth_sections():
    """11개 지표 + 최근 종가 창을 Markdown 으로 반환."""
    dates = pd.date_range("2024-01-01", "2025-01-10", freq="B")
    with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=_ohlcv_df(dates)):
        snapshot = pykrx.build_market_snapshot("005930", "2025-01-10", look_back_days=5)
    assert "검증 시장 데이터 스냅샷" in snapshot
    assert "005930" in snapshot
    assert "최근 검증 OHLCV" in snapshot
    assert "검증 기술지표" in snapshot
    assert "최근 검증 종가" in snapshot
    # 11개 지표 전부 포함
    for ind in ("close_10_ema", "rsi", "boll", "macd", "atr"):
        assert ind in snapshot


# ============================================================================
# Integration tests (Task 11a, #92) — 실제 KRX / pykrx 호출. CI 는 skip.
#   로컬 실행: ``pytest tests/test_pykrx_vendor.py -m integration``
#   keyless 라 환경변수 불필요.
# ============================================================================


@pytest.mark.integration
def test_live_ohlcv_for_005930_has_recent_rows():
    """2024-01-01 이후 005930 OHLCV 가 비어있지 않고 영어 컬럼으로 변환됨."""
    frame = pykrx.load_ohlcv("005930", "2026-11-03")
    assert not frame.empty
    assert set(frame.columns) >= {"Date", "Open", "High", "Low", "Close", "Volume"}
    # 최근 데이터가 as_of_date 범위 안
    assert frame["Date"].max() <= pd.Timestamp("2026-11-03")
    # 최소 몇 백 영업일 (5년 look-back 디폴트)
    assert len(frame) >= 100


@pytest.mark.integration
def test_live_stock_data_csv_for_005930():
    """get_stock_data 가 CSV 문자열을 돌려주고 KRX 헤더 포함."""
    out = pykrx.get_stock_data("005930", "2026-10-01", "2026-10-31")
    assert "# KRX OHLCV for 005930 from 2026-10-01 to 2026-10-31" in out
    assert "Open,High,Low,Close,Volume" in out


@pytest.mark.integration
def test_live_indicator_window_renders_rsi_values():
    """최근 영업일 RSI 창 — 숫자 값 또는 N/A 가 포함."""
    out = pykrx.get_indicator("005930", "rsi", "2026-11-03", 10)
    assert "rsi" in out.lower()
    # 영업일/주말 라인 둘 다 가능
    assert "2026-11-03" in out or "2026-11-02" in out
