# [#55 #56] Task 6d/6e: 레거시 Yahoo / Alpha Vantage vendor 삭제 + symbols.py 정리

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/55 (6d), https://github.com/timonPark/TradingAgents-KR/issues/56 (6e)
- PR: (작업 완료 후 추가)
- 상위 에픽: #51
- 브랜치: `feat/55-56-legacy-vendor-cleanup`
- 작업 기간: 2026-11-03 ~

## 범위

Task 6a-c (#52/#53/#54) 로 가격·지표·수급이 pykrx 로 전환되었고 DART (Task 5)
가 fundamentals 를 서브. 이제 라우팅이 참조하지 않는 레거시 vendor 파일과
테스트를 전면 삭제. 6d (symbols.py 정리) 와 6e (vendor 디렉터리 삭제) 를
하나의 PR 로 통합 — `normalize_symbol` 은 Yahoo 가 소비자였으므로 Yahoo 삭제
후에만 안전하게 제거 가능.

## 전략: 뉴스는 Task 7 로 유예

code_artifact.md 는 Yahoo/Alpha Vantage 디렉터리 전체 삭제를 명시하지만, 뉴스
서브모듈 (`yahoo/news.py`, `alpha_vantage/news.py`) 은 Task 7 이 네이버뉴스로
교체 예정. 중간 상태에서 `get_news` / `get_global_news` 가 깨지는 걸 막기 위해
**news.py 와 공유 `common.py` 는 유지**, 가격·지표·스냅샷 파일만 삭제.

## 수행한 변경

### 신규: pykrx vendor 확장

`tradingagents/dataflows/vendors/pykrx.py`
- `get_closes(ticker, start_date, end_date)` 신규 — 상류 `yahoo.market.get_closes`
  와 같은 shape (Date 인덱스, Close 값의 Series). `end_date` 는 exclusive. settlement
  레이어가 holding window 수익률 계산에 사용.

### 삭제: 레거시 vendor 소스

- `tradingagents/dataflows/vendors/yahoo/market.py`
- `tradingagents/dataflows/vendors/yahoo/ohlcv.py`
- `tradingagents/dataflows/vendors/yahoo/snapshot.py`
- `tradingagents/dataflows/vendors/alpha_vantage/stock.py`
- `tradingagents/dataflows/vendors/alpha_vantage/indicator.py`

### 축소: 뉴스 서브모듈만 유지

- `yahoo/common.py` — `yf_retry` + `_answered_empty` 만 남기고 `price_text`,
  `raise_for_empty`, `vendor_reachable` 사용 등 삭제. Task 7 전까지 news.py 가 쓰는
  최소 기능만 유지.
- `yahoo/news.py` — `normalize_symbol` import 를 인라인 `strip().upper()` 로 교체.
- `alpha_vantage/__init__.py` — `get_indicator`, `get_stock` 재노출 삭제. news 만.

### `tradingagents/dataflows/symbols.py`

- `normalize_symbol` 함수 **삭제** — 유일 소비자 (`yahoo/market.py`, `yahoo/ohlcv.py`,
  `yahoo/snapshot.py`, `yahoo/news.py`) 가 전부 사라졌거나 인라인화됨.
- 모듈 docstring 업데이트: 삭제된 로직 목록에 `normalize_symbol` 추가, 공개 함수
  섹션으로 재구성.

### `tradingagents/memory/settlement.py`

- `get_closes` import 를 `yahoo.market` → `vendors.pykrx` 로 전환.

### `tradingagents/default_config.py`

- `benchmark_map` 을 다국적 접미사 매핑 20여 개 → `{"": "069500"}` 단일로 축소.
  KRX-only 포크의 기본 벤치마크는 KODEX 200 ETF.
- 관련 주석 업데이트.

### 테스트 전면 삭제

- `tests/test_yfinance_stale_ohlcv_guard.py`
- `tests/test_ohlcv_cache_freshness.py`
- `tests/test_ohlcv_date_column.py`
- `tests/test_ohlcv_latest_bar.py`
- `tests/test_date_boundaries.py`

### 테스트 부분 수정

- `tests/test_cache_writes.py` — Yahoo OHLCV 캐시 테스트 1건 삭제, pandas 미사용 import 정리.
- `tests/test_no_data_handling.py` — Yahoo cache-poisoning 테스트 `TestLoadOhlcvNoPoison`
  클래스 전체 삭제. module docstring 에 "pykrx 는 영속 OHLCV 캐시 없음" 노트 추가.
- `tests/test_memory_log.py`:
  - `_pykrx_ohlcv` 헬퍼 추가 — 한국어 컬럼 DataFrame 반환.
  - 6개 fetch_returns 테스트: `yfinance.Ticker` patch → `pykrx.stock.get_market_ohlcv_by_date` patch,
    티커 `NVDA/SPY` → `005930/069500` 로 교체.
  - `test_resolve_benchmark_explicit_override` — 벤치마크 override 를 KRX 티커 (`229200`
    KODEX 코스닥 150) 로.
  - 통합: `test_resolve_benchmark_default_is_kodex_200` 신규 추가 (DEFAULT_CONFIG 가
    `069500` 반환하는지).
  - 삭제: `test_resolve_benchmark_suffix_map`, `_brazil`, `_regional_indexes`,
    `_us_ticker_defaults_to_spy`, `_unknown_suffix_falls_back`, `_case_insensitive`
    — 전부 다국적 접미사 매핑 테스트.
  - `test_a_longer_window_asks_for_enough_price_history` — yahoo.market patch →
    pykrx.stock patch.

## 설계 결정 변경 사항

### `yahoo/news.py` + `alpha_vantage/news.py` 보존 전략

code_artifact.md Task 6 는 Yahoo/AV 디렉터리 전체 삭제를 명시하지만, 뉴스 서브모듈이
사라지면 `get_news` / `get_global_news` 라우팅이 **중간 상태에서 깨짐**. 네이버뉴스
전환 (Task 7) 전까지 가용성 유지를 위해 news.py 와 그 의존성 (`common.py` 의
`yf_retry` / Alpha Vantage `_make_api_request` 등) 만 유지.

이 결정은 code_artifact.md Task 6 와 완벽히 일치하지는 않지만, Task 7 가 뉴스 vendor
를 완전히 교체할 때 Yahoo/AV news.py 와 common.py 를 함께 삭제하면 결과적으로 동일한
최종 상태에 도달.

### `benchmark_map` 단일 엔트리로 축소

code_artifact.md 는 benchmark 변경을 명시하지 않지만, KR-only 포크에서 다국적 접미사
매핑은 의미가 없음. Yahoo `.KS`/`.KQ` 접미사도 pykrx 환경에서는 사용되지 않음 (KRX
는 6자리 숫자만). 디폴트 `benchmark_ticker=None` 유지 + `benchmark_map={"": "069500"}`
로 모든 KRX 티커가 KODEX 200 ETF 대비 alpha 측정. 사용자가 코스닥 전용 비교를 원하면
`benchmark_ticker="229200"` 로 override 가능.

### `pykrx.get_closes` end_date exclusive 규약

상류 `yahoo.market.get_closes` 는 `end` 를 exclusive 로 다룸 (yfinance 동작과 동일).
pykrx 는 end 를 inclusive 로 쓰므로 vendor 레이어에서 `end_date - 1` 로 변환해
settlement 가 동일 규약으로 호출할 수 있도록. settlement 는 변경 없음.

## 검증 결과

- `pytest -q` 전체 → **870 passed, 8 subtests passed** (삭제된 51개 테스트 반영)
- `ruff check tradingagents cli tests` → **All checks passed**

## 다음 작업 핸드오프

### Task 6 에픽 (#51) 종결

이 PR 머지 후 Task 6 전체 close 가능:
- #52 (6a) ✅ pykrx vendor 신규 작성 — 머지됨 (PR #57)
- #53 (6b) ✅ router 를 pykrx 로 전환 — 머지됨 (PR #58)
- #54 (6c) ✅ market_analyst 사전조회에 수급 섹션 추가 — 머지됨 (PR #59)
- #55 (6d) + #56 (6e) 🟡 **이 PR** — 레거시 vendor 삭제 + symbols.py 정리

### Task 7 (#?): 네이버뉴스 + ECOS 로 뉴스/거시 교체

이 때 완전히 삭제될 파일:
- `tradingagents/dataflows/vendors/yahoo/` 디렉터리 (news.py + common.py + __init__.py)
- `tradingagents/dataflows/vendors/alpha_vantage/` 디렉터리 (news.py + common.py + __init__.py)
- `tradingagents/dataflows/vendors/reddit.py`
- `tradingagents/dataflows/vendors/stocktwits.py`
- `tradingagents/dataflows/vendors/fred.py`
- `tradingagents/dataflows/vendors/polymarket.py`
- `tradingagents/dataflows/symbols.py` 의 `crypto_base` 스텁 (reddit/stocktwits 삭제 후)

신규:
- `tradingagents/dataflows/vendors/naver_news.py`
- `tradingagents/dataflows/vendors/ecos.py`

