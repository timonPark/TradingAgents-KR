# [#149] 재무 차트 — 유동성(현금 vs 단기 차입) 추가

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/149
- PR: https://github.com/timonPark/TradingAgents-KR/pull/156
- 브랜치: feat/149-liquidity-chart
- 작업 기간: 2026-11-05

## 수행한 변경

- `tradingagents/dataflows/vendors/dart.py`: `_KEY_ACCOUNTS` 에 재무상태표 계정 추가 (`cash`, `short_term_deposits`, `short_borrowings`, `current_long_term_debt`, `current_convertible_bonds`). 같은 key 에 표준 ID 가 둘이면(`ifrs-full_ShorttermBorrowings` / `dart_CurrentLoansReceived`) 먼저 찾은 것만 사용하고 합산하지 않는다.
- `tradingagents/charts.py`: `waterfall_chart` 에 독립 막대 kind(`asset`/`debt`) 추가, `liquidity_chart` 신규, `build_financial_charts` 가 3개 차트를 돌려줌. 실패 문구는 3개 차트 모두에 사유로 표시.
- `tests/test_charts.py`, `tests/test_dart_vendor.py`: 유동성 차트·BS 계정 식별 테스트 + 실호출 3건.

## 설계 결정 변경 사항

- 이슈 제안의 "현금성자산 vs 단기 차입·CB" 를 독립 막대(자산 초록 / 차입 빨강)로 구현. 현금 계정이 없거나 차입 계정이 하나도 없으면 0 막대로 그리지 않고 사유를 표시한다 (차입이 없는 회사와 계정 미식별을 구분할 수 없으므로).
- 단기금융상품(`ShorttermDepositsNotClassifiedAsCashEquivalents`)을 별도 막대로 함께 표시 (삼성전자는 현금성자산과 맞먹는 규모).

## 검증 결과

- 실제 DART 반기 응답(삼성전자·두산에너빌리티·금호전기)에서 계정 식별 확인. 두산 현금성 2.82조 vs 단기 차입 4.49조, 금호전기 현금 45.0억 vs 단기차입 13.6억 + CB 29.5억.
- `pytest` 1115 passed, `ruff check .` 통과, `-m integration tests/test_dart_vendor.py` 10 passed.
- 변이 검사: "먼저 찾은 ID 만" 가드 제거 시 테스트 실패.

## 다음 작업 핸드오프

- 미등록 후보 이슈: DART 공시 → 뉴스 분석가(대량보유·임원지분·CB 이벤트), 주요뉴스(global news) 복구.
- 결정 대기: 색상 규칙(한국식 상승 빨강/하락 파랑), #152 되돌리기 여부.
