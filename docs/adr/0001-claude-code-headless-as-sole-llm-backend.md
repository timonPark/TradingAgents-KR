# ADR-0001: Claude Code 헤드리스를 유일 LLM 백엔드로 채택

- 상태: Accepted
- 날짜: 2026-11-02
- 관련 이슈/문서: `code_artifact.md` Task 1·Task 2, [[CLAUDE.md]] 금지사항 §4.6

## 문제 상황 (Context)

상류 TauricResearch/TradingAgents 는 Anthropic, OpenAI, Google, Azure, Bedrock, xAI, DeepSeek, Qwen, GLM, MiniMax, OpenRouter, Ollama 등 10개 이상의 LLM provider 를 추상화해 지원한다. 이 추상화는 `tradingagents/llm_clients/factory.py` 의 provider 레지스트리, provider 별 클라이언트 파일, 모델 능력 테이블(`capabilities.py`), CLI provider 선택 흐름(`cli/selections.py`) 등 코드베이스 전반에 걸쳐 있다.

이 포크의 소유자는 두 가지 제약을 가진다:

1. **비용**: 토큰 종량제 API 결제를 회피하고 이미 보유한 Anthropic Max/Pro 플랜 구독 쿼터로 운용하기를 원한다.
2. **키 관리**: `.env` 에 여러 LLM API 키를 두는 운용을 꺼린다. 자격증명을 OAuth 토큰 하나로 단일화하길 원한다.

Claude Code CLI 헤드리스 모드(`claude -p`) 는 두 제약을 동시에 충족한다 — Max 플랜 쿼터로 과금되고 OAuth 토큰으로 자격증명이 단일화된다. 다만 내부적으로는 여전히 `api.anthropic.com` 을 호출하므로 **"네트워크 격리" 목적은 아니다**.

## 결정 (Decision)

**LLM 백엔드를 Claude Code CLI 헤드리스로 단일화한다.**

- `tradingagents/llm_clients/` 아래 provider 추상화와 Anthropic/OpenAI/Google/Azure/Bedrock/ChatGPT 등 모든 구현 파일을 삭제한다.
- `pyproject.toml` 에서 `langchain-anthropic`, `langchain-openai`, `langchain-google-genai`, `langchain-aws` (bedrock extra) 의존성을 제거한다. `langchain-core` 와 `langgraph` 는 유지한다 (오케스트레이션은 그대로 사용).
- CLI 의 provider 선택 흐름(`cli/prompts.py`, `cli/selections.py`, `cli/prefs.py`, `cli/run.py`)을 삭제하고 고정값(`claude-code`)을 사용한다.
- 신규 `tradingagents/llm_clients/claude_code_client.py` 에서 LangChain `BaseChatModel` 을 `claude -p` subprocess 호출로 래핑한다.
- 상류 TauricResearch/TradingAgents 추적을 포기하는 **하드 포크**로 포지셔닝한다. upstream remote 를 추가하지 않는다.

## 결과 (Consequences)

**긍정:**
- LLM 결제 모델이 Max/Pro 쿼터로 단일화되어 운영 비용이 예측 가능해진다.
- API 키 관리/누출 리스크가 감소한다 — OAuth 토큰 하나만 관리.
- 코드베이스가 가벼워진다 — provider 추상화와 10+ provider 코드/테스트가 제거되어 유지보수 표면적 축소.
- 포크 포지셔닝이 명확해진다 ("한국 증시용 Claude Code 전용 TradingAgents").

**부정:**
- 상류의 신규 provider 지원, 버그 수정, 기능 추가를 자동으로 받지 못한다. 상류 변경을 수동 포팅해야 한다.
- Claude Code CLI 가 subprocess 로 호출되므로 호출당 콜드 스타트(~2-10초)가 발생한다. LangChain 네이티브 API 호출 대비 느리다.
- LLM 다양성을 상실한다 — Claude 모델 품질에 종속되며, Claude 가 특정 추론에 약한 경우 대안이 없다.
- Max/Pro 쿼터 제한이 반복 호출 (백테스트, 다량 종목 분석) 시 병목이 될 수 있다.

**완화책:**
- 어댑터 세마포어(`TRADINGAGENTS_CLAUDE_CONCURRENCY`, 디폴트 2) 로 동시 실행 제한 → 쿼터 소진 속도 조절.
- 분석가 노드 [[사전조회 패턴]] (ADR-0002) 으로 LLM 호출 횟수를 분석가당 3~5회에서 1회로 감소.
- Escape hatch `TRADINGAGENTS_CLAUDE_BARE=1` 로 `--bare` 모드 + `ANTHROPIC_API_KEY` 사용 가능 — 결정론이 중요한 디버깅/테스트용.

## 고려된 대안 (Alternatives Considered)

**(1) Soft fork — Claude Code 를 하나의 provider 로 추가하고 상류 추적 유지**
- 기각 사유: 상류가 provider 를 계속 늘리는 방향이라 Claude Code 가 "하나의 선택지" 로 희석됨. 한국 증시 전용 포크의 포지셔닝이 흐려지고, 머지마다 provider 간 충돌 처리 비용 발생.

**(2) Ollama 로컬 모델로 완전 오프라인**
- 기각 사유: 금융 추론에 필요한 품질 미흡. GPU 요건 발생. 사용자의 실제 제약(비용/키관리) 과 부합하지 않음 — 오프라인 자체는 요건이 아니었음.

**(3) Anthropic API 유지 + 단일 provider 로만 축소**
- 기각 사유: Max 플랜 쿼터 활용 요구를 충족하지 못함. 결제가 여전히 토큰 종량제.
