# [#103] `.env.example` / `.env.enterprise.example` 하드 포크 정합성 교정

- 이슈: #103
- PR: (작업 완료 후 추가)
- 브랜치: `chore/103-env-example-hardfork`
- 작업 기간: 2026-11-04 ~

## 배경

Task 2 (#21) 에서 외부 LLM provider 를 **코드에서** 제거했지만 템플릿 파일은
상류 TauricResearch 그대로 남아 있어 **ADR-0001 (Claude Code 단일 백엔드)**
결정과 모순. 포크 사용자가 OpenAI/Google/Anthropic/Groq 등 **참조되지 않는**
API 키를 설정하도록 안내하는 상태였음. Task 12 머지 이후 운영 검증 준비 중
발견.

## 수행한 변경

### `.env.example` 전면 재작성 (85줄 유지)

**삭제** (상류 템플릿에서 가져온 불필요 항목):
- LLM provider API 키 — OpenAI / Google / Anthropic / XAI / DeepSeek /
  Dashscope (전세계/CN) / Zhipu (전세계/CN) / Minimax (전세계/CN) / OpenRouter /
  Mistral / Moonshot / Groq / NVIDIA — 총 15개 키
- SEC_EDGAR_USER_AGENT (Task 5 로 DART 대체)
- FRED_API_KEY (Task 7 로 ECOS 대체)
- TYPESAFE_API_KEY (StockTwits/Reddit 제거됨)
- OPENAI_COMPATIBLE_API_KEY (단일 백엔드)
- AWS Bedrock 섹션 (AWS_BEARER_TOKEN_BEDROCK, AWS_DEFAULT_REGION, AWS_PROFILE)
- ChatGPT Plus / `tradingagents login chatgpt` 안내
- OLLAMA_BASE_URL
- TRADINGAGENTS_LLM_PROVIDER / DEEP_THINK_PROVIDER / QUICK_THINK_PROVIDER /
  BACKEND_URL / TEMPERATURE / LLM_MAX_RETRIES / MAX_TOKENS /
  OPENAI_REASONING_EFFORT / GOOGLE_THINKING_LEVEL / ANTHROPIC_EFFORT /
  MAX_TOOL_ROUNDS — 단일 백엔드 고정으로 불필요

**추가** (KRX 하드 포크 전용):
- **KRX vendor 키 섹션**:
  - DART_API_KEY (필수 표기 + opendart.fss.or.kr 발급 URL 주석)
  - ECOS_API_KEY (선택, 한국은행 ECOS)
  - KRX_ID / KRX_PW (선택, pykrx 투자자 흐름)
- **TradingAgents 설정 오버라이드**: 코드에서 실제 참조되는 TRADINGAGENTS_*
  환경변수만 (default_config.py `_ENV_VAR_MAP` 과 일치):
  - RESULTS_DIR / CACHE_DIR / MEMORY_LOG_PATH
  - OUTPUT_LANGUAGE (기본 Korean)
  - BENCHMARK_TICKER / NO_UPDATE_CHECK
  - DEEP_THINK_LLM / QUICK_THINK_LLM (기본 sonnet / haiku)
  - EFFORT / QUICK_EFFORT (기본 high / medium)
  - MAX_DEBATE_ROUNDS / MAX_RISK_ROUNDS (기본 1)
  - CHECKPOINT_ENABLED (기본 false)
- **Claude Code 어댑터 튜닝**:
  - CLAUDE_CONCURRENCY (세마포어, Max 쿼터 보호)
  - CLAUDE_TIMEOUT (단일 호출 타임아웃)
- **Docker 실행 섹션** (TRADINGAGENTS_DATA_DIR)
- **⚠️ Escape hatch 섹션** (CLAUDE.md §4.6):
  - TRADINGAGENTS_CLAUDE_BARE + ANTHROPIC_API_KEY — 디버깅 전용, 운영 금지
    경고 포함

### `.env.enterprise.example` 삭제

Azure OpenAI 만 담긴 템플릿. 하드 포크에서 Azure 역시 외부 LLM provider 로
제거 대상 범위에 포함. README / CLAUDE.md 에서 참조 없음 확인 후 삭제.

## 설계 결정 변경 사항

### conftest.py 의 `.env.enterprise` 참조 유지

`tests/conftest.py:20-21` 에서 `_blank_settings_overlay` 가 `.env.enterprise`
도 읽는 코드가 있음. 하드 포크 정합성상 제거할 수 있지만:
- 파일 없을 때 `dotenv_values` 가 빈 dict 반환 → 테스트 영향 없음
- 사용자가 로컬에 `.env.enterprise` 를 두고 있을 수 있음 (이번 세션 전부터)
  — 기존 사용 패턴 유지하는 쪽이 안전

별도 이슈로 돌릴 가치가 없어 이번 범위에서 제외. 필요 시 후속 이슈로.

## 검증 결과

- `grep -E "OPENAI_API_KEY|GOOGLE_API_KEY|FRED_API_KEY|SEC_EDGAR|TYPESAFE|OLLAMA_BASE|AZURE_OPENAI|AWS_BEARER|..." .env.example` → **0건**
- `wc -l .env.example` → **85줄** (상류 84 → KRX 85 거의 동일, 노이즈 감소)
- `ls .env.enterprise.example` → **파일 없음**
- README / CLAUDE.md 에서 `enterprise` 참조 → **없음**
- `pytest -q` → **851 passed, 11 deselected** (template 변경이 테스트에 영향 없음)
- `ruff check tradingagents cli tests` → **All checks passed**

## 완료 criteria 확인

- ✓ `.env.example` 에 LLM provider 키 **0개**
- ✓ `.env.example` 에 코드에서 실제 참조되는 환경변수만 노출
- ✓ DART_API_KEY 필수 표기 + 발급 URL 주석
- ✓ escape hatch 경고 (ANTHROPIC_API_KEY 운영 금지) 명시
- ✓ `.env.enterprise.example` 삭제
- ✓ README 에서 `.env.enterprise.example` 참조 없음 (처음부터 없었음)
- ✓ `grep OPENAI_API_KEY .env.example` → 0건

## 다음 작업 핸드오프

### 사용자 액션 대기
- DART API 키 발급 (opendart.fss.or.kr)
- 발급 후 `.env` 생성: `cp .env.example .env && echo "DART_API_KEY=<발급키>" >> .env`

### 운영 검증 (사용자 DART 키 준비 후)
- `python -m cli.main run` 로 실제 KRX 티커 (예: 005930 삼성전자) 분석
- Docker build + run 검증 (HOME 재지정 OAuth 가정 실증)
