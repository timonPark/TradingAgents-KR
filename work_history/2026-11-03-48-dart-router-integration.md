# [#48] Task 5b: router + fundamentals_analyst DART 통합 + 레거시 vendor 삭제

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/48
- PR: (작업 완료 후 추가)
- 상위 에픽: #46
- 브랜치: `feat/48-dart-router-integration`
- 작업 기간: 2026-11-03 ~

## 범위

Task 5a (#47, PR #49 머지됨) 에서 작성한 `vendors/dart.py` 를 실제 운용 경로에
연결. router 의 fundamentals/insider 분기를 DART 단일로 축소하고,
fundamentals_analyst 가 선조회에 CB (전환사채) 섹션을 포함하도록 확장.
레거시 SEC EDGAR / Alpha Vantage fundamentals / Yahoo fundamentals vendor
파일과 관련 테스트를 전부 삭제.

## 수행한 변경

### `tradingagents/dataflows/router.py`

- `TOOLS_CATEGORIES["fundamental_data"]` 에 `get_convertible_bonds` 신규 등록 + `get_insider_transactions` 를 `news_data` 에서 **이관** (DART 는 지분변동 공시를 재무/공시 vendor 로 서브. 상류의 Yahoo 뉴스 피드 기반 insider 와 범주가 다름).
- `VENDOR_METHODS` 의 `get_fundamentals`/`get_balance_sheet`/`get_cashflow`/`get_income_statement`/`get_insider_transactions` 를 **DART 단일 vendor** 로 축소.
- `get_convertible_bonds` 분기 신규 등록 (DART only).
- 레거시 import 제거: `vendors.sec_edgar`, `vendors.alpha_vantage.fundamentals`, `vendors.yahoo.fundamentals` 전부.

### `tradingagents/dataflows/vendors/dart.py`

- `get_company_profile(ticker)` 신규 추가 — DART `company()` 를 호출해 `longName`/`shortName`/`exchange`/`quoteType` 를 담은 dict 반환. `context.py` 의 identity 해석이 Yahoo 대신 DART 로부터 받도록 전환. 조회 실패 시 빈 dict (fail-open).

### `tradingagents/dataflows/vendors/alpha_vantage/__init__.py`

- `fundamentals` 모듈 import 제거.
- `get_insider_transactions` 재노출 삭제 (라우터가 더 이상 Alpha Vantage insider 를 호출하지 않음).

### `tradingagents/dataflows/vendors/alpha_vantage/news.py`

- `get_insider_transactions` 함수 자체 삭제 (dead code, 라우터 경로 없음).
- `withhold_undisclosed_trades` import 제거.

### `tradingagents/agents/context.py`

- `get_company_profile` import 를 `vendors.yahoo.fundamentals` → `vendors.dart` 로 전환. `_identity()` 호출 경로 동일.

### `tradingagents/agents/analysts/fundamentals_analyst.py`

- `_prefetch_fundamentals_data` 에 `get_convertible_bonds` 선조회 추가.
- `_render_prefetched` 에 "Convertible Bonds (최근 1년 CB 발행 공시)" 섹션 추가 — CB 는 희석 리스크 지표라 분석가가 투자 판단에 반영해야 함.

### `tradingagents/agents/tools.py`

- `@tool` 데코레이터로 `get_convertible_bonds` 신규 노출 — `trade_date` InjectedState, `ticker` InjectedState.

### `tradingagents/default_config.py`

- `data_vendors.fundamental_data` 디폴트를 `"sec_edgar,yfinance"` → `"dart"` 로 변경.

### 삭제 파일

- `tradingagents/dataflows/vendors/sec_edgar.py`
- `tradingagents/dataflows/vendors/alpha_vantage/fundamentals.py`
- `tradingagents/dataflows/vendors/yahoo/fundamentals.py`
- `tests/test_sec_edgar.py`
- `tests/test_alpha_vantage_hardening.py`
- `tests/test_fundamentals_lookahead.py`
- `tests/test_fundamentals_units.py`
- `tests/test_statement_knowledge_time.py`
- `tests/test_undated_tools_as_of.py` (전부 yahoo_fundamentals/polymarket insider 테스트)
- `tests/test_yahoo_rate_limit.py` (yahoo fundamentals rate-limit 테스트)

### 테스트 수정

- `tests/test_cache_writes.py` — sec_edgar 전용 테스트 1개 제거, 나머지 ohlcv/일반 캐시 테스트는 유지.
- `tests/test_dataflows_config.py` — tool_vendors 테스트에서 `"sec_edgar,yfinance"` → `"dart"` 로 교체.
- `tests/test_report_html.py` — 리포트 헤더의 fundamental_data vendor 를 `"dart"` 로 교체. 체인 순서 검증 제거 (단일 vendor).
- `tests/test_instrument_identity.py` — identity 해석 테스트가 Yahoo `yf.Ticker` 를 patch 하던 것을 `agents.context.get_company_profile` 를 patch 하도록 전환. 테스트 티커도 KRX (`005930` 삼성전자) 로 변경.
- `tests/test_no_data_handling.py` — yahoo fundamentals unreachable 테스트 제거.
- `tests/test_graph_end_to_end.py` — `tool_methods` 집합에 `get_convertible_bonds` 추가.

## 설계 결정 변경 사항

### `get_insider_transactions` 를 `fundamental_data` 범주로 이관

code_artifact.md Task 5 에는 "SEC EDGAR 교체" 로만 명시되어 있고 insider_transactions 가 어느 범주에 속해야 하는지는 명시 없음. 상류에서는 Yahoo 뉴스 피드가 insider trades 를 돌려줬기 때문에 `news_data` 에 있었는데, DART 는 주요주주/임원 지분변동을 **공시 데이터** (`major_shareholders_exec`) 로 서브. 사용자가 KRX insider 를 분석할 때 "뉴스" 가 아닌 "공시" 로 다루는 게 자연스러워 범주 이동.

영향: `data_vendors.news_data = "yfinance"` 디폴트 상태에서 insider_transactions 는 news_data 라우팅으로 yfinance 를 요구했음. 범주 이동으로 fundamental_data 라우팅 → DART 로 자연스레 전환.

### `get_company_profile` 를 DART 로 이전 (Yahoo 완전 분리)

code_artifact.md Task 5 는 재무/공시만 명시하지만 `context.py` 의 identity 해석이 Yahoo `yf.Ticker().info` 를 요구. KRX 종목코드로 Yahoo 를 호출하면 빈 결과 또는 엉뚱한 미국 종목에 매칭될 위험. 따라서 DART `company()` 결과를 Yahoo 포맷으로 매핑하는 `get_company_profile` 을 `vendors/dart.py` 에 추가. sector/industry 는 DART `induty_code` 가 숫자 코드만 제공 — 가독성 매핑 테이블 없이는 깔끔히 노출 불가라 identity 에서는 생략. 분석가 프롬프트는 `company_name` + `exchange` (KOSPI/KOSDAQ) 로 anchoring 가능.

## 검증 결과

- `pytest -q` 전체 → **922 passed, 8 subtests passed**
- `ruff check tradingagents cli tests` → **All checks passed**
- `grep -r "sec_edgar\|yahoo.fundamentals\|alpha_vantage.fundamentals" tradingagents/` → 0 매치 (docstring 설명 1건 제외)

실제 DART 네트워크 통합 테스트는 Task 11 로 분산.

## Task 5 에픽 (#46) 종결

이 PR 머지 후 모든 하위 이슈 close 가능:
- #47 (5a) ✅ `vendors/dart.py` 신규 작성 + OpenDartReader 의존성 (머지됨, PR #49)
- #48 (5b) 🟡 **이 PR** — router 통합 + 레거시 vendor 삭제

## 다음 작업 핸드오프

### Task 6 (#?): pykrx 로 Yahoo/Alpha Vantage 가격·지표 교체

- `vendors/yahoo/ohlcv.py`, `market.py`, `snapshot.py` 를 pykrx 기반으로 교체
- `vendors/alpha_vantage/stock.py`, `indicator.py` 삭제 또는 pykrx 로 전환
- `data_vendors.core_stock_apis` 디폴트를 `"pykrx"` 로

### Task 7 (#?): 네이버뉴스 + ECOS 로 Reddit/StockTwits/FRED 교체

- `vendors/reddit.py`, `vendors/stocktwits.py`, `vendors/fred.py` 삭제
- `vendors/naver_news.py`, `vendors/ecos.py` 신규 작성
- `sentiment_analyst.py` 를 네이버뉴스/증권 커뮤니티 기반으로 전환

