# [#154] DART 손익 표에 누적 열 추가 — 현금흐름표와 기간 통일

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/154
- PR: https://github.com/timonPark/TradingAgents-KR/pull/155
- 브랜치: fix/154-dart-income-cumulative
- 작업 기간: 2026-11-05

## 수행한 변경

- `tradingagents/dataflows/vendors/dart.py`
  - `_format_statement(df, division_code, reprt_code)`: 반기·3분기 손익 표에 `당기(분기 3개월)` · `누적` · `전년 동기 누적` 열. 누적 값이 없는 보고서(1분기·사업보고서)는 기존 `당기/전기/전전기`.
  - `_period_note`: 표 머리말(보고서 종류·단위·각 열의 기간, 현금흐름표와 비교할 때 `누적` 사용 안내).
  - `_key_first`: `_KEY_ACCOUNTS` 의 표준 계정 ID 로 핵심 계정을 맨 앞에 정렬한 뒤 `.head(30)`.
  - `_money_text`: 금액을 천 단위 구분 정수로, 값 없음은 `-` (지수 표기·`nan` 제거).
  - `get_income_statement`: IS 우선, IS 가 없는 회사만 CIS (두산 CIS 는 기타포괄손익뿐이라 매출이 없었음).
- `tests/test_dart_vendor.py`: 표 열·머리말, 핵심 계정 정렬(IS·CF), 금액 표기, IS/CIS 우선순위, 표-차트 값 일치 유닛 테스트 + 실호출 2건.

## 설계 결정 변경 사항

없음. (`.head(30)` 은 유지하되 핵심 계정을 앞에 두는 방식으로 잘림을 막음.)

## 검증 결과

- `pytest` 1105 passed, `ruff check .` 통과
- 실호출 `pytest tests/test_dart_vendor.py -m integration` 7 passed (두산에너빌리티·금호전기 손익 표 포함)
- 변이 검사: 핵심 계정 정렬 기본 순위를 `len(order)` 로 바꾸면 CF 정렬 테스트 실패 → 구현 중 발견한 버그(CF 핵심 계정이 정렬되지 않음)를 테스트가 잡음.

## 다음 작업 핸드오프

- #149 의 유동성(현금 vs 단기차입·CB) 차트: 단기차입·CB 표준 계정 ID 검증 필요.
- 후보 이슈(미등록): DART 공시 → 뉴스 분석가, 주요뉴스(global news) 복구.
