# [#52] Task 6a: vendors/pykrx.py 신규 작성 (OHLCV + 기술지표 + 투자자별 수급)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/52
- PR: (작업 완료 후 추가)
- 상위 에픽: #51
- 브랜치: `feat/52-pykrx-vendor`
- 작업 기간: 2026-11-03 ~

## 범위

Yahoo Finance + Alpha Vantage 가격·기술지표 vendor 를 KRX 전용 pykrx 로 교체.
Task 6a 는 vendor 모듈 신규 작성만 담당. router 연결과 레거시 vendor 삭제는
Task 6b/6e 로 분산.

## 수행한 변경

### `pyproject.toml`

- `pykrx>=1.0.49` 의존성 추가.
- 주석에 pandas 호환성 노트: pykrx 1.2.x 는 `pandas<3.0` 선언하지만 OHLCV
  경로는 pandas 3.x 와 호환 (의존성 리졸버 경고 1건, 실행 영향 없음).

### `tradingagents/dataflows/vendors/pykrx.py` 신규

**모듈 수준:**
- `_check_krx_credentials()` — `KRX_ID`/`KRX_PW` 환경변수 확인. 수급 API 가
  로그인 요구. OHLCV 는 keyless.
- `_to_krx_date()` — `YYYY-MM-DD` → `YYYYMMDD` 변환.
- `_PYKRX_COLUMN_MAP` — 한국어 → 영어 OHLCV 컬럼 매핑 (시가→Open 등).
- `_normalize_ohlcv_frame()` — pykrx DataFrame 을 상류 `yahoo.ohlcv.load_ohlcv`
  shape (Date 컬럼, 영어 OHLCV, 오름차순) 로 변환.
- `SUPPORTED_INDICATORS` — stockstats 로 계산 가능한 11개 지표 매핑 (close_10_ema,
  close_50_sma, close_200_sma, rsi, boll, boll_ub, boll_lb, macd, macds, macdh,
  atr) + 한국어 설명.

**공개 함수 (상류 vendor shape 호환):**
- `load_ohlcv(ticker, as_of_date, fill_gaps=True)` — 5년 look-back, as_of_date
  이후 행 제거. 상류 `yahoo.ohlcv.load_ohlcv` 와 동등. `fill_gaps` 는 KRX 영업일
  only 이라 unused (placeholder).
- `get_stock_data(ticker, start_date, end_date)` — 지정 창 OHLCV 를 CSV 문자열로.
  상류 `yahoo.market.get_YFin_data_online` / `alpha_vantage.stock.get_stock` 와 동등.
- `get_indicator(ticker, indicator, curr_date, look_back_days=30)` — 상류
  `alpha_vantage.indicator.get_indicator` 호환.
- `get_stock_stats_indicators_window(ticker, indicator, as_of_date, look_back_days)` —
  상류 `yahoo.market.get_stock_stats_indicators_window` 호환. 영업일 아닌 날짜는
  "N/A: 영업일 아님 (주말/공휴일)" 로 표시.
- `get_investor_net_purchases(ticker, trade_date, look_back_days=5)` — **KRX 전용
  신규 지표**. 투자자별 (외국인/기관/개인) 순매수 요약. 로그인 자격증명 없음 또는
  vendor 에러 시 fail-safe 문자열 반환 (분석가 run 중단 방지).
- `build_market_snapshot(ticker, as_of_date, look_back_days=30)` — 상류
  `yahoo.snapshot.build_verified_market_snapshot` 와 같은 역할. 한국어 섹션 헤더.

### `tests/test_pykrx_vendor.py` 신규

**15개 테스트**, 전부 `pykrx.stock` 함수를 `patch` 로 모킹 (네트워크 호출 없음):
- `get_stock_data` CSV 렌더링 / 날짜 포맷 오류 / empty 처리
- `load_ohlcv` as_of_date 필터링 (look-ahead 방지) / 잘못된 날짜 / empty
- `get_indicator` 지원 지표만 수용 / 지표 창 렌더링
- 영업일 아닌 날짜에 "N/A" 마커
- `get_investor_net_purchases` 자격증명 없음 fail-safe / 포맷 / 잘못된 날짜 /
  vendor 에러 / empty
- `build_market_snapshot` 11개 지표 + 종가 창 포함 확인

## 설계 결정 변경 사항

### 수급 데이터 shape 선택

code_artifact.md Task 6 은 "외국인/기관 5거래일 순매수" 명시. pykrx 는 두 API 제공:
- `get_market_net_purchases_of_equities_by_ticker` — 종목 리스트에 대한 순매수
- `get_market_trading_value_by_investor` — 특정 종목에 대한 투자자별 거래대금/순매수

**후자를 선택** — 단일 종목 분석에 더 자연스럽고 투자자 분류 (외국인/기관/개인)
가 명시적. 전자는 종목 간 비교에 적합한데 분석가 workflow 와 거리가 있음.

### 로그인 요구 vs keyless 분리

OHLCV 는 keyless 로 즉시 동작, 수급은 KRX_ID/KRX_PW 로그인 필요 → vendor 시작부
에 서로 다른 fail 모드 명시. 수급 호출만 `_check_krx_credentials()` 로 가드.
OHLCV 는 자격증명 체크 생략 (CI 와 로컬 개발 모두 바로 동작).

### pandas 3.x vs pykrx 선언 상충

pykrx 1.2.x 는 `pandas<3.0` 을 선언하지만 OHLCV 경로는 3.x 와 동작 확인됨 (실제
smoke 로 005930 OHLCV 가 정상 반환). 프로젝트 전체는 pandas 3+ 를 요구하므로
pykrx 선언을 믿지 않고 유지. 의존성 리졸버가 설치 시 경고를 띄우지만 기능상 문제
없음.

## 검증 결과

- `pytest tests/test_pykrx_vendor.py -v` → **15 passed**
- `pytest -q` 전체 → **937 passed, 8 subtests passed** (pykrx 테스트 15개 추가 반영)
- `ruff check tradingagents cli tests` → **All checks passed**
- Smoke test (실제 pykrx 호출):
  ```python
  pykrx.get_stock_data("005930", "2025-01-02", "2025-01-10")
  # → '# KRX OHLCV for 005930 ... 2025-01-02,52700,53600,...'
  ```

실제 네트워크 통합 테스트 (수급 포함) 는 Task 11 로 분산.

## 다음 작업 핸드오프

### Task 6b (#53): router + default_config 전환
- `router.py`: `get_stock_data`/`get_indicators` 를 pykrx 단일 vendor 로
- `get_investor_net_purchases` 분기 신규 등록 (KRX 전용)
- `default_config.py`: `data_vendors.core_stock_apis`, `technical_indicators` 를 `"pykrx"` 로

### Task 6c (#54): market_analyst 사전조회 확장
- `_prefetch_market_data` 에 수급 호출 추가
- 프롬프트에 "외국인/기관 N 거래일 순매수" 섹션

### Task 6e (#56): 레거시 yahoo/av 디렉터리 전면 삭제
- `vendors/yahoo/`, `vendors/alpha_vantage/` 디렉터리 삭제
- 관련 테스트 (`test_alpha_vantage_*`, `test_yahoo_*`) 삭제
- news 분기는 Task 7 로 네이버뉴스 전환 전까지 임시 조치 필요

