# [#174] 끝난 분석의 기준일과 에이전트별 등급을 API 로 조회

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/174
- PR: (PR 생성 후 기재)
- 브랜치: feat/174-report-agent-ratings
- 작업 기간: 2026-11-08

## 수행한 변경

- `tradingagents/agent_ratings.py` 신규: 에이전트의 섹션 글에서 5단계 등급을 읽는 판독기 `parse_agent_rating(text, agent)` 와 에이전트 10개 → 리포트 섹션 파일 대응 `AGENT_REPORT_FILES`. 규칙은 krx-screener 의 `agent_ratings.py` 를 그대로 옮겼다 (`등급`/`Rating` 라벨, 리서치 매니저만 `추천`, 줄 머리·접두 라벨 뒤만 라벨, `최종 거래 제안` 불읽음, 엇갈리면 비움).
- `api/reports_store.py`: 헤더 "- 분석일:" 에서 기준일을 읽고(`_read_header`), 섹션 파일에서 에이전트별 등급을 읽는다(`_read_agent_ratings`). `ReportSummary` 에 `trade_date`, `agent_ratings` 추가. `list_reports` 가 `ticker`/`trade_date` 로 **먼저 거른 뒤** `limit` 적용하고 남은 항목만 등급을 읽는다. 단건용 `read_report_meta` 신규.
- `api/routes/reports.py`: `GET /api/reports` 와 `GET /api/reports/{id}` 응답에 `trade_date`(없으면 null), `agent_ratings`(읽지 못한 에이전트는 빠짐) 추가. 목록에 `ticker`, `trade_date` 쿼리 파라미터. 기존 필드는 그대로, 조건을 안 주면 지금과 같다 (하위 호환).
- `GLOSSARY.md`: 에이전트별 등급.
- 테스트: `tests/test_agent_ratings.py` 신규(26), `tests/test_api_reports.py` +6.

## 설계 결정 변경 사항

`code_artifact.md` 와 달라진 지점 없음. 이슈가 열어 둔 부분을 아래처럼 정했다.

- **등급을 새로 저장하지 않고 저장된 리포트 트리에서 읽는다.** 이슈는 "`report_saved` 때 같이 디스크에 남기면" 이라고 제안했지만, 섹션 파일(`1_analysts/market.md` 등)이 이미 각 에이전트의 글을 담고 있다. 트리에서 읽으면 (1) 서버를 다시 켜도 같고 (2) **이미 저장된 리포트도 소급해서 읽히며**(이슈의 "소급 안 하면 비는 문제" 해소) (3) 새 파일 형식·마이그레이션이 없다. 대가로 목록 호출마다 `limit` 개 리포트의 파일 10개씩을 읽는다 — 실제 서버에서 50개 0.09초, 137개 전부 0.17초.
- **기준일은 헤더의 "- 분석일:" 에서 읽는다.** `report_id` 의 `stamp` 는 저장 시각이라 기준일이 아니다. 헤더에 줄이 없으면 `trade_date` 는 null 이고 기준일 필터에서 빠진다.
- **에이전트 이름은 krx-screener 가 이미 쓰는 것과 같게** (`market`, `news`, `fundamentals`, `bull`, `bear`, `research_manager`, `aggressive`, `conservative`, `neutral`, `portfolio_manager`). 클라이언트가 판독기를 걷어내고 바로 바꿔 쓸 수 있다.
- **`rating.extract_rating` 을 쓰지 않고 판독기를 따로 두었다.** 서버의 `extract_rating` 은 `최종 거래 제안`(BUY/HOLD/SELL 3단계) 라벨도 읽어서, 5단계 등급이 없는 글에서 뭉갠 값이 나온다. 에이전트 평균 점수가 한쪽으로 치우치므로 그 라벨을 읽지 않는 규칙이 필요했다.
- **`RunSnapshot` 에는 넣지 않았다** (이슈의 "(선택)"). 클라이언트는 `report_saved` 이벤트의 `report_id` 로 `GET /api/reports/{id}` 를 부르면 된다.
- 같은 종목·기준일을 다시 분석해도 리포트 디렉터리는 시각별로 따로 남는다(덮어쓰이지 않음). 목록은 최신순이라 `?ticker=…&trade_date=…` 의 첫 항목이 가장 최근 분석이다.

## 검증 결과

- `pytest` 1250 passed (25 deselected), 새 테스트는 구현 전 실패(red) 확인 후 통과 (판독기 테스트는 옮긴 규칙을 고정하는 용도라 구현 직후 통과). `ruff check tradingagents cli tests api` 통과.
- **krx-screener 판독기와 대조:** 이 컴퓨터의 실제 상태 로그 **125개**의 에이전트 칸 전부(등급 읽힌 칸 1229개)에서 서버 판독기와 krx-screener 판독기의 결과가 **차이 0**.
- **리포트 트리와 상태 로그 대조:** 실제 리포트 **137개**가 모두 기준일과 등급을 읽었고, 같은 (종목, 기준일)의 상태 로그가 있는 124건에서 트리에서 읽은 에이전트별 등급이 로그에서 읽은 것과 **전부 같다** (섹션 파일의 글 = 상태 칸의 글임을 확인). 이슈의 예시 리포트(웹젠 `069080_20261108_071143`)는 `trade_date=2026-11-05` 와 에이전트 10개 등급이 읽힌다.
- 이 검증 스크립트는 저장소에 두지 않았다 (특정 컴퓨터의 로그에 의존).

## 다음 작업 핸드오프

- 관찰 (이 PR 과 무관, 고치지 않음): `api/reports_store.py::_ALLOWED_FOLDERS` 는 `analysts`, `research` 등을 허용하지만 실제 리포트 폴더는 `1_analysts`, `2_research` 등이라, `GET /api/reports/{id}` 의 `files` 에는 실제 트리에서 `complete_report.md` 만 나온다 (기존 테스트는 `analysts/` 로 만든 가짜 트리를 쓴다). 후속 이슈 후보.
- 한계: 서버가 글 모양(`**등급**` 줄)을 바꾸면 그 에이전트가 비게 된다 (오류로 멈추지 않음). 이제 판독기가 서버 안에 있으므로 글을 렌더링하는 쪽(`agents/schemas.py`)을 바꿀 때 같이 확인할 수 있다.
- krx-screener 는 `GET /api/reports?ticker=…&trade_date=…` 의 `agent_ratings` 로 상태 로그 직접 읽기(같은 컴퓨터 전제, 덮어쓰기 위험)를 대체할 수 있다. 클라이언트 쪽 전환은 그 저장소의 별도 작업.
