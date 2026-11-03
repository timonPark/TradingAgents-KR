# [#54] Task 6c: market_analyst 사전조회에 투자자별 수급 섹션 추가

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/54
- PR: (작업 완료 후 추가)
- 상위 에픽: #51
- 브랜치: `feat/54-market-analyst-investor-flow`
- 작업 기간: 2026-11-03 ~

## 범위

Task 6b (#53, PR #58) 로 라우팅 전환이 완료된 상태에서 market_analyst 가 수급
도구를 실제로 선조회하도록 확장. 투자자별 (외국인/기관/개인) 순매수는 KRX 가격
변동의 **선행 지표** 로 — 외국인 매도 흐름이 가격 하락을 선행하는 경우가 많아
시장 분석가가 이 신호를 명시적으로 활용해야 함.

## 수행한 변경

### `tradingagents/agents/analysts/market_analyst.py`

- `get_investor_net_purchases` import 추가.
- `_prefetch_market_data` 가 `get_investor_net_purchases(.invoke)` 호출 추가 — `look_back_days=5`, 다른 선조회와 같은 `_safe` 래퍼로 fail-safe 보장.
- 반환 dict 에 `investor_flow` 키 추가.
- `_render_prefetched` 에 "### 투자자별 수급 (최근 5거래일 순매수 — KRX 전용 선행 지표)" 섹션 추가.
- 시스템 프롬프트 지시 추가: "KRX Investor Flow" 블록에서 수급을 추세·모멘텀 지표와 함께 해석하도록 안내 (외국인 매도 지속 → 가격 하락 선행 / 기관 매수 유입 → 반등 선행).

### `tests/test_graph_end_to_end.py`

- `test_a_full_run_reaches_a_logged_decision` 의 `tool_methods` 집합에 `get_investor_net_purchases` 추가.

## 설계 결정 변경 사항

### 수급 섹션 한국어 헤더

프롬프트의 다른 pre-fetched 섹션은 영어 헤더지만 수급은 **한국어 섹션 헤더** 로 작성 (예: "투자자별 수급" vs "Investor Net Purchases"). 이유:
- 섹션 내용이 한국어 데이터 (외국인/기관/개인 라벨)
- 한국어 선행 지표라는 KRX 전용성 강조
- Task 9 (한국어 프롬프트 전환) 이 아직이지만, KRX 전용 블록부터 한국어화를 시작

Task 9 에서 전체 프롬프트가 한국어로 통일되면 다른 섹션 헤더도 같은 톤으로 전환.

### `look_back_days=5` 고정

code_artifact.md Task 6 에 "외국인/기관 5거래일 순매수" 명시. 추세 분석에 충분하면서 수급 노이즈가 과하지 않은 창. 분석가가 더 긴 창을 원하면 Task 9 프롬프트 튜닝 시점에 재검토.

## 검증 결과

- `pytest -q` 전체 → **921 passed, 8 subtests passed**
- `ruff check tradingagents cli tests` → **All checks passed**

## 다음 작업 핸드오프

### Task 6d (#55): `symbols.py` Yahoo 심볼 변환 잔재 정리
- Task 4a 에서 `normalize_symbol` 등 Yahoo 호환 shim 이 남아있음. KRX 전용 vendor 전환이 완료됐으므로 하위호환 shim 전수 삭제.

### Task 6e (#56): 레거시 yahoo/av 디렉터리 + 테스트 전면 삭제
- `vendors/yahoo/` 전체 (ohlcv, market, snapshot, news, common)
- `vendors/alpha_vantage/` 전체 (indicator, stock, news, common — news 는 Task 7 네이버뉴스 전환 전까지 임시 유지 여부 결정)
- 관련 테스트 삭제: `test_yahoo_*`, `test_alpha_vantage_*`

### Task 7 (#?): 네이버뉴스 + ECOS 로 뉴스/거시 교체 (Reddit/StockTwits/FRED/Polymarket 삭제)

