# [#24] Task 2d: pyproject.toml LLM SDK 의존성 제거

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/24
- PR: (작업 완료 후 추가)
- 상위 에픽: #21
- 브랜치: `feat/24-pyproject-deps-cleanup`
- 작업 기간: 2026-11-02 ~

## 범위

Claude Code 어댑터는 subprocess 호출만 사용하므로 외부 LLM SDK Python 패키지 의존성이 전부 불필요합니다. `pyproject.toml` 에서 제거합니다.

## 수행한 변경

### `pyproject.toml`

**제거된 의존성:**
- `langchain-anthropic>=1.7.4` (Task 2a 에서 삭제된 anthropic_client.py 가 사용)
- `langchain-openai>=1.6.6` (삭제된 openai_client.py 가 사용)
- `langchain-google-genai>=4.4.0` (삭제된 google_client.py 가 사용)

**제거된 optional-dependencies:**
- `[project.optional-dependencies] bedrock` 섹션 전체 (삭제된 bedrock_client.py 가 사용했던 `langchain-aws`)

**유지된 핵심 의존성:**
- `langchain-core>=1.6.5` — BaseChatModel 인터페이스, 메시지 타입, PromptValue 등
- `langgraph>=1.2.12`, `langgraph-checkpoint-sqlite>=3.1.1` — 그래프 오케스트레이션
- 데이터·CLI·UX 의존성 (`yfinance`, `pandas`, `questionary`, `rich`, `typer`, `stockstats` 등) — Task 5·6·7 에서 KRX vendor 로 교체 예정

**프로젝트 메타데이터:**
- `description`: "TradingAgents: Multi-Agents LLM Financial Trading Framework" → "TradingAgents-KR: Multi-Agents LLM Financial Trading Framework (Korean Market, Claude Code backend)"
- `dependencies` 섹션 상단에 ADR-0001 참조 주석 추가

## 설계 결정 변경 사항

없음. code_artifact.md Task 2 와 이슈 #24 명세대로.

## 검증 결과

### SDK 완전 제거 후 fresh install

```bash
.venv/bin/pip uninstall -y langchain-anthropic langchain-openai \
  langchain-google-genai anthropic openai google-auth google-genai
.venv/bin/pip install -e ".[dev]"
```

→ `Successfully installed tradingagents-0.7.1` — 설치 성공.

### 테스트

- `pytest -q` → **1160 passed, 8 subtests passed** (전체 스위트 통과)
- `ruff check tradingagents cli tests` → **All checks passed**

### E2E smoke (SDK 없는 환경에서)

```python
from langchain_core.messages import HumanMessage
from tradingagents.llm_clients import create_tier_client
from tradingagents.default_config import build_default_config

config = build_default_config()
quick = create_tier_client(config, tier='quick')  # ClaudeCodeClient(model='haiku')
llm = quick.get_llm()
resp = llm.invoke([HumanMessage(content='say exactly: no-sdks-ok')])
# → 'no-sdks-ok'
```

langchain-anthropic / langchain-openai / langchain-google-genai 가 **없는 환경에서** Claude Code 를 호출해 응답을 복원함. 어댑터가 외부 LLM SDK 에 전혀 의존하지 않음을 실증.

## 다음 작업 핸드오프

- **#25 (2e)**: `default_config.py` 외부 provider env 매핑 삭제 (`TRADINGAGENTS_ANTHROPIC_EFFORT`, `TRADINGAGENTS_OPENAI_REASONING_EFFORT`, `TRADINGAGENTS_GOOGLE_THINKING_LEVEL`, `TRADINGAGENTS_TEMPERATURE`, `TRADINGAGENTS_LLM_MAX_RETRIES`, `TRADINGAGENTS_MAX_TOKENS`, `TRADINGAGENTS_LLM_PROVIDER`, `TRADINGAGENTS_LLM_BACKEND_URL`, `TRADINGAGENTS_DEEP_THINK_PROVIDER`, `TRADINGAGENTS_QUICK_THINK_PROVIDER`, `TRADINGAGENTS_DEEP_THINK_BACKEND_URL`, `TRADINGAGENTS_QUICK_THINK_BACKEND_URL`) 와 대응 디폴트 값 삭제. `api_key_env.py` 를 claude-code 하나만 남기도록 축소.
- **#26 (2f)**: `conftest.py` 의 `_API_KEY_ENV_VARS` 축소, README/CHANGELOG 외부 provider 설명 정리.
