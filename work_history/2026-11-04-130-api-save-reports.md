# [#130] Fix: API 러너가 save_reports 호출 누락

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/130
- 브랜치: `fix/130-api-save-reports`
- 작업 기간: 2026-11-04

## 치명적 버그

웹에서 실행한 run 은 **디스크에 리포트가 저장되지 않음**.

- CLI (`cli/run.py`) 는 완료 후 `graph.save_reports(final_state, ticker)` 를 직접 호출
- API 러너 (`api/runner.py:69`) 는 `graph.propagate(...)` 만 호출하고 반환값 `(final_state, rating)` 을 **버림**

결과:
- Task 14e (#110) run 은 결정만 받고 상세 리포트 접근 불가
- Task 14f (#111) 리포트 뷰어가 디스크를 소스 오브 트루스로 쓰므로 웹 run 은 뷰어에 안 보임
- Task 14f 다운로드 (#128) 도 저장된 게 없으니 동작 불가
- **Task 14 에픽 (#105) 이 실질적 사용 불가 상태였음**

## 수정

### `api/runner.py`
propagate 반환값을 받아 `save_reports` 호출. 저장 성공 시 `report_saved` SSE 이벤트 발화 — 프론트가 완료 후 `/report?id=...` 로 자동 라우팅 가능.

### 테스트 — `tests/test_api_runs.py`
- 신규 `test_runner_calls_save_reports_on_success` — mock graph 가 save_reports 호출 받는지 검증
- 기존 3개 fake graph 에 `save_reports` no-op 추가

## 검증

- `pytest tests/test_api_runs.py -v` → **8 passed**
- `pytest -q` 전수 → **909 passed, 11 deselected**
- `ruff check .` → clean
