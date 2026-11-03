# [#66] Task 7e: prediction_markets 범주 + polymarket 완전 제거

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/66
- PR: (작업 완료 후 추가)
- 상위 에픽: #61
- 브랜치: `feat/66-remove-prediction-markets`
- 작업 기간: 2026-11-03 ~

## 범위

Polymarket 등 예측시장 플랫폼은 한국에 등가체가 없음 (유사한 KR 서비스 존재해도
규제 불안정, 유동성 부족). 분석 파이프라인에서 `get_prediction_markets` 도구와
`prediction_markets` 범주를 **완전 제거**.

**scope 밖:**
- `vendors/polymarket.py` 파일 삭제: Task 7f (#67) 와 함께

## 수행한 변경

### `tradingagents/dataflows/router.py`

- `polymarket` import 전부 제거.
- `TOOLS_CATEGORIES["prediction_markets"]` 범주 삭제.
- `OPTIONAL_CATEGORIES` 에서 `"prediction_markets"` 제거 — 이제 `macro_data` 만
  optional. 하드 포크 결정 (ADR-0001) 주석 추가.
- `VENDOR_METHODS["get_prediction_markets"]` 분기 삭제.

### `tradingagents/agents/tools.py`

- `get_prediction_markets` `@tool` 함수 전체 삭제. 삭제 사유 안내 주석 유지.

### `tradingagents/agents/analysts/news_analyst.py`

- `get_prediction_markets` import 제거.
- `_PREDICTION_TOPICS` 상수 삭제.
- `_prefetch_news_data` 에서 prediction markets 선조회 loop 삭제.
- 반환 dict 에서 `prediction_markets` 키 삭제.
- `_render_prefetched` 에서 "### Prediction Markets" 섹션 삭제.
- 시스템 프롬프트의 "live prediction-market probabilities ..." 설명 삭제.

### `tradingagents/default_config.py`

- `data_vendors.prediction_markets` 엔트리 삭제.

### `tradingagents/report_html.py`

- `_CATEGORY` 매핑에서 `prediction_markets` 라벨 삭제 — 리포트 헤더가 더 이상
  "Prediction markets" 라인을 렌더링하지 않음.

### 테스트 수정 / 삭제

- `tests/test_polymarket.py` **전면 삭제** — 더 이상 vendor 라우팅이 없음.
- `tests/test_graph_end_to_end.py` — `tool_methods` 집합에서
  `get_prediction_markets` 제거.

## 설계 결정 변경 사항

### `vendors/polymarket.py` 파일 유지 (Task 7f 로 유예)

code_artifact.md Task 7 은 "삭제: vendors/polymarket.py" 명시. 이번 PR 범위는
**라우팅/도구/분석가에서 참조 제거** 로 한정하고, 파일 삭제는 Task 7f (레거시
전면 cleanup) 와 일괄 처리. 라우팅 참조가 없어 dead code 상태라 분석에 영향 없음.

### `OPTIONAL_CATEGORIES` 재검토

상류의 OPTIONAL_CATEGORIES 는 `{"macro_data", "prediction_markets"}`. 둘 다
vendor 실패 시 sentinel 반환으로 분석가 run 보호. prediction_markets 삭제 후
`macro_data` 만 남음. ECOS 키 미설정이나 네트워크 블립이 분석가를 중단시키지
않도록 유지.

## 검증 결과

- `pytest -q` 전체 → **913 passed, 8 subtests passed** (삭제된 test_polymarket.py
  반영, 10개 테스트 제거됨)
- `ruff check tradingagents cli tests` → **All checks passed**

## 다음 작업 핸드오프

### Task 7f (#67): 레거시 vendor + 테스트 + crypto_base 전면 삭제

Task 7 에픽 (#61) 마지막 단계:
- 디렉터리 삭제: `vendors/yahoo/`, `vendors/alpha_vantage/`
- 파일 삭제: `vendors/reddit.py`, `vendors/stocktwits.py`, `vendors/fred.py`,
  `vendors/polymarket.py`
- `symbols.py::crypto_base` 스텁 함수 삭제
- 관련 테스트 삭제: `test_social_lookahead.py`, `test_reddit*.py`,
  `test_stocktwits*.py`, `test_fred_vendor.py`, `test_news_lookahead.py`,
  `test_yahoo_rate_limit.py` 등

