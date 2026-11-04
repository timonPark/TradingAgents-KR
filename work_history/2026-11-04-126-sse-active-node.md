# [#126] Fix: 분석 백엔드가 활성 노드/라운드/경과를 SSE 로 노출

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/126
- 브랜치: `fix/126-sse-active-node`
- 작업 기간: 2026-11-04

## 증상

Task 14e (#110) 머지 이후 실제 분석을 돌리니 UI 가 수십 분간 `6/8` 에서 변동 없음. `ps -p <claude pid>` 로는 "Bear 리서처가 10분째 응답 대기" 를 확인 가능했지만 SSE 로는 아무것도 안 나왔다. **서버가 가진 정보를 외부에 노출하지 않는 관측성 결함.**

## 수정

### 1) `tradingagents/graph/trading_graph.py`
- `_NODE_LABELS` 신설 — LangGraph 노드 이름(`Bull/Bear Researcher`, `Trader`, `Aggressive/Conservative/Neutral Risk Analyst` 등)을 한국어 라벨로 매핑
- `_iter_graph_events` 신규 private helper — `graph.stream(stream_mode=["values","tasks"], subgraphs=True)` 에서 task 시작(result=None)/완료(result=dict)를 구분해 `task_start` / `task_complete` / `state_update` / `message` 를 yield
- `_run_graph` 의 debug 경로를 `_iter_graph_events` 로 전환 → `node_start` / `node_complete` emit. 기존 state-diff 기반 `node_complete` 는 **안전망**으로 보존

### 2) `api/run_store.py`
- `RunState` 에 `active_node`, `active_node_started_at` 추가
- `record()` 가 `node_start` → 세팅, `node_complete`/`done`/`error` → 해제

### 3) `api/routes/runs.py`
- `RunSnapshot` 에 두 필드 노출 (ISO8601)

### 4) `web/src/components/RunPanel.tsx`
- SSE listener 에 `node_start` 추가
- 가장 최근 `node_start` 이후 완료 이벤트가 없으면 "활성"
- 1초 간격 리렌더로 "응답 대기 중 · 7분 15초" 라이브 업데이트
- 활성 노드 하이라이트 패널 (`.live-active`) + 완료 step 의 `elapsed_ms` 표기

### 5) `web/src/components/RunPanel.css`
- `.live-active`, `.active-dot` (patina pulse), `.active-label`, `.active-meta`, `.step-elapsed`

### 6) 테스트
- `test_trading_graph_progress.py`: 기존 테스트를 `_iter_graph_events` 모킹으로 전환 + `test_task_start_and_complete_events_in_debug_mode` 신규
- `test_api_runs.py`: `test_snapshot_exposes_active_node_during_run` 신규

## 설계 결정

- **`stream_run` 은 그대로** (public API 호환), `_iter_graph_events` 는 private
- **state-diff `node_complete` 유지** — LangGraph 버전/구성 차이로 tasks 가 전부 안 나올 수 있으므로 안전망. 중복 이벤트는 UI 에서 dedup
- **라벨 생성은 백엔드**가 — 프론트는 받은 걸 그대로 표시

## 검증 결과

- `pytest tests/test_trading_graph_progress.py tests/test_api_runs.py -v` → **12 passed**
- `pytest -q` 전수 → **908 passed, 11 deselected**
- `ruff check .` → clean
- `cd web && npm run build` → 2 pages / 973ms
