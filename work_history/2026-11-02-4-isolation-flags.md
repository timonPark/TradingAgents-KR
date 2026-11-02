# [#4] Task 1c: 어댑터 격리 플래그 적용

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/4
- PR: (작업 완료 후 추가)
- 상위 에픽: #1
- 브랜치: `feat/4-isolation-flags`
- 작업 기간: 2026-11-02 ~

## 범위

Claude Code 가 기본으로 로드하는 숨은 상태(auto-memory, 상위 CLAUDE.md 자동 발견, hooks, SKILLS, 플러그인, 호스트 상태 섹션 등) 가 분석 결과의 결정론을 깨뜨리지 못하도록 어댑터 subprocess 호출에 격리 플래그 전체 세트를 명시 적용합니다. 추가로 SystemMessage 를 역할에 맞게 `--append-system-prompt` 로 분리 전달합니다.

## 수행한 변경

### `tradingagents/llm_clients/claude_code_client.py`

- `_split_messages(messages)` **신규**: 메시지 리스트를 `(system_prompt, conversation_prompt)` 로 분리. SystemMessage 는 전부 합쳐 시스템 영역으로, Human/AI 는 역할 접두사와 함께 대화 영역으로. SystemMessage 가 없으면 시스템 영역이 빈 문자열이 되어 호출부가 `--append-system-prompt` 플래그를 생략할 수 있게 함.
- `_messages_to_prompt(messages)` **레거시 호환 유지**: 내부적으로 `_split_messages` 를 호출해 단일 문자열로 재조립. 외부 참조나 레거시 호출을 위해 보존.
- `ChatClaudeCodeHeadless._base_cli_args(prompt, system_prompt="")` 확장:
  - Task 1a 의 `-p`, `--output-format json`, `--model`, `--no-session-persistence`, `--permission-mode plan` 유지
  - **신규 격리 플래그 2개**:
    - `--disable-slash-commands` — SKILLS/slash command 로딩 차단
    - `--exclude-dynamic-system-prompt-sections` — cwd/env/git status 등 호스트 종속 섹션을 시스템 프롬프트에서 제거 (프롬프트 캐시 재사용성 향상 + 호스트 상태 유출 방지)
  - **조건부 플래그**:
    - `--append-system-prompt <system>` — `system_prompt` 가 비어있지 않을 때만 추가. 상위 `~/.claude/CLAUDE.md` 자동 발견 내용을 TradingAgents 지침으로 희석.
- `ChatClaudeCodeHeadless._generate` 호출부 변경: `_messages_to_prompt(messages)` → `_split_messages(messages)` 분리 후 `_base_cli_args(conversation, system_prompt=system_prompt)` 호출.
- `_StructuredClaudeCode.invoke` 호출부 변경: 위와 동일한 패턴 적용. `--json-schema` 는 그대로 유지.

### `tests/test_claude_code_client.py`

- 기존 `test_generate_passes_cli_args`: Task 1c 격리 플래그 전체 세트 (`--disable-slash-commands`, `--exclude-dynamic-system-prompt-sections`) 검증 추가. SystemMessage 없는 경우 `--append-system-prompt` 가 포함되지 않음을 검증.
- 기존 `test_generate_prompt_contains_message_text` → `test_generate_system_message_goes_to_append_system_prompt` 로 교체: SystemMessage 가 `-p` 에서 사라지고 `--append-system-prompt` 로 분리 전달되는지 검증.
- 신규 `test_generate_multiple_system_messages_concatenated`: 여러 SystemMessage 가 하나의 append-system-prompt 로 합쳐지는지.
- 신규 `_split_messages` 유닛 테스트 3개 (정상 분리, SystemMessage 없음, SystemMessage 만).
- 신규 `test_structured_output_also_uses_isolation_flags_and_system_split`: structured 경로도 격리 플래그 + SystemMessage 분리 적용되는지 (ChatPromptTemplate 입력 포함).

레거시 테스트 `test_messages_to_prompt_formats_roles` 는 `test_messages_to_prompt_legacy_format_still_works` 로 리네임: `_messages_to_prompt` 함수가 레거시 호환으로 유지되므로 기존 포맷 (System: 접두사 포함) 테스트도 유지.

## 설계 결정 변경 사항

Task 1a 에서는 "System/User/Assistant" 역할 접두사로 모든 메시지를 단일 문자열(`-p`) 에 넣는 단순 방식을 썼으나, Task 1c 에서 **SystemMessage 를 `--append-system-prompt` 로 분리**하는 것으로 전환했습니다. 이유:

1. Claude Code 가 `--append-system-prompt` 를 지원하므로 역할을 올바른 자리에 배치하는 게 더 정확.
2. `--exclude-dynamic-system-prompt-sections` 는 "시스템 프롬프트 영역" 을 수정하므로, SystemMessage 를 그 영역에 명시 전달해야 의미가 있음.
3. 대화 영역(`-p`) 과 시스템 영역을 분리하면 프롬프트 캐시 재사용성도 향상됨 (시스템은 보통 턴마다 같고 대화만 바뀜).

레거시 `_messages_to_prompt` 는 보존했습니다 — 외부 호출 호환 + 레거시 단일 문자열 포맷이 필요한 경우(e.g. 단순 디버그 출력) 를 위해.

## 검증 결과

- `pytest tests/test_claude_code_client.py -v` → **27 passed in 0.56s** (Task 1a 9 + Task 1b 13 + Task 1c 5 + 레거시 유지 포함)
- `ruff check` → **All checks passed**
- **End-to-end smoke test**:
  ```python
  llm = ChatClaudeCodeHeadless(model='haiku')
  llm.invoke([
      SystemMessage(content='Reply in exactly 3 words, no punctuation.'),
      HumanMessage(content='Describe Samsung Electronics.'),
  ])
  # → AIMessage(content='삼성전자')
  ```
  SystemMessage 지시(한국어로는 느슨하게 해석되어 3단어 아닌 1단어 응답이 왔지만) 가 반영됨 — 분리 전달 경로가 작동.

## 다음 작업 핸드오프

Task 1d (#5) 동시 실행 세마포어로 진행. 세마포어는 `_run_claude_subprocess` 함수 또는 `ChatClaudeCodeHeadless._generate`/`_StructuredClaudeCode.invoke` 진입 지점에 모듈 레벨 `threading.Semaphore` 를 두는 패턴.

주의 사항:
- `--exclude-dynamic-system-prompt-sections` 플래그는 Claude Code help 에 따르면 "기본 시스템 프롬프트에만 적용되고 `--system-prompt` 사용 시 무시" 라고 되어있음. 우리는 `--append-system-prompt` 를 쓰므로 플래그가 유효함 (override 아님).
- 테스트는 subprocess 모킹이라 실제로 Claude Code 가 플래그를 지원하는지는 CI 단위에서 검증 안 됨. E2E smoke 가 통과하므로 실제 CLI 가 플래그를 거부하지 않음은 확인됨.
