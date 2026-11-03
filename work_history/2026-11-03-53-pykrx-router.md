# [#53] Task 6b: router + default_config 를 pykrx 로 전환

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/53
- PR: (작업 완료 후 추가)
- 상위 에픽: #51
- 브랜치: `feat/53-pykrx-router`
- 작업 기간: 2026-11-03 ~

## 범위

Task 6a (#52, PR #57) 에서 작성한 `vendors/pykrx.py` 를 router 에 연결.
`core_stock_apis`, `technical_indicators` 범주를 pykrx 단일 vendor 로 축소하고,
`get_investor_net_purchases` (KRX 전용 수급) 분기 신규 등록. 레거시 Yahoo/AV
vendor 는 아직 import 는 유지 (Task 6e 에서 삭제). news 와 verified snapshot 은
라우팅만 전환.

## 수행한 변경

### `tradingagents/dataflows/router.py`

- `TOOLS_CATEGORIES["core_stock_apis"]` 설명 업데이트 + `get_investor_net_purchases` 추가 (KRX 전용 신규 지표).
- `VENDOR_METHODS` 재편:
  - `get_stock_data` 분기 → `{"pykrx": get_pykrx_stock_data}` 단일로.
  - `get_indicators` 분기 → `{"pykrx": get_pykrx_indicators_window}` 단일로.
  - `get_investor_net_purchases` 분기 신규 등록 → `{"pykrx": get_pykrx_investor_net_purchases}`.
- 레거시 Yahoo/AV import 정리: `get_alpha_vantage_stock`, `get_alpha_vantage_indicator`, `get_YFin_data_online`, `get_stock_stats_indicators_window` 제거.

### `tradingagents/agents/tools.py`

- `get_investor_net_purchases` `@tool` 신규 노출 — ticker/trade_date InjectedState, look_back_days 기본 5.
- `build_verified_market_snapshot` import 를 `vendors.yahoo.snapshot` → `vendors.pykrx` 로 전환 (alias `build_market_snapshot as build_verified_market_snapshot`).

### `tradingagents/default_config.py`

- `data_vendors.core_stock_apis`: `"yfinance"` → `"pykrx"`
- `data_vendors.technical_indicators`: `"yfinance"` → `"pykrx"`

### 테스트 수정 / 삭제

- `tests/test_yahoo_snapshot.py` **삭제** — 전부 Yahoo 전용. pykrx snapshot 커버리지는 `test_pykrx_vendor.py::test_build_market_snapshot_renders_ground_truth_sections` 가 담당.
- `tests/test_dataflows_config.py` — `core_stock_apis` 기본값 검증을 `"pykrx"` 로, `technical_indicators` 기본값 검증을 `"pykrx"` 로.
- `tests/test_no_data_handling.py` — 두 센티넬 테스트를 하나로 통합. 멀티 vendor fallback 패턴이 pykrx 단일 vendor 환경에서 사라졌으므로 단일 vendor 가 NoMarketDataError 를 던지는 경우만 테스트.
- `tests/test_graph_end_to_end.py` —
  - import 를 `yahoo.market/snapshot` → `vendors.pykrx` 로.
  - `offline` fixture 의 `load_ohlcv` 를 pykrx vendor 에서 patch.
  - Yahoo identity resolution patch 제거 (Task 5b 에서 context 가 DART 로 전환됨).
  - `test_a_streamed_run_reads_its_own_graph_config` 의 vendor 이름 `yfinance` → `pykrx`.

## 설계 결정 변경 사항

### Verified snapshot alias 전환

`get_verified_market_snapshot` 는 분석가가 가격/지표 정확성 검증에 쓰는 도구. Task 6a 에서 pykrx 쪽에 `build_market_snapshot` 를 Yahoo snapshot 과 같은 shape 로 작성해 두었음. tools.py 가 함수 이름까지 바꾸면 분석가 프롬프트 참조도 바꿔야 해서 **import alias 로 이름 유지** (`build_market_snapshot as build_verified_market_snapshot`). 분석가 쪽은 변경 없이 pykrx snapshot 을 받게 됨.

### `get_investor_net_purchases` 를 core_stock_apis 범주에 배치

code_artifact.md Task 6 는 "분석 컨텍스트에 포함" 만 명시. 수급은 가격 변동 선행 지표라 가격 vendor 와 같은 범주 (`core_stock_apis`) 에 두는 게 자연스러움. `fundamental_data` 는 재무/공시 범주 (DART), `news_data` 는 뉴스 범주라 둘 다 수급의 정체성과 맞지 않음.

### Yahoo snapshot 테스트 삭제 범위

Task 6e (레거시 vendor 삭제) 가 명시적으로 테스트 삭제를 다루지만, 라우팅 전환 (Task 6b) 시점에 이미 Yahoo snapshot 코드 경로가 끊겼음. snapshot 커버리지는 `test_pykrx_vendor.py` 가 담당하므로 중복 테스트 제거.

## 검증 결과

- `pytest -q` 전체 → **921 passed, 8 subtests passed**
- `ruff check tradingagents cli tests` → **All checks passed**

## 다음 작업 핸드오프

### Task 6c (#54): market_analyst 사전조회에 수급 섹션 추가
- `_prefetch_market_data` 에 `get_investor_net_purchases` 호출 추가
- `_render_prefetched` 에 "외국인/기관 N 거래일 순매수" 섹션 추가

### Task 6d (#55): symbols.py Yahoo 심볼 변환 잔재 정리
### Task 6e (#56): 레거시 yahoo/av 디렉터리 + 테스트 전면 삭제
- `vendors/yahoo/` 전체 (ohlcv, market, snapshot 포함 — snapshot 은 이미 라우트 끊김)
- `vendors/alpha_vantage/` 전체 (news 서브모듈만 남아있음 — Task 7 네이버뉴스 전환 전까지 임시로 둘지 결정 필요)

