# [#25] Task 2e: default_config.py / api_key_env.py 외부 provider 참조 삭제

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/25
- PR: (작업 완료 후 추가)
- 상위 에픽: #21
- 브랜치: `feat/25-config-env-cleanup`
- 작업 기간: 2026-11-02 ~

## 범위

Config 정의와 API 키 매핑에서 외부 provider 흔적 전면 삭제. 추가로 삭제된 키를 참조하던 downstream (reporting, graph) 과 그 테스트도 함께 정리.

## 수행한 변경

### `tradingagents/default_config.py`

**`_ENV_OVERRIDES` 에서 삭제 (12개 매핑):**
- `TRADINGAGENTS_LLM_PROVIDER` → `llm_provider` (claude-code 고정)
- `TRADINGAGENTS_DEEP_THINK_PROVIDER` → `deep_think_provider`
- `TRADINGAGENTS_QUICK_THINK_PROVIDER` → `quick_think_provider`
- `TRADINGAGENTS_DEEP_THINK_BACKEND_URL` → `deep_think_backend_url`
- `TRADINGAGENTS_QUICK_THINK_BACKEND_URL` → `quick_think_backend_url`
- `TRADINGAGENTS_LLM_BACKEND_URL` → `backend_url`
- `TRADINGAGENTS_TEMPERATURE` → `temperature`
- `TRADINGAGENTS_LLM_MAX_RETRIES` → `llm_max_retries`
- `TRADINGAGENTS_MAX_TOKENS` → `max_tokens`
- `TRADINGAGENTS_GOOGLE_THINKING_LEVEL` → `google_thinking_level`
- `TRADINGAGENTS_OPENAI_REASONING_EFFORT` → `openai_reasoning_effort`
- `TRADINGAGENTS_ANTHROPIC_EFFORT` → `anthropic_effort`

**`build_default_config` 에서 삭제된 config 키 (11개):**
- `backend_url`, `quick_think_provider`, `deep_think_provider`, `quick_think_backend_url`, `deep_think_backend_url`
- `google_thinking_level`, `openai_reasoning_effort`, `anthropic_effort`
- `temperature`, `llm_max_retries`, `max_tokens`

**유지:**
- 데이터 레이어 전용 키 (data_vendors, tool_vendors, benchmark_map, 뉴스 설정)
- Claude Code 티어별 설정 (effort, quick_effort)
- 그래프 설정 (max_debate_rounds 등)

**`output_language` 디폴트 변경:** `"English"` → `"Korean"` (Task 2c 에서 CLI 가 이미 Korean 으로 전환됨 — 이제 DEFAULT_CONFIG 도 harmonize).

### `tradingagents/llm_clients/api_key_env.py`

파일 전체를 `{"claude-code": None}` 하나만 남기도록 축소. 상류의 15개 provider 매핑 제거. 56줄 → 26줄.

### `tradingagents/reporting.py`

리포트 헤더에서 `deep_think_provider`/`quick_think_provider` 참조 제거. 티어별 effort 표시 추가:
```
- TradingAgents 0.5.2: claude-code, deep sonnet (effort high), quick haiku (effort medium)
```

### `tradingagents/graph/trading_graph.py`

- `_NOT_IN_SIGNATURE` 에서 `llm_max_retries` 삭제 (더 이상 config 키 아님)
- `run_settings()`: 삭제된 provider-specific 키 (`deep_think_provider`, `quick_think_provider`) 를 제거하고 `effort`, `quick_effort` 추가
- `tier_provider` 미사용 import 제거

### 테스트 업데이트

- `test_env_overrides.py`: `test_string_overrides` 가 더 이상 존재하지 않는 env 변수 (`LLM_PROVIDER`, `LLM_BACKEND_URL`) 대신 model/effort 로 교체. `test_reasoning_thinking_overrides` 와 `test_reasoning_effort_defaults_to_none` 를 `test_effort_overrides` 로 통합. `test_no_env_uses_built_in_defaults` 와 `test_empty_env_value_is_passthrough` 의 삭제된 키 참조 제거.
- `test_checkpoint_resume.py`: `_run_signature` 테스트에서 삭제된 키 (`backend_url`, `temperature`, `openai_reasoning_effort`, `llm_max_retries`) 를 effort/quick_effort 로 교체. base_config 를 claude-code 샘플로.
- `test_reporting.py`: SETTINGS 를 claude-code 로 교체. 헤더 예상 문자열을 "claude-code, deep sonnet (effort high), quick haiku (effort medium)" 로. `test_run_settings_record_the_run_without_endpoints_or_paths` 에서 `backend_url` 삭제, `effort` 검증 추가.
- `test_report_html.py`: SETTINGS 와 `test_run_details_show_each_value_as_its_own_field` 를 claude-code 샘플로.

## 설계 결정 변경 사항

### `output_language` 디폴트 변경

Task 2c 에서 CLI 가 Korean 으로 전환되었지만 DEFAULT_CONFIG 는 여전히 English 였습니다. 이 PR 에서 harmonize — DEFAULT_CONFIG 도 Korean 디폴트. Task 9 (프롬프트 현지화) 가 이 베이스에서 작업 가능.

### `TRADINGAGENTS_LLM_PROVIDER` 완전 제거

이슈 #25 는 이 환경변수를 "참조 삭제" 하라고 명시했으나, env 매핑 자체를 유지하면 사용자가 `TRADINGAGENTS_LLM_PROVIDER=openai` 를 설정해 config 를 혼란에 빠뜨릴 수 있습니다. 하드 포크 결정에 부합하도록 **env 매핑 자체를 삭제**하여 `llm_provider` 를 build-time 상수로 완전 고정.

## 검증 결과

- `pytest -q` → **1159 passed, 8 subtests passed**
- `ruff check tradingagents cli tests` → **All checks passed**
- E2E: 삭제된 env 변수 (`TRADINGAGENTS_LLM_PROVIDER=openai` 등) 를 설정해도 `DEFAULT_CONFIG["llm_provider"]` 는 여전히 `"claude-code"` — env 매핑이 없으므로 _apply_env_overrides 가 무시.

## 다음 작업 핸드오프

- **#26 (2f)**: 환경변수/문서 마무리
  - `tests/conftest.py` 의 `_API_KEY_ENV_VARS` 축소 (claude-code 는 OAuth 라 더미 키 불필요)
  - `.env.example` 또는 유사 파일에서 LLM API 키 라인 제거
  - `README.md`, `CHANGELOG.md` 외부 LLM provider 설명 정리
  - 코드 주석의 레거시 "openai", "anthropic" 참조 정리 (의미 있는 참조는 유지)
  - `TRADINGAGENTS_CLAUDE_BARE=1` 가 사용하는 `ANTHROPIC_API_KEY` 는 유지
