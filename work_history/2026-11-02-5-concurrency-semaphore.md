# [#5] Task 1d: 동시 실행 세마포어 (TRADINGAGENTS_CLAUDE_CONCURRENCY)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/5
- PR: (작업 완료 후 추가)
- 상위 에픽: #1
- 브랜치: `feat/5-concurrency-semaphore`
- 작업 기간: 2026-11-02 ~

## 범위

LangGraph 가 분석가 노드들을 병렬 실행하거나 백테스트가 여러 종목을 동시에 돌릴 때 Claude Code subprocess 가 무제한으로 생성되지 않도록 **모듈 레벨 세마포어**로 동시 실행을 제한합니다. OAuth Max/Pro 쿼터 소진과 머신 메모리 고갈(Node.js 런타임당 300~500MB)을 보호합니다.

## 수행한 변경

### `tradingagents/llm_clients/claude_code_client.py`

- 환경변수 `TRADINGAGENTS_CLAUDE_CONCURRENCY` (디폴트 `2`) 로 조절되는 모듈 레벨 lazy singleton 세마포어 추가.
- `_resolve_concurrency()`: 환경변수를 읽어 양의 정수로 검증. 부적합 (비정수, 0, 음수) 시 `ValueError` 로 명확히 실패.
- `_get_semaphore()`: double-checked locking 패턴의 lazy singleton. 환경변수는 **첫 호출 시점에만** 평가 — 실행 중인 분석이 동시성 예산을 바꾸는 것을 막기 위함.
- `_reset_semaphore()`: 테스트용 재초기화 헬퍼 (`global _SEMAPHORE = None`). 다음 `_get_semaphore()` 호출 시 환경변수를 다시 읽음.
- `_run_claude_subprocess()` 를 세마포어 `with` 블록으로 감쌈 — 모든 subprocess 호출 경로가 자동으로 세마포어를 지남 (`_generate` 와 `_StructuredClaudeCode.invoke` 양쪽).

### `tests/test_claude_code_client.py`

- autouse 픽스처 `_fresh_semaphore` 추가: 매 테스트마다 환경변수 삭제 + 세마포어 재초기화. 테스트 격리 보장.
- Task 1d 테스트 9개 추가:
  - `_resolve_concurrency` 디폴트, 환경변수 설정, 빈 문자열 폴백, 비정수 거부, 0 거부, 음수 거부
  - 실제 동시성 검증 (3 쓰레드 + concurrency=2 → `max_in_flight <= 2`)
  - 완전 직렬 검증 (4 쓰레드 + concurrency=1 → `max_in_flight == 1`)

## 설계 결정 변경 사항

없음. 이슈 #5 와 code_artifact.md Task 1 명세대로.

**lazy singleton 패턴 채택 이유:** 모듈 import 시점에 환경변수를 읽으면 테스트/CI 에서 pytest fixture 가 환경변수를 설정하기 **전에** 세마포어가 생성되어 디폴트값으로 고정됨. 지연 평가로 "첫 호출 시" 를 보장.

**동시성 환경변수 변경 시 반영 안 함:** 운영 중에 환경변수를 바꿔 쿼터를 늘리는 것은 혼란의 원인이 됨 (일부 호출만 늘어남). 프로세스 시작 시 결정된 값을 끝까지 유지.

## 검증 결과

- `pytest tests/test_claude_code_client.py -v` → **35 passed in 1.00s** (Task 1a 9 + Task 1b 13 + Task 1c 5 + Task 1d 8)
- `ruff check` → **All checks passed**
- 동시성 검증: 쓰레드 기반 테스트로 세마포어가 실제로 호출 수를 제한하는지 확인. 실제 subprocess 를 호출하지는 않지만 `subprocess.run` 모킹에 `sleep(0.1)` 지연을 주입해 겹침을 유도.

## 다음 작업 핸드오프

Task 1e (#6) 오류 처리 정책 (타임아웃·재시도·429). 세마포어는 이미 `_run_claude_subprocess` 안에 자리잡았으므로, 타임아웃/재시도 로직은 세마포어 `with` 블록 **안쪽**에서 돌아가야 함 (하나의 호출이 재시도 중일 때 다른 호출이 이미 쿼터를 밀어내지 못하도록).
