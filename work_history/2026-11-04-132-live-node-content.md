# [#132] Feat: 각 노드 완료 시 리포트 본문을 라이브 패널에 즉시 표시

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/132
- 브랜치: `feat/132-live-node-content`
- 작업 기간: 2026-11-04

## 치명적 UX 결함 수정

지금까지 라이브 패널은 노드별 **라벨 + elapsed 만** 보여줬음. 사용자는 수십 분 기다리는데 각 분석가가 뭘 분석했는지 결과를 못 보고, 최종 `Underweight` 한 줄만 받는 상황. 완전히 UX 설계 실패였음.

## 수정

### 코어 — `tradingagents/graph/trading_graph.py`

- `_render_report_content(value)` 신규 — state 값을 사용자 마크다운으로 평탄화.
  - 문자열 → 그대로
  - dict (debate_state 등) → `_DEBATE_FIELD_LABELS` 알려진 필드만 `### 라벨 \n\n 본문` 형태로 결합
  - 그 외 → 빈 문자열
- `_run_graph` state-diff 기반 `node_complete` emit 에 **`content` 필드 추가**.

### 백엔드 — `api/run_store.py`

- `RunState.reports: dict[str, str]` 추가 — 노드별 리포트 축적
- `record()` 가 `node_complete` 이벤트의 `content` 를 `reports[node]` 에 저장
- 늦게 접속한 클라이언트도 폴링으로 지금까지의 리포트 전부 확인 가능

### 백엔드 — `api/routes/runs.py`

- `RunSnapshot.reports` 노출 — `GET /api/runs/{id}` 응답에 포함

### 프론트 — `web/src/components/RunPanel.tsx`

- `marked` + `DOMPurify` 임포트 (ReportViewer 와 동일 방식)
- `Event.content` 필드 타입에 추가
- 각 완료 노드 아래 `<details class="step-report">` 아코디언 (**기본 open**) 으로 `content` 를 마크다운 렌더
- 사용자가 노드 완료 **즉시** 분석가 리포트 본문을 화면에서 읽을 수 있음

### 프론트 — `web/src/components/RunPanel.css`

- `.live-step` 구조를 flex column 으로 변경, `.step-head` 가 상단 라벨
- `.step-report` 아코디언 + `.step-report-body` 마크다운 prose 스타일 (헤딩/표/코드/blockquote 등)

### 테스트 — `tests/test_live_node_content.py` 신규 5개

- `_render_report_content` 문자열 passthrough / dict 평탄화 / 비지원 타입 처리
- `_run_graph` 가 node_complete 이벤트에 content 를 실어 보내는지
- API snapshot 의 `reports` 필드에 노드별 본문이 축적되는지

## 검증

- `pytest tests/test_live_node_content.py -v` → **5 passed**
- `pytest -q` 전수 → **922 passed, 11 deselected**
- `ruff check .` → clean
- `cd web && npm run build` → 2 pages / 343ms

## 로컬 실제 돌려서 확인할 것

PR 머지 후:
- 서버 재시작 (git pull + uvicorn 재시작)
- `effort=low` + 분석가 전부로 run 하나 돌림
- 노드가 끝날 때마다 **라이브 패널에 분석가 리포트 본문이 아코디언으로 펼쳐지는지** 확인
- 사용자가 끝까지 기다리지 않고도 중간 결과를 읽을 수 있는지
