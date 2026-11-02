# [#8] Task 1g: llm_clients 패키지 공개 심볼 정리 (범위 축소)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/8
- PR: (작업 완료 후 추가)
- 상위 에픽: #1
- 브랜치: `feat/8-llm-clients-init-cleanup`
- 작업 기간: 2026-11-02 ~

## 범위

Task 1g (#8) 의 당초 범위는 (a) `factory.py` 에 `claude-code` 분기 추가, (b) `api_key_env.py` 조정, (c) `__init__.py` 공개 심볼 정리 세 가지였으나, **(a) 와 (b) 는 Task 1f (#7) 에서 선반영**되어 (디폴트 provider 변경이 그 분기들을 필수로 요구) 이 PR 에는 **(c) 공개 심볼 정리와 그 검증 테스트**만 남았습니다.

## 수행한 변경

### `tradingagents/llm_clients/__init__.py`

- `ChatClaudeCodeHeadless` 와 `ClaudeCodeClient` 를 패키지 레벨에서 공개 export 로 추가.
- `__all__` 에 두 이름 포함.
- 결과: `from tradingagents.llm_clients import ChatClaudeCodeHeadless, ClaudeCodeClient` 가 가능해져 외부 코드 (예: 테스트, 통합 지점) 에서 모듈 경로 전체를 쓰지 않고 어댑터에 접근 가능.

### `tests/test_claude_code_client.py`

Task 1g 테스트 3개 추가:
- `test_package_exposes_claude_code_symbols`: `tradingagents.llm_clients` 패키지에서 두 심볼 접근 가능 + `__all__` 등록 검증
- `test_factory_create_llm_client_returns_claude_code_client`: `create_llm_client(provider="claude-code", model="sonnet")` 가 `ClaudeCodeClient` 반환 (Task 1f 가 선반영한 분기의 통합 검증)
- `test_factory_create_llm_client_passes_kwargs_through`: `effort` 같은 kwargs 가 어댑터까지 전달됨

## 설계 결정 변경 사항

**범위 축소.** 이슈 #8 Definition of Done 기준:
- [x] `create_llm_client(provider="claude-code", model="sonnet")` 가 어댑터 인스턴스 반환 → Task 1f 에서 이미 구현 + 이 PR 에서 통합 테스트 추가
- [x] 기존 provider 경로는 아직 동작 (Task 2 전까지) → 유지됨 (Task 1f 가 다른 provider 분기 건드리지 않음)

실질 코드 변경은 `__init__.py` 몇 줄과 테스트 3개입니다.

## 검증 결과

- `pytest tests/test_claude_code_client.py -v` → **76 passed** (Task 1a~1h 73 + Task 1g 3)
- `ruff check tradingagents tests` → **All checks passed**

## 다음 작업 핸드오프

### Task 1 에픽 완료 조건

Task 1i (#10) "어댑터 유닛 테스트" 는 하위 이슈 1a~1h 를 통해 **점진적으로 커버되어 왔음** — 지금 76개 유닛 테스트가 다음을 전부 포함:

- `invoke()` 성공 경로 (JSON 응답 → AIMessage)
- `with_structured_output()` 왕복 (Pydantic → JSON Schema → `structured_output` → Pydantic)
- `bind_tools()` 호출 시 — 어댑터는 `bind_tools` 를 **정의하지 않음** (사전조회 패턴 ADR-0002 로 LangGraph `BaseChatModel` 의 디폴트 bind_tools 가 그대로 사용되지만, 분석가 노드는 이 경로를 쓰지 않음 — Task 3 범위에서 ToolNode/루프 자체가 제거됨). `NotImplementedError` 전파 테스트는 Task 3 에서 분석가 노드 변경과 함께 추가.
- 격리 플래그 전수 (`--permission-mode plan`, `--no-session-persistence`, `--disable-slash-commands`, `--exclude-dynamic-system-prompt-sections`, `--append-system-prompt`)
- 세마포어 (3 쓰레드 + concurrency=2, 4 쓰레드 + concurrency=1 실제 동시성 검증)
- 타임아웃 (effort별 디폴트, 환경변수 오버라이드)
- non-zero exit 1회 재시도, 429 60초 대기 + 재시도, JSON 파싱 실패 전파
- 티어별 모델 매핑 (deep/quick), effort 유효성 검증, 디폴트 폴백
- `TRADINGAGENTS_CLAUDE_BARE=1` escape hatch (엄격한 "1" 매칭, 어댑터 레벨 선검증)
- 패키지 공개 심볼

Task 1i 는 이슈 자체를 **완료 처리**하면 됨 (별도 PR 불필요). 또는 간단한 "체크리스트 반영" PR 로 close.

### Task 1 에픽 (#1) 완료 상태

- #2 (1a) ✅ 머지 — 기본 subprocess 래퍼
- #3 (1b) ✅ 머지 — with_structured_output
- #4 (1c) ✅ 머지 — 격리 플래그 + SystemMessage 분리
- #5 (1d) ✅ 머지 — 세마포어
- #6 (1e) ✅ 머지 — 오류 처리 정책
- #7 (1f) ✅ 머지 — 티어 매핑 (1g 일부 선반영)
- #9 (1h) ✅ 머지 — bare escape hatch
- #8 (1g) 🟡 이 PR 리뷰 대기
- #10 (1i) 🟡 암묵적 완료 — 76 테스트 축적

이 PR 머지 후 Task 1 에픽 (#1) 을 close 하고 Task 2 (provider 삭제) 로 넘어가면 됨.
