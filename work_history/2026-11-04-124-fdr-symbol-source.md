# [#124] 긴급 fix: 종목 검색 데이터 소스 pykrx → FinanceDataReader

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/124
- 상위: Task 14a (#106) 후속 핫픽스
- 브랜치: `fix/124-fdr-symbol-source`
- 작업 기간: 2026-11-04

## 증상

로컬 웹 UI (또는 CLI) 에서 종목 검색 시 **"검색 결과 없음"** 만 반환.

## 원인

`pykrx.stock.get_market_ticker_list` / `get_market_ticker_name` 이 KRX 사이트 변경으로 깨진 상태. OHLCV 같은 다른 pykrx 함수는 정상.

- `get_market_ticker_list(...)` → `[]`
- `get_market_ticker_name('005930')` → **`Empty DataFrame`** (str 대신 DataFrame 반환)

그리고 **빈 리스트가 캐시 파일에 `[]` 로 저장**돼서 pykrx 가 고쳐지더라도 하루 동안 검색이 계속 실패.

## 수정

### 1) `tradingagents/dataflows/krx_symbol_search.py`

- 데이터 소스를 **`FinanceDataReader`** (`fdr.StockListing('KRX')`) 로 교체
  - KRX 전종목 (2876건) 을 `Code`, `Name`, `Market` 컬럼으로 반환
  - `Market` 에서 `KOSPI` / `KOSDAQ` 만 필터 (`KONEX` 제외 — Task 14a 범위와 동일)
- 내부 함수 `_fetch_from_pykrx` → **`_fetch_tickers`** 로 리네임 (data source 중립)
- `_load_all` 에 **빈 결과 가드** 추가: fetch 가 0건이면 캐시 저장하지 않고 다음 호출에서 재시도

### 2) `pyproject.toml`

- `dependencies` 에 `finance-datareader>=0.9` 추가 — CLI 와 웹 양쪽에서 필요한 코어 종속성 (web extra 아님)

### 3) `tests/test_krx_symbol_search.py`

- monkeypatch 대상을 `_fetch_from_pykrx` → `_fetch_tickers` 로 리네임
- 빈 결과가 캐시에 **저장되지 않는지** 검증하는 테스트 추가

## 사용자 즉시 조치 (PR 머지 전)

```bash
rm ~/.tradingagents/cache/krx_tickers_*.json      # 빈 캐시 제거
```

## 검증 결과

- `pytest tests/test_krx_symbol_search.py -v` → **19 passed** (기존 17 + 신규 2: 빈 결과 캐시 가드)
- `pytest -q` 전수 → **906 passed, 11 deselected** (회귀 없음, 893→906)
- `ruff check .` → clean
- 라이브 smoke: `list_all()` → **2719 tickers** (1.6초), `search("삼성", limit=5)` → **5 hits** (삼성E&A, 삼성FN리츠, 삼성SDI, 삼성SDI우, 삼성공조)
