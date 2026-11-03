# [#114] 핫픽스: `test_memory_as_of_gates_historical_but_not_live` TZ 불일치

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/114
- PR: (작업 완료 후 추가)
- 브랜치: `fix/114-memory-as-of-tz`
- 작업 기간: 2026-11-04

## 증상

PR #113 (Task 14a) CI 에서 `tests/test_memory_pointintime.py::test_memory_as_of_gates_historical_but_not_live` 가 UTC TZ job (py3.11 / py3.13 / py3.14) 에서 실패. `py3.12 (Asia/Seoul)` job 과 로컬 (KST) 은 통과.

```
AssertionError: assert '2026-11-03' is None
 +  where '2026-11-03' = _memory_as_of('2026-11-03')
```

## 원인

- 프로덕션 코드 `is_historical()` 는 `date_window.get_current_date()` 를 사용해 **KST** 기준 오늘을 결정 (Task 8 #74, 2026-11-02 머지)
- 테스트의 `today = datetime.now().strftime("%Y-%m-%d")` 는 **시스템 로컬 TZ** 기준
- CI UTC job 에서 KST 자정 직후 (예: 11-04 09:23 KST = 11-04 00:23 UTC) 시점에 두 값이 1일 차이 (`"2026-11-03"` vs `"2026-11-04"`) → `is_historical("2026-11-03")` True → `_memory_as_of` 가 날짜 반환 → 테스트 fail

## 수정

테스트가 production code 와 **같은 KST 기준 오늘** 을 사용하도록 교체:

```python
from tradingagents.dataflows.date_window import get_current_date
today = get_current_date()
future = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
```

프로덕션 코드 무변경. KST 결정은 Task 8 (#74) 의 설계 결정이고 그대로 유지하는 것이 맞음.

## 검증 결과

- `pytest tests/test_memory_pointintime.py -v` → **6 passed** (로컬 KST)
- `TZ=UTC pytest tests/test_memory_pointintime.py::test_memory_as_of_gates_historical_but_not_live -v` → **1 passed** (UTC 시뮬레이션)
- `ruff check tests/test_memory_pointintime.py` → All checks passed

## 다음 작업 핸드오프

- 이 핫픽스 머지 후 PR #113 (Task 14a) rebase → 모든 CI job 녹색 예상
