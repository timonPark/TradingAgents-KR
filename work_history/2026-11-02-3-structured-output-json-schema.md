# [#3] Task 1b: with_structured_output → --json-schema 매핑

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/3
- PR: (작업 완료 후 추가)
- 상위 에픽: #1
- 브랜치: `feat/3-structured-output-json-schema`
- 작업 기간: 2026-11-02 ~

## 범위

Task 1a 에서 작성한 `ChatClaudeCodeHeadless` 위에 `with_structured_output(Schema)` 를 추가해 Pydantic 스키마 기반 구조화 출력을 지원합니다. Portfolio Manager / Trader / Research Manager 가 이 경로를 사용합니다 (`tradingagents/agents/structured.py`).

## 사전 확인 (중요 발견)

`claude -p ... --json-schema <schema>` 실제 호출로 응답 구조를 확인한 결과:

```json
{
  "result": "",                                       ← 비어있음
  "structured_output": {"action": "BUY", "reason": "..."},  ← 여기에 데이터
  "is_error": false,
  ...
}
```

**중요:** `--json-schema` 사용 시 Claude Code 는 응답을 `result` 가 아니라 **`structured_output` 필드**에 담습니다. Task 1a 에서 가정한 "result 필드에서 응답 추출" 과 다른 경로입니다. 구현에 반영.

## 수행한 변경

### `tradingagents/llm_clients/claude_code_client.py`

- `_coerce_input_to_messages(input)` 신규: str / list[BaseMessage] / PromptValue 세 종류 입력을 BaseMessage 리스트로 통일.
- `_run_claude_subprocess(args)` 신규: subprocess 호출 + JSON 파싱 + is_error 전파를 모듈 수준 공통 헬퍼로 분리. `_generate()` 와 `_StructuredClaudeCode.invoke()` 양쪽에서 재사용.
- `ChatClaudeCodeHeadless._base_cli_args(prompt)` 신규: 구조화/비구조화 호출의 공통 CLI 인자 (model, output-format, no-session-persistence, permission-mode) 를 메서드로 추출. structured 경로는 여기에 `--json-schema <json>` 만 추가.
- `ChatClaudeCodeHeadless.with_structured_output(schema, **kwargs)` 신규:
  - LangChain `BaseChatModel.with_structured_output` 호환 시그니처.
  - Pydantic 스키마를 `model_json_schema()` 로 JSON Schema 변환.
  - `_StructuredClaudeCode` 인스턴스 반환.
- `_StructuredClaudeCode` 신규: `.invoke(input)` 호출 시 subprocess 호출 → `structured_output` 필드에서 Pydantic 인스턴스 복원.
- `_parse_structured_output(payload, schema)` 신규: payload의 `structured_output` 을 Pydantic 인스턴스로 복원. 복원 실패 (필드 없음, dict 아님, 스키마 위반) 시 `None` 반환 — `structured.py` 의 free-text 폴백 경로가 작동하도록.

### `tests/test_claude_code_client.py`

Task 1b 테스트 13개 추가 (전체 22개). 커버리지:
- `_coerce_input_to_messages`: str, list, PromptValue 세 경로
- `_parse_structured_output`: 정상, structured_output 필드 없음, dict 아님, 스키마 위반
- `with_structured_output.invoke`: 정상 응답, --json-schema 인자 포함, 입력 세 종류 수용, 폴백 (None 반환), is_error 전파

## 설계 결정 변경 사항

code_artifact.md Task 1 명세와 일치. 다만 **중요한 구현 세부 하나 발견/반영**:

- 당초 계획: "응답 JSON 의 `result` 를 Pydantic 인스턴스로 복원"
- 실제 CLI 동작: `--json-schema` 모드에서는 `result` 가 비어있고 `structured_output` 필드에 Pydantic 복원용 dict 가 담김
- 이슈 #3 본문의 설명 ("응답 JSON 의 result 를 Pydantic 인스턴스로 복원") 은 실제와 다르므로 PR 설명에서 명시.

## 검증 결과

- `pytest tests/test_claude_code_client.py -v` → **22 passed in 0.40s** (Task 1a 9개 + Task 1b 13개)
- `ruff check tradingagents/llm_clients/claude_code_client.py tests/test_claude_code_client.py` → **All checks passed** (auto-fix 1회: forward reference 인용부호 제거)
- **End-to-end smoke test** (실제 `claude` CLI + 삼성전자 종목코드):
  ```python
  class Decision(BaseModel):
      action: Literal["BUY","SELL","HOLD"]
      reason: str

  llm = ChatClaudeCodeHeadless(model="haiku")
  result = llm.with_structured_output(Decision).invoke(
      "Return a trade decision for ticker 005930 (Samsung Electronics). action and brief reason."
  )
  # → Decision(action='HOLD', reason='삼성전자(005930)는 메모리 반도체 업사이클 수혜 기대에도 불구하고...')
  ```
  Pydantic 인스턴스 정상 복원, 한국어 reason 포함.

## 다음 작업 핸드오프

이 PR 머지 후 Task 1c (#4) 격리 플래그 추가로 진행. 지금은 어댑터가 `--no-session-persistence` 와 `--permission-mode plan` 만 적용하고 있어, `--disable-slash-commands` / `--exclude-dynamic-system-prompt-sections` / `--append-system-prompt` 가 아직 미적용. Task 1c 에서 `_base_cli_args()` 에 추가.
