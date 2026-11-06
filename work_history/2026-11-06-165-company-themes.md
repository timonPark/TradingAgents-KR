# [#165] 회사 개요 — 소속 테마 (근거·출처 표기)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/165 (상위: #163)
- PR: https://github.com/timonPark/TradingAgents-KR/pull/167
- 브랜치: feat/165-company-themes
- 작업 기간: 2026-11-06

## 수행한 변경

- `tradingagents/agents/analysts/company_themes.py` 신규: `Theme`/`ThemeList` 스키마, `extract_themes`(구조화 출력 1회), `verify_themes`(근거 문장이 사업 개요 발췌에 실제로 있는 테마만 최대 3개, 공백·따옴표 차이는 무시, 12자 미만 근거·20자 초과 이름·중복 제외). 결과는 `{status: ok|none|error|unavailable, themes, reason}`.
- `tradingagents/agents/analysts/fundamentals_analyst.py`: 보고서 작성 뒤 테마 추출, `fundamentals_data["themes"]` 로 최종 상태까지 보존. 실패해도 재무 보고서는 막히지 않는다.
- `tradingagents/report_html.py`: 회사 개요 안에 "소속 테마" 블록(`_themes_html`) — 테마별 원문 인용, 못 구하면 "확인되지 않음 — 사유". 출처 문구에 "테마 이름은 모델이 붙였고 인용문은 원문 확인분" 명시.
- `GLOSSARY.md`: 소속 테마.
- 테스트: `tests/test_company_themes.py` 신규(17), `tests/test_fundamentals_overview.py` 수정.

## 설계 결정 변경 사항

- **근거 인용 검증으로 환각 차단.** 이슈의 "조회 자료에 근거 + 출처 표기"를 "모델이 낸 인용문이 공시 원문에 그대로 있어야 채택"으로 구현. 테마 *이름*은 모델이 붙이므로 완전히 기계 검증되지는 않고, 인용문이 옆에 함께 보여 독자가 판단한다.
- **자료는 DART 사업 개요만.** 뉴스 근거 테마는 #166(핵심 이슈)과 함께 다룬다 — 분석가들이 병렬로 돌아 재무 분석가는 뉴스 결과를 보지 못한다.
- LLM 호출이 재무 분석가당 1회 → 2회로 늘었다 (테마 추출은 짧은 구조화 호출).

## 검증 결과

- 실제 Claude Code 로 알테오젠(피하주사 제형 전환 / 플랫폼 기술 라이선스 / 바이오시밀러), 삼성전자(메모리 반도체 / OLED / 전장), 금호전기(LED 조명 / 형광 램프 / 소프트웨어) 추출 확인 — 모두 근거 문장이 DART 원문 그대로.
- 알테오젠 보고서 PDF 1쪽에서 소속 테마 블록 확인.
- `pytest` 1166 passed, `ruff check .` 통과.
- 변이 검사: 근거 존재 검사 제거 → 지어낸 근거 테스트 2건 실패, 최소 길이 검사 제거 → 짧은 근거 테스트 실패.

## 다음 작업 핸드오프

- #166 현재 핵심 이슈 2~3개 (뉴스·공시 근거).
- 테마를 뉴스 근거까지 넓히려면 뉴스 분석가 결과를 재무 분석가 뒤 단계에서 합쳐야 한다.
