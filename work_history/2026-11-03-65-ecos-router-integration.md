# [#65] Task 7d: router + macro 범주를 ECOS 로 전환

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/65
- PR: (작업 완료 후 추가)
- 상위 에픽: #61
- 브랜치: `feat/65-ecos-router-integration`
- 작업 기간: 2026-11-03 ~

## 범위

Task 7b (#63, PR #69) 에서 작성한 `vendors/ecos.py` 를 라우팅/분석가에 연결.
FRED (미국) 거시지표 vendor 를 한국은행 ECOS 로 완전 대체. news_analyst 의
사전조회 거시 지표 목록도 ECOS alias 로 교체.

**scope 밖 (다음 단계):**
- prediction_markets + polymarket 제거: Task 7e (#66)
- 레거시 vendor 파일 전면 삭제: Task 7f (#67)

## 수행한 변경

### `tradingagents/dataflows/router.py`

- `fred.get_macro_data` import → `ecos.get_macro_data`.
- `VENDOR_METHODS["get_macro_indicators"]` 를 `{"ecos": get_ecos_macro_data}`
  단일 vendor 로 축소.

### `tradingagents/agents/analysts/news_analyst.py`

- `_MACRO_INDICATORS` 를 FRED alias → ECOS alias 로 교체:
  - `cpi` (유지, ECOS 는 소비자물가지수)
  - `core_pce` → `core_cpi`? → 삭제 (ECOS 에 PCE 등가체 없음)
  - `unemployment` → `unemployment_rate`
  - `fed_funds_rate` → `base_rate` (한국은행 기준금리)
  - `10y_treasury` → `treasury_10y` (국고채 10년)
  - `yield_curve` → 삭제 (ECOS 에 수익률 곡선 통합 지표 없음)
  - **신규**: `usd_krw` (원/달러 환율), `consumer_sentiment` (CSI)
- 시스템 프롬프트의 "FRED (Federal Reserve Economic Data)" 설명 → "한국은행 ECOS"
  로 교체. 지표 목록도 한국어 지표명으로 (기준금리, 소비자물가지수, 실업률, 국고채
  10년, 원/달러 환율, 소비자심리지수).
- `_render_prefetched` 섹션 헤더: "Macroeconomic Indicators (FRED, by series)"
  → "Korean Macroeconomic Indicators (한국은행 ECOS, by series)".

### `tradingagents/agents/tools.py`

- `get_macro_indicators` tool docstring 재작성:
  - FRED alias 예시 (cpi, core_pce, fed_funds_rate, 10y_treasury, ecb_deposit_rate, ...)
    → ECOS alias (base_rate, cpi, usd_krw, consumer_sentiment, ...)
  - 설명도 한국 거시 지표 범주로.

### `tradingagents/default_config.py`

- `data_vendors.macro_data`: `"fred"` → `"ecos"`.

## 설계 결정 변경 사항

### 지표 선택 — code_artifact.md Task 7 명시 범위 확장

code_artifact.md 는 "환율·기준금리 정적 매핑 또는 ECOS 호출" 명시. news_analyst
사전조회에 핵심 6개 지표를 선택:
- 기준금리 + 10년 금리 (금리 환경)
- CPI (인플레이션)
- 실업률 (노동)
- 원/달러 환율 (대외)
- CSI (소비자 심리)

이는 KRX 투자 판단에 가장 영향력 큰 매크로 신호들. 확장 가능성 열려있음.

### `yield_curve` / `core_pce` 삭제

상류 FRED 는 2y-10y 스프레드를 `T10Y2Y` 로 서브하지만 ECOS 는 수익률 곡선 통합
지표를 공식 제공하지 않음. 분석가가 필요하면 `treasury_3y` 와 `treasury_10y` 를
각각 조회해 수동 계산 가능. `core_pce` 는 미국 Fed 선호 지표라 한국 거시에 등가체
없음 — `core_cpi` 는 ECOS 가 지원하지만 데이터 가용성 문제로 Task 11 통합 테스트
에서 확인 후 추가 결정.

### Tool docstring 한국어화 범위

지표 설명을 한국어로 전환 (`'base_rate' (기준금리)`). 함수 docstring 도 한국어로.
LangChain tool 레지스트리는 docstring 을 LLM 에게 그대로 노출하므로 KRX 분석
컨텍스트에 맞는 지표 안내가 됨. Task 9 (한국어 프롬프트 전환) 전까지 KRX 전용
도구부터 선제적으로 한국어화.

### news_analyst 변경 영향 범위

사전조회 호출은 tool wrapper 통한 간접 호출이라 vendor 교체만으로 자동 ECOS 를
받음. tuple 상수 (`_MACRO_INDICATORS`) 와 프롬프트 설명만 조정하면 됨.

## 검증 결과

- `pytest -q` 전체 → **922 passed, 8 subtests passed**
- `ruff check tradingagents cli tests` → **All checks passed**

## 다음 작업 핸드오프

### Task 7e (#66): prediction_markets + polymarket 완전 제거
- `router.TOOLS_CATEGORIES["prediction_markets"]` 삭제
- `router.VENDOR_METHODS["get_prediction_markets"]` 삭제
- `tools.py::get_prediction_markets` @tool 삭제
- `news_analyst._PREDICTION_TOPICS` 삭제, 선조회 호출 삭제, 프롬프트 섹션 삭제
- `default_config.data_vendors.prediction_markets` 삭제

### Task 7f (#67): 레거시 vendor + 테스트 + crypto_base 전면 삭제
- 디렉터리 `vendors/yahoo/`, `vendors/alpha_vantage/` 전체 삭제
- 파일 `vendors/reddit.py`, `vendors/stocktwits.py`, `vendors/fred.py`,
  `vendors/polymarket.py` 삭제
- `symbols.py::crypto_base` 스텁 함수 삭제
- 관련 테스트 삭제

