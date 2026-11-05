# [#163] 보고서에 회사 개요 추가 (사업 내용 + 표지 회사명)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/163
- PR: (PR 생성 후 기입)
- 브랜치: feat/163-company-overview
- 작업 기간: 2026-11-06

## 수행한 변경

- `tradingagents/dataflows/vendors/dart.py`: `get_business_overview` 신규 (+ `_plain_text`, `_table_rows`, `_trim_overview`, `_latest_business_report`). 분석 기준일 이전의 정기보고서(사업보고서 우선)에서 "사업의 개요" 원문을 평문으로 발췌, 회사 개황·접수번호·원문 링크와 JSON 으로 반환. 표는 행 단위(`a | b | c`)로 평탄화.
- `tradingagents/dataflows/router.py`, `tradingagents/agents/tools.py`: `get_business_overview` 등록 (fundamental_data).
- `tradingagents/agents/analysts/fundamentals_analyst.py`: 발췌를 "회사 개요" 근거로 프롬프트에 주입, 공시에 없는 내용은 학습 지식으로 채우지 못하게 지시, `fundamentals_data["business"]` 로 최종 상태까지 보존.
- `tradingagents/report_html.py`: "회사 개요" 섹션(`company_overview_html`, 한눈에 보기 앞) + 표지·`<title>` 회사명(`_company_name`).
- `GLOSSARY.md`: 회사 개요.
- 테스트: `tests/test_dart_vendor.py`(+실호출 3), `tests/test_fundamentals_overview.py` 신규, `tests/test_report_html.py`, `tests/test_graph_end_to_end.py`.

## 설계 결정 변경 사항

- **개요 본문은 모델이 쓰지 않는다.** 이슈 5번(환각 방지)을 "조회한 공시 원문 발췌 + 출처 표기"로 구현 — 지어낸 내용이 들어갈 구조적 여지가 없다.
- **범위 밖(후속):** 이슈의 "소속 테마"와 "현재 핵심 이슈 2~3개"는 공시에 없고 뉴스·시장 해석이 필요해 LLM 합성이 들어간다. 이번에는 재무 분석가가 공시 발췌에 근거해 사업·용어를 풀어 쓰도록 지시하는 데까지만 했고, 별도 섹션은 만들지 않았다.
- 회사명은 조회한 개황 → 실행 시작 때 확정한 `instrument_context` 순. 렌더 단계에서 네트워크 호출은 하지 않는다.

## 검증 결과

- 알테오젠(196170)·삼성전자(005930)·금호전기(001210) 실제 DART 응답으로 사업 개요 추출 확인. 알테오젠: Hybrozyme 플랫폼, MSD·AstraZeneca·GSK 등 라이선스 계약, 마일스톤·로열티 수익 구조가 원문 그대로 나옴.
- 알테오젠 보고서 HTML/PDF 에서 표지 "알테오젠 196170", 맨 앞 "회사 개요" 섹션 확인.
- `pytest` 1149 passed, `ruff check .` 통과, `-m integration tests/test_dart_vendor.py` 13 passed.
- 변이 검사: 이스케이프 제거 → `test_overview_escapes_markup_from_the_filing`, `name` 변수 섀도잉 → 표지 테스트(구현 중 실제 발생한 버그), 사업보고서 우선순위 제거 → 우선순위 테스트 실패.

## 다음 작업 핸드오프

- 소속 테마·현재 핵심 이슈 섹션 (뉴스 분석가 결과 + 공시에 근거한 LLM 합성, 출처 표기).
- 결정 대기: 색상 규칙(한국식 상승 빨강/하락 파랑), #152 되돌리기 여부.
