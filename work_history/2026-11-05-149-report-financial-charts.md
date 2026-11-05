# [#149] 보고서 재무 차트 — 손익 폭포·현금 브리지 (DART 표준 계정 ID 기반)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/149
- PR: (작성 후 기입)
- 브랜치: feat/149-report-financial-charts
- 작업 기간: 2026-11-05 ~ 2026-11-05

## 문제

이전 보고서에는 재무 차트(손익 폭포·현금 브리지)가 있었지만 현재 파이프라인에는 없다. 재무제표는 계정명 기준 마크다운 표라 회사마다 계정명이 달라(`매출액`/`수익`, `반기순이익`/`당기순이익(손실)`) 문자열 매칭은 조용히 틀린 값을 그릴 수 있다.

## 조사 결과 (실제 DART 응답: 삼성전자·두산에너빌리티·금호전기)

- 표준 계정 ID 는 세 회사에서 일관됐다 (`ifrs-full_Revenue`, `dart_OperatingIncomeLoss`, `ifrs-full_ProfitLoss`, `ifrs-full_CashFlowsFromUsedInOperatingActivities` 등).
- 금호전기는 손익계산서(IS)가 없고 포괄손익계산서(CIS) 하나에 손익이 있다 → IS, CIS 순서로 찾는다.
- 같은 ID `ifrs-full_ProfitLoss` 가 IS·CIS·CF 에 모두 있다 → 손익 항목은 IS/CIS 에서만 읽는다.
- **기간 함정**: 반기·3분기 보고서에서 손익의 `thstrm_amount`(당기)는 해당 분기 3개월치이고 누적은 `thstrm_add_amount` 다. 현금흐름표는 `thstrm_amount` 가 이미 누적이다. 둘을 섞으면 안 된다 (두산 매출: 당기 4.72조 vs 누적 8.99조).
- `finstate_all` 은 연결(CFS)만 요청한다 (별도 OFS 폴백 없음).

## 수행한 변경

- `tradingagents/dataflows/vendors/dart.py` — `extract_key_accounts`(표준 계정 ID, 손익은 누적 금액·현금흐름은 당기 금액, 빈 값은 뺌, 부문(주석) 행 무시), `get_financial_accounts`(JSON 문자열, 실패는 사람이 읽는 문구)
- `tradingagents/dataflows/router.py`, `tradingagents/agents/tools.py` — `get_financial_accounts` 라우팅·도구
- `tradingagents/agents/analysts/fundamentals_analyst.py`, `agents/state.py` — 프롬프트에는 주입하지 않고 `final_state["fundamentals_data"]` 로 보존
- `tradingagents/graph/analyst_execution.py` — 재무 분석가의 `data_key="fundamentals_data"` (#151 의 서브그래프 출력 경로 사용)
- `tradingagents/charts.py` — `parse_financial_accounts`, `waterfall_chart`, `income_waterfall`(매출액 → 매출원가 → 매출총이익 → 판관비 등 → 영업이익 → 영업외·법인세 등 → 순이익), `cash_bridge`(기초 현금 → 영업·투자·재무 → 환율·기타 → 기말 현금), `build_financial_charts`. 계정을 찾지 못하면 추정하지 않고 어떤 계정이 없는지 사유로 표시. 단위는 크기에 따라 억 원/조 원, 기간·연결 여부를 부제에 표기.
- `tradingagents/report_html.py` — 재무 분석가 섹션 끝에 "재무 차트", 폭포 CSS
- 테스트: `tests/test_dart_vendor.py`(추출 11 + 실호출 3), `tests/test_charts.py`(10), `tests/test_report_html.py`(2), 전체 그래프 실행(`test_graph_end_to_end`)·서브그래프(`test_analyst_execution`)에 `fundamentals_data` 확인

## 설계 결정 변경 사항

이슈 #149 의 "유동성(현금성자산 vs 단기 차입·CB)" 차트는 이번 범위에서 제외했다. 단기차입·CB 의 표준 계정 ID 가 회사별로 검증되지 않았고, 이 프로젝트의 원칙(추정 금지)상 ID 를 확인하기 전에는 그릴 수 없다. 별도로 계정 ID 를 조사한 뒤 추가한다.

## 검증 결과

- `pytest` 전체 통과, `ruff check .` 통과
- **실호출 통합 테스트**(`-m integration`): 업종이 다른 3개 회사(삼성전자·두산에너빌리티·금호전기)에서 핵심 계정 8개가 모두 표준 계정 ID 로 식별되고 현금 브리지가 맞아떨어짐
- 3개 회사의 실제 데이터로 차트를 렌더해 DART 원본 값과 대조 (두산 매출 8.99조·영업이익 0.55조, 금호전기 영업손실 -9.9억·현금 38.2→45.0억, 삼성 매출 305.37조)
- 누적 금액 규칙을 되돌리는 변형을 넣어 테스트 4건이 실패하는 것을 확인 후 복원
- 기존 `tests/test_dart_vendor.py` 의 autouse 픽스처가 실호출 테스트에서도 `DART_API_KEY` 를 더미 키로 덮어 실호출 테스트 2건이 원래부터 실패하던 것을 발견해 함께 수정

## 다음 작업 핸드오프

- 별도 이슈 후보: 재무 분석가 프롬프트의 마크다운 표는 `당기`(손익은 분기 3개월치)·`전기` 만 보여주고 누적을 숨겨, 현금흐름표(누적)와 기간이 섞여 읽힐 수 있다. 또 `.head(30)` 으로 표가 잘린다.
- 연결(CFS)만 요청한다. 연결 재무제표가 없는 회사는 차트가 사유로 표시된다 (별도 OFS 폴백은 범위 밖).
- 유동성 차트: 단기차입·CB 표준 계정 ID 조사 후 추가.
