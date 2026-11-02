# [#9] Task 1h: Escape hatch TRADINGAGENTS_CLAUDE_BARE=1

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/9
- PR: (작업 완료 후 추가)
- 상위 에픽: #1
- 브랜치: `feat/9-bare-escape-hatch`
- 작업 기간: 2026-11-02 ~

## 범위

디버깅/테스트 상황에서 Claude Code 를 `--bare` 모드 + `ANTHROPIC_API_KEY` 로 운영할 수 있는 escape hatch. 결정론이 중요한 상황에서만 사용하도록 디폴트는 OFF.

## 수행한 변경

### `tradingagents/llm_clients/claude_code_client.py`

- `_BARE_ENV = "TRADINGAGENTS_CLAUDE_BARE"` 상수 신규.
- `_ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"` 상수 신규.
- `_bare_mode_enabled()` 신규: 환경변수 값이 **정확히 `"1"`** 일 때만 True. `true`/`yes`/`on` 같은 느슨한 매칭은 거부 — 오타로 켜지는 사고 방지.
- `_validate_bare_prereqs()` 신규: bare 모드 활성 시 `ANTHROPIC_API_KEY` 가 공백/미설정인 경우 즉시 `RuntimeError` 로 명확히 실패. subprocess 호출 전에 어댑터 레벨에서 선검증 — Claude Code 의 "No API key" 에러보다 운영 디버깅에 유리.
- `_base_cli_args`: 격리 플래그 뒤에 bare 분기 추가.
  ```
  if _bare_mode_enabled():
      _validate_bare_prereqs()
      args.append("--bare")
  ```
  - `_generate` 와 `_StructuredClaudeCode.invoke` 양쪽 경로에서 자동 적용.
  - 다른 격리 플래그 (`--permission-mode`, `--no-session-persistence`, `--disable-slash-commands`, `--exclude-dynamic-system-prompt-sections`) 는 유지 — bare 모드가 이것들을 자동 처리하지는 않거나 (예: slash-commands 는 bare 모드에서도 여전히 로드됨), 중복이 해를 끼치지 않음.

### `tests/test_claude_code_client.py`

Task 1h 테스트 10개 추가:
- `_bare_mode_enabled`: 디폴트 OFF, `"1"` 매칭, 느슨한 매칭 거부 (`"true"`, `"yes"`, `"on"`, `"True"`, `"01"`, `" 1 "` 전부 False)
- `_validate_bare_prereqs`: 키 설정 시 통과, 미설정/공백 시 RuntimeError
- CLI 인자: 디폴트 OFF 시 `--bare` 없음, 환경변수 ON + 키 있을 때 `--bare` 있음
- 어댑터 선검증: bare 모드 ON + 키 없음 → `_generate` 호출 시점에서 RuntimeError (subprocess 호출 전)
- structured 경로도 동일하게 `--bare` 적용

## 설계 결정 변경 사항

없음. 이슈 #9 와 code_artifact.md Task 1 명세대로.

**엄격한 "1" 매칭 선택 이유:** 환경변수를 `TRADINGAGENTS_CLAUDE_BARE=true` 로 적으면 느슨한 매칭이면 True 가 되는데, 이 플래그는 OAuth 를 끄고 API 키 운영으로 전환하는 큰 전환이라 오타/실수로 켜지면 사용자가 혼란스러워진다. 매뉴얼하게 `=1` 을 적어야만 켜지도록 엄격화.

**다른 격리 플래그를 bare 모드에서도 유지하는 이유:** Claude Code help 문서는 `--bare` 가 "skip hooks, LSP, plugin sync, attribution, auto-memory, background prefetches, keychain reads, CLAUDE.md auto-discovery" 라고 명시. SKILLS/slash-commands 는 `/skill-name` 으로 여전히 해결 가능 — `--disable-slash-commands` 는 bare 모드에서도 유용. 중복으로 인한 CLI 거부 사례도 테스트에서 확인 안 됨.

## 검증 결과

- `pytest tests/test_claude_code_client.py -v` → **73 passed in 1.04s** (Task 1a 9 + 1b 13 + 1c 5 + 1d 8 + 1e 20 + 1f 8 + 1h 10)
- `pytest -q` 전체 스위트 → **1485 passed, 1 skipped**
- `ruff check` → **All checks passed**

## 다음 작업 핸드오프

Task 1g (#8) 는 대부분이 Task 1f 에서 선반영됨 — 남은 작업은 `tradingagents/llm_clients/__init__.py` 공개 심볼 정리 정도. Task 1 에픽 완료까지 가볍게 마무리 가능.

Task 1i (#10) 는 실제로는 이 PR 들을 통해 **진행 중 커버되어 왔음**. 73개 유닛 테스트 + 전체 스위트 1485 passed 상태. 하위 이슈 자체는 "커버리지 >= 90%" 같은 체크리스트 수준의 집계 역할만 남음.
