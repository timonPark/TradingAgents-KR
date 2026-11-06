# [#166] 회사 개요 — 현재 핵심 이슈 2~3개 (뉴스·공시 근거, 출처 표기)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/166 (상위: #163)
- PR: https://github.com/timonPark/TradingAgents-KR/pull/168
- 브랜치: feat/166-company-issues
- 작업 기간: 2026-11-06

## 수행한 변경

- `tradingagents/dataflows/vendors/dart.py`: `get_recent_disclosures` 신규 — 분석 기준일 이전 30일 공시를 최신순 최대 20건 JSON(`date/title/filer/url`)으로. `router.py`·`tools.py` 등록.
- `tradingagents/agents/analysts/company_issues.py` 신규: 기사(N)·공시(D)에 번호를 붙여 모델에 주고 `Issue{title, summary, source_ids, evidence}` 구조화 출력. `verify_issues` 가 (1) 번호가 조회한 자료인지 (2) 인용구(8자 이상)가 인용한 자료의 제목에 있는지(줄임표로 잘린 제목은 보이는 부분만) 검사, 통과한 이슈만 최대 3개. 출처의 제목·날짜·링크는 **조회 데이터에서** 붙인다. 결과 `{status: ok|none|error|unavailable, issues, reason}`.
- `tradingagents/agents/analysts/news_analyst.py`: 공시 사전조회 추가 → **프롬프트에도 "최근 공시" 블록으로 주입**(프롬프트가 이미 공시 리스크를 언급하는데 공시를 못 보던 문제), 보고서 작성 뒤 이슈 추출, `company_issues` 로 보존.
- `tradingagents/graph/{analyst_execution,setup}.py`, `agents/state.py`: 분석가 서브그래프가 `company_issues` 를 최종 상태까지 내보내도록 `extra_data_keys` 추가.
- `tradingagents/report_html.py`: 회사 개요에 "현재 핵심 이슈" 블록(번호 목록 + 출처 줄, http(s) 링크만, 모델 글은 이스케이프).
- `company_themes.py`: `_squash` → `squash` (두 모듈 공용).
- `GLOSSARY.md`: 현재 핵심 이슈.
- 테스트: `tests/test_company_issues.py` 신규(26), `tests/test_dart_vendor.py`(+3 단위, +1 실호출), `test_graph_end_to_end.py`, `test_structured_agents.py` 수정.

## 설계 결정 변경 사항

- **재무 분석가가 아니라 뉴스 분석가에서 추출.** 분석가들이 병렬이라 재무 분석가는 뉴스를 못 본다. 그래프 토폴로지를 바꾸는 대신 뉴스를 이미 가진 뉴스 분석가에 #165 와 같은 패턴(보고서 작성 뒤 짧은 구조화 호출)을 붙였다. 호출은 뉴스 분석가당 1회 → 2회.
- **근거 = 번호 + 헤드라인 인용.** 이슈 5번(환각 방지)을 "인용구가 인용한 자료 제목에 그대로 있어야 채택, 출처는 조회 데이터"로 구현. 이슈 제목·요약 문장은 모델이 쓰므로 완전히 기계 검증되지는 않는다 (보고서에 명시).
- 뉴스 헤드라인만 근거다(본문 미조회). 요약에 "자료에 없어 확인할 수 없다"는 한계 문구가 섞여 나올 수 있다.
- 한계: 회사 개요 섹션은 재무 분석가의 `business` 가 있어야 만들어지므로 뉴스 분석가만 선택한 실행에서는 핵심 이슈가 보고서에 나오지 않는다.

## 검증 결과

- 실제 Claude Code + 실제 네이버 뉴스·DART 공시로 알테오젠(3분기 영업이익·마일스톤 / 합병 증권신고서 정정 요구 / 소송 시간 문제), 삼성전자(잠정실적·배당·자사주 처분), 금호전기(애프터마켓 급락·전환권 행사) 추출 — 인용구는 모두 헤드라인·공시 제목 그대로.
- 알테오젠 보고서 PDF 1쪽에서 소속 테마·현재 핵심 이슈(출처 줄 포함) 표시 확인.
- `pytest` 1195 passed, `ruff check .` 통과.
- 변이 검사: 인용 일치 검사 제거 → 2건, 번호 실재 검사 제거 → 2건, 최소 길이 검사 제거 → 1건 실패. (줄임표 포함 금지 검사는 `_core` 와 중복이라 제거.)

## 다음 작업 핸드오프

- 관찰: `get_global_news` 의 `naver_news` vendor 가 "엔드포인트가 stock.naver.com 로 이전됨" 으로 실패한다 (이 PR 과 무관, 주요뉴스 복구 필요).
- #163 마무리: uvicorn 을 띄워 새 분석 전체를 돌려 개요(테마·핵심 이슈) 확인.
