# [#2] Task 1a: ChatClaudeCodeHeadless 기본 subprocess 래퍼

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/2
- PR: (작업 완료 후 추가)
- 상위 에픽: #1
- 브랜치: `feat/2-claude-code-adapter-basic-wrapper`
- 작업 기간: 2026-11-02 ~

## 범위

LangChain `BaseChatModel` 을 상속하는 `ChatClaudeCodeHeadless` 클래스의 기본 골격. `claude -p` subprocess 를 호출하고 결과 JSON 을 LangChain `AIMessage` 로 반환하는 최소 동작까지만.

이후 하위 이슈에서 추가될 기능 (여기서는 포함하지 않음):
- #4 격리 플래그 전체 세트 (`--disable-slash-commands`, `--exclude-dynamic-system-prompt-sections`, `--append-system-prompt`)
- #5 동시 실행 세마포어
- #6 타임아웃·재시도·429 처리
- #7 모델 티어 매핑 (deep/quick, effort)
- #8 factory.py / api_key_env.py 통합
- #9 `--bare` escape hatch

## 사전 확인

`claude -p "say exactly: pong" --output-format json --no-session-persistence --permission-mode plan` 실제 응답 JSON 구조 확인:

```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "result": "pong",
  "session_id": "<uuid>",
  "stop_reason": "end_turn",
  "duration_ms": 769,
  ...
}
```

파싱 대상 필드: `result` (응답 텍스트), `is_error` (오류 플래그), `subtype` (에러 종류 식별), `session_id` (디버깅용).

## 수행한 변경

- `tradingagents/llm_clients/claude_code_client.py` 신규 (약 100줄)
  - `_messages_to_prompt(messages)`: LangChain 메시지 리스트 → 역할 접두사(System/User/Assistant) 포맷의 단일 프롬프트 문자열
  - `ChatClaudeCodeHeadless(BaseChatModel)`: LangChain BaseChatModel 서브클래스
    - `_llm_type` → `"claude-code"`
    - `_generate()` → `subprocess.run(["claude", "-p", prompt, "--output-format", "json", "--model", <sonnet|opus|haiku>, "--no-session-persistence", "--permission-mode", "plan"])` 호출 → JSON 파싱 → `ChatResult`
    - `is_error=True` 응답 시 `RuntimeError` 발생
  - `ClaudeCodeClient(BaseLLMClient)`: TradingAgents 어댑터 래퍼
    - `get_llm()` → `ChatClaudeCodeHeadless` 인스턴스 반환
    - `validate_model()` → `{sonnet, opus, haiku}` 집합 체크
- `tests/test_claude_code_client.py` 신규 (약 130줄, 9개 테스트)
- `work_history/2026-11-02-2-claude-code-adapter-basic-wrapper.md` 신규 (이 파일)

## 설계 결정 변경 사항

없음. code_artifact.md Task 1 과 이슈 #2 범위 내 작업.

몇 가지 의도적으로 Task 1a 범위에 포함하지 않은 격리 플래그 (`--disable-slash-commands`, `--exclude-dynamic-system-prompt-sections`, `--append-system-prompt`) 는 Task 1c (#4) 로 미룸.

## 검증 결과

- `pytest tests/test_claude_code_client.py -v` → **9 passed in 1.46s**
  - 역할 접두사 포맷팅
  - 비문자열 content 처리 (langchain 의 list-form 메시지)
  - `_llm_type` 값
  - 응답 성공 경로 (`result` → `AIMessage.content`)
  - CLI 인자 전달 (model, output-format, no-session-persistence, permission-mode plan)
  - 프롬프트 안에 메시지 텍스트 포함
  - `is_error=True` → `RuntimeError`
  - 클라이언트 래퍼 → 어댑터 인스턴스
  - 모델 유효성 검증
- `ruff check tradingagents/llm_clients/claude_code_client.py tests/test_claude_code_client.py` → **All checks passed**
- **수동 smoke test** (실제 `claude` CLI 호출):
  ```python
  llm = ChatClaudeCodeHeadless(model='haiku')
  llm.invoke([HumanMessage(content='say exactly: smoke-ok')]).content
  # → 'smoke-ok'
  ```
  정상 응답. 어댑터가 실제 subprocess 경로에서도 동작 확인.

## 다음 작업 핸드오프

Task 1b (#3) `with_structured_output → --json-schema 매핑` 이 바로 이어지는 자연 후속. `ChatClaudeCodeHeadless._generate()` 가 완성되어 있어 그 위에 `with_structured_output` 을 추가로 올리면 됨.

주의 사항:
- `_messages_to_prompt` 의 역할 접두사 처리는 지금은 단순하지만 Task 1c (#4) 에서 `--append-system-prompt` 와 조화를 이루도록 재검토 필요 (System 메시지를 인라인이 아니라 플래그로 분리).
- 현재는 `subprocess.run(..., check=True)` 로 non-zero exit 를 그대로 전파. Task 1e (#6) 에서 재시도 로직 추가 시 `check=False` 로 바꾸고 수동으로 returncode 처리.
