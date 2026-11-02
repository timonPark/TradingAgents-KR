# [#22+#23+#27] Task 2a+2b+2c: provider 삭제 + factory 축소 + CLI 정리

- 이슈: #22 (Task 2a), #23 (Task 2b), #27 (Task 2c)
- PR: (작업 완료 후 추가)
- 상위 에픽: #21
- 브랜치: `feat/22-provider-client-cleanup`
- 작업 기간: 2026-11-02 ~

## 범위

세 개의 하위 이슈를 하나의 PR 로 묶었습니다 — 파일 삭제(2a), factory 축소(2b), CLI 정리(2c) 가 **원자적**으로 가야 main 이 깨지지 않기 때문입니다. 사용자 승인 하에 진행.

## 수행한 변경

### Task 2a: provider 클라이언트 소스 + 테스트 삭제

**삭제된 소스 (9개):**
- `tradingagents/llm_clients/anthropic_client.py`
- `tradingagents/llm_clients/openai_client.py`
- `tradingagents/llm_clients/google_client.py`
- `tradingagents/llm_clients/azure_client.py`
- `tradingagents/llm_clients/bedrock_client.py`
- `tradingagents/llm_clients/chatgpt_auth.py`
- `tradingagents/llm_clients/capabilities.py`
- `tradingagents/llm_clients/model_catalog.py`
- `tradingagents/llm_clients/validators.py`

**삭제된 테스트 (22개):**
- Provider: `test_anthropic_effort.py`, `test_azure_client.py`, `test_bedrock_provider.py`, `test_chatgpt_auth.py`, `test_chatgpt_provider.py`, `test_deepseek_reasoning.py`, `test_google_api_key.py`, `test_google_thinking_level.py`, `test_minimax.py`, `test_openai_compatible_provider.py`, `test_openai_reasoning_effort.py`, `test_openai_responses_base_url.py`, `test_openrouter_model_select.py`, `test_ollama_base_url.py`, `test_provider_registry.py`, `test_tier_providers.py`, `test_model_validation.py`, `test_capabilities.py`
- 외부 LLM 공통: `test_api_key_env.py`, `test_llm_max_retries.py`, `test_llm_max_tokens.py`, `test_temperature_config.py`

**유지:** `base_client.py`, `claude_code_client.py`, `factory.py`, `api_key_env.py`, `__init__.py` 만 `llm_clients/` 에 남음.

### Task 2b: factory.py 축소

`tradingagents/llm_clients/factory.py` 가 180줄 → 80줄 수준으로 축소:
- `OPENAI_COMPATIBLE_PROVIDERS` 레지스트리, `is_openai_compatible`, `check_endpoint`, `REASONING_EFFORT_PROVIDERS`, `_is_native_openai_base_url`, `ProviderSpec` dataclass 전부 삭제
- `_coerce_max_retries`, `_coerce_max_tokens`, `_PASSTHROUGH_KWARGS` 삭제 (Claude Code 자체 처리)
- `create_llm_client`: provider 가 `claude-code` 가 아니면 명확한 `ValueError` 로 거부
- `build_llm_kwargs`: `claude-code` 분기만 남김 (`effort` 추출)
- `tier_provider`: 항상 `claude-code` 반환
- `create_tier_client`: `backend_url` 로직 제거, 티어별 effort 매핑만 유지

### Task 2c: CLI provider 선택 흐름 제거

**`cli/prompts.py` (790줄 → 320줄):**
- 삭제: `_llm_provider_table`, `select_llm_provider`, `provider_default_url`, `resolve_backend_url`, `prompt_openai_compatible_url`
- 삭제: `ask_glm_region`, `ask_qwen_region`, `ask_minimax_region`, `confirm_ollama_endpoint`
- 삭제: `ask_openai_reasoning_effort`, `ask_anthropic_effort`, `ask_gemini_thinking_config`
- 삭제: `select_chatgpt_model`, `select_openrouter_model`, `_fetch_openrouter_models`, `_select_listed_model`, `LISTED_LIVE`
- 삭제: `ensure_signed_in`, `ensure_api_key`, `_OPENROUTER_MAINSTREAM`
- 변경: `_select_model(provider, mode)` → `_select_model(mode)` + Claude 모델 리스트 (sonnet/opus/haiku/custom)
- 변경: `select_shallow_thinking_agent` / `select_deep_thinking_agent` 가 provider 인자 없이 동작
- 신규: `ask_effort(mode, default)` — Claude Code `--effort` 레벨 선택 UI
- 변경: `ask_output_language` 디폴트가 Korean 으로 변경
- 변경: 티커 예시 문자열 한국 종목코드 (005930 등) 로 교체

**`cli/selections.py` (384줄 → 215줄):**
- 삭제: provider 선택 (Step 6), region 선택, backend_url 로직, `_check_tier_providers`
- 삭제: 삭제된 `ask_*_effort` 호출부, API 키 pre-check
- 추가: Step 7a/7b (deep/quick effort 선택) — `TRADINGAGENTS_EFFORT` / `TRADINGAGENTS_QUICK_EFFORT` 로 각각 skip 가능
- Welcome 박스: TradingAgents-KR + Claude Code 백엔드 명시로 변경
- `unattended_gaps`: `TRADINGAGENTS_LLM_PROVIDER` 삭제

**`cli/prefs.py` (94줄 → 95줄, 로직 단순화):**
- 삭제: `_llm_provider_table`, `get_model_options` 참조
- `REMEMBERED`: `llm_provider`, `backend_url` 제거, `effort`, `quick_effort` 추가
- `sanitize`: provider table 검증 삭제. 모델 ID 는 자유 텍스트로 유지, effort 는 알려진 레벨 (`low/medium/high/xhigh/max`) 만 유지.

**`cli/main.py`:**
- 삭제: `login` / `logout` typer 명령 (ChatGPT 플랜 로그인), `SIGNED_IN_PROVIDERS`, `Plan` StrEnum, `chatgpt_auth` import

**`cli/run.py`:**
- `_build_run_config`: `backend_url`, `google_thinking_level`, `openai_reasoning_effort`, `anthropic_effort` 삭제
- `llm_provider = "claude-code"` 하드코딩
- 신규: `effort`, `quick_effort` 전달
- `output_language` 디폴트가 English → Korean 으로 변경

### 테스트 보강

CLI 변경 반영:
- `tests/test_cli_env_skip.py`: 전면 재작성 — `TestProviderDefaultUrl` 삭제, `TestReasoningEffortSkippedFromEnv` → `TestEffortSkippedFromEnv` (effort/quick_effort env skip)
- `tests/test_cli_prefs.py`: SAVED 딕셔너리를 Claude Code 모델 + effort 로 교체, provider/backend_url 테스트 삭제, effort 유효성 테스트 추가
- `tests/test_cli_headless.py`: UNATTENDED_ENV 를 Claude Code 모델 + effort 로 교체, tier provider 관련 테스트 4개 삭제, 티커 예시 005930 으로
- `tests/test_cli_config_precedence.py`: SELECTIONS 를 claude-code 모양으로 교체, GLM/thinking 테스트 2개 삭제
- `tests/test_cli_commands.py`: login/logout 테스트 4개 삭제
- `tests/test_cli_updates.py`: ENV 를 Claude Code 모양으로 교체, `ensure_api_key` 모킹 삭제

## 설계 결정 변경 사항

### 범위 확장 (사용자 승인)

이슈 2a 는 공식적으로는 "파일 삭제만" 이지만, source 파일을 삭제하면 CLI 와 factory 가 즉시 import 실패하는 것이 밝혀졌습니다. 사용자 승인 하에 Task 2a+2b+2c 를 하나의 원자적 PR 로 묶었습니다. #22, #23, #27 세 이슈를 함께 close.

### CLI 흐름 재설계

Step 6 (provider 선택) 완전 제거. 기존 8단계 (ticker/date/language/analysts/depth/provider/thinking/effort) 가 7단계 (ticker/date/language/analysts/depth/thinking/effort) 로 축소. provider 는 자동으로 claude-code.

### 테스트 재작성 vs 삭제

code_artifact.md Task 11 (테스트 재작성) 의 하위 범위에 들어가야 할 CLI 테스트 재작성을 **지금 함께 처리** 했습니다 — PR 범위상 깨진 테스트를 두면 CI 가 빨간 상태로 머지되어야 하는데 이는 CLAUDE.md 금지. Task 11 은 vendor 신규 테스트에 집중.

## 검증 결과

- `pytest -q` → **1160 passed, 8 subtests passed** (Task 1 이전 1485 → 325 감소 — 삭제된 테스트 반영)
- `ruff check tradingagents cli tests` → **All checks passed**
- E2E config 조립:
  ```python
  config = build_default_config()
  # llm_provider=claude-code, deep=sonnet/high, quick=haiku/medium
  quick = create_tier_client(config, 'quick')  # ClaudeCodeClient(model='haiku', effort='medium')
  deep = create_tier_client(config, 'deep')    # ClaudeCodeClient(model='sonnet', effort='high')
  ```

## 다음 작업 핸드오프

- **#24 (2d)**: `pyproject.toml` 의 `langchain-anthropic`, `langchain-openai`, `langchain-google-genai`, `langchain-aws` 의존성 제거
- **#25 (2e)**: `default_config.py` 의 외부 provider 관련 env 매핑 (`TRADINGAGENTS_LLM_PROVIDER`, `TRADINGAGENTS_LLM_BACKEND_URL`, `TRADINGAGENTS_ANTHROPIC_EFFORT`, `TRADINGAGENTS_OPENAI_REASONING_EFFORT`, `TRADINGAGENTS_GOOGLE_THINKING_LEVEL`, `TRADINGAGENTS_TEMPERATURE`, `TRADINGAGENTS_LLM_MAX_RETRIES`, `TRADINGAGENTS_MAX_TOKENS`) 와 디폴트 값 삭제
- **#26 (2f)**: 환경변수/문서 마무리 — `conftest.py` 의 `_API_KEY_ENV_VARS` 축소, README/CHANGELOG 외부 provider 설명 정리
