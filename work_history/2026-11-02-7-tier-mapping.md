# [#7] Task 1f: 모델 티어 매핑 + --effort CLI 플래그 전달

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/7
- PR: (작업 완료 후 추가)
- 상위 에픽: #1
- 브랜치: `feat/7-tier-mapping`
- 작업 기간: 2026-11-02 ~

## 범위

TradingAgents 의 deep/quick 추론 티어를 Claude Code 어댑터 config 로 매핑합니다. 깊은 추론은 Sonnet high, 빠른 추론은 Haiku medium 이 디폴트 (그릴링 Q9 결과).

이슈 #7 명시 범위를 넘어 **Task 1g (#8) 의 일부 (factory.py `create_llm_client` 분기 + api_key_env 처리) 를 선반영** 했습니다. 디폴트 provider 를 claude-code 로 바꾸면서 그 분기가 없으면 main 이 깨지기 때문입니다. 설계 결정 변경 사항 섹션 참조.

## 수행한 변경

### `tradingagents/default_config.py`

- `_ENV_OVERRIDES` 에 `TRADINGAGENTS_EFFORT` → `effort`, `TRADINGAGENTS_QUICK_EFFORT` → `quick_effort` 매핑 추가.
- 디폴트 값 변경:
  - `llm_provider`: `"openai"` → `"claude-code"` (ADR-0001)
  - `deep_think_llm`: `"gpt-6-sol"` → `"sonnet"` (Claude Code alias)
  - `quick_think_llm`: `"gpt-6-luna"` → `"haiku"`
  - 신규 `effort: "high"` (deep 티어)
  - 신규 `quick_effort: "medium"` (quick 티어)

### `tradingagents/llm_clients/claude_code_client.py`

- `_base_cli_args` 에 `--effort <level>` 플래그 추가. 매 subprocess 호출마다 포함.
- `_validate_effort(effort)` 신규: effort 값이 `_EFFORT_TIMEOUTS` 키 중 하나인지 검증. 알 수 없는 값은 `ValueError`.
- `ClaudeCodeClient.get_llm()` 수정: kwargs 로 받은 `effort` 를 검증 후 `ChatClaudeCodeHeadless` 로 전달.

### `tradingagents/llm_clients/factory.py`

- `create_llm_client` 에 `claude-code` 분기 선반영 (Task 1g 범위이지만 main 깨짐 방지).
- `build_llm_kwargs` 에 claude-code 분기 추가: `config["effort"]` 를 kwargs 로 추출.
- `create_tier_client` 수정: `provider == "claude-code"` 일 때 티어에 맞는 effort 를 `config["effort"]` 로 **정규화**하여 `build_llm_kwargs` 에 넘김 (deep → `effort`, quick → `quick_effort`). `build_llm_kwargs` 가 tier-agnostic 하게 유지됨.

### `tradingagents/llm_clients/api_key_env.py`

- `PROVIDER_API_KEY_ENV` 에 `"claude-code": None` 추가 (OAuth 기반 — 환경변수 API 키 불필요). Task 1g 범위이지만 main 깨짐 방지.

### 테스트

- `tests/test_claude_code_client.py` Task 1f 테스트 8개 추가:
  - `--effort` CLI 플래그 전달 (deep 경로, structured 경로)
  - `ClaudeCodeClient` effort kwarg 전달, 유효성 검증, 디폴트 폴백
  - factory `create_tier_client` deep/quick 티어별 effort 매핑
  - `api_key_env` claude-code 키 불필요
- `tests/test_env_overrides.py` 2개 테스트 업데이트 (디폴트가 openai → claude-code 로 바뀜 반영).
- `tests/test_cli_headless.py` 1개 테스트 업데이트 (checked list 의 첫 번째 provider 가 openai → claude-code).

## 설계 결정 변경 사항

### 범위 확장 (Task 1g 선반영)

이슈 #7 의 공식 범위는 "default_config, --effort CLI 전달, factory.create_tier_client 수정" 이지만, 실제 작업 중 **디폴트 provider 를 `openai` → `claude-code` 로 바꾸면 Task 1g 가 마련할 `create_llm_client` claude-code 분기와 `api_key_env` 처리가 없이는 main 이 깨짐**을 발견. 다음 두 가지를 Task 1f 에서 선반영:

1. `factory.create_llm_client` 의 `claude-code` 분기 (ClaudeCodeClient 인스턴스화)
2. `api_key_env.PROVIDER_API_KEY_ENV` 에 `claude-code: None` 추가

Task 1g (#8) 는 이제 다음에 집중:
- (해당 분기들은 이미 선반영되었으므로 테스트/문서만 보강)
- `pyproject.toml` 의존성 조정 (다른 provider 정리는 Task 2 범위, 여기선 아직 유지)
- 어댑터 공개 심볼 정리 (`llm_clients/__init__.py`)

### 티어별 effort 매핑 방식

`build_llm_kwargs` 는 tier-agnostic 하게 유지하고, `create_tier_client` 가 호출 티어에 따라 `effort` 또는 `quick_effort` 를 `config["effort"]` 로 정규화한 뒤 넘깁니다. 대안인 "`build_llm_kwargs` 에 tier 파라미터 추가" 보다 상류 함수 시그니처를 덜 흔듭니다.

## 검증 결과

- `pytest -q` → **1475 passed, 1 skipped** (전체 스위트)
- `ruff check tradingagents tests` → **All checks passed**
- **End-to-end smoke test**:
  ```python
  config = build_default_config()
  # llm_provider=claude-code, deep=sonnet/high, quick=haiku/medium
  quick = create_tier_client(config, tier='quick')
  llm = quick.get_llm()  # ChatClaudeCodeHeadless(model='haiku', effort='medium')
  llm.invoke([HumanMessage(content='say exactly: pipeline-ok')])
  # → AIMessage(content='pipeline-ok')
  ```
  전체 파이프라인 (config → factory → 어댑터 → `claude -p`) 통과 확인.

## 다음 작업 핸드오프

Task 1g (#8) 는 범위가 축소됨 — 주요 분기가 이미 선반영되어 있어 남은 작업은:
- `tradingagents/llm_clients/__init__.py` 공개 심볼 정리 (ClaudeCodeClient, ChatClaudeCodeHeadless 노출)
- Task 1g 범위의 테스트 보강 (이미 Task 1f 에서 간접 커버되지만 별도 유닛)
- 다른 provider 코드 정리는 Task 2 범위이므로 Task 1g 에서는 손대지 않음

Task 1h (#9) escape hatch `TRADINGAGENTS_CLAUDE_BARE=1` 는 독립적으로 진행 가능.
