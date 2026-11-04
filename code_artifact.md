# TradingAgents 한국 증시 버전 커스터마이징 작업 리스트

TauricResearch/TradingAgents 프레임워크의 핵심 추론 엔진(LangGraph 오케스트레이션, 토론 및 리스크 관리 파이프라인)을 유지하면서, LLM 백엔드를 Claude Code 헤드리스로 고정하고 데이터 수집 레이어를 한국 증시(KOSPI/KOSDAQ) 환경으로 전환하기 위한 엔지니어링 작업 명세서입니다.

**LLM 백엔드 정책:** 외부 LLM API(Anthropic/OpenAI/Gemini/Azure/Bedrock 등) 경로는 전면 제거합니다. 추론은 로컬에 설치된 Claude Code CLI(OAuth 토큰 기반)만을 통해 수행합니다. Claude Code 자체는 Max/Pro 플랜 쿼터로 `api.anthropic.com` 을 호출하지만, TradingAgents 코드베이스는 Anthropic/OpenAI SDK 를 직접 의존하지 않습니다.

**포크 전략:** `TauricResearch/TradingAgents` 상류 추적을 포기하는 하드 포크입니다. provider 추상화와 미사용 vendor 코드/의존성을 삭제하고 한국 증시 전용 포크로 재포지셔닝합니다.

**툴 호출 방식:** MCP 서버 브리지를 사용하지 않습니다. 분석가 4개의 툴 집합이 정적으로 정의되어 있어 LLM 의 동적 툴 선택이 필요 없다는 점, Claude Code subprocess 스핀업 비용이 비싸다는 점을 고려해 **데이터 사전조회 + 프롬프트 주입** 패턴으로 전환합니다. 분석가당 Claude Code 호출을 3~5회에서 1회로 축소합니다.

---

## 1. 사전 환경 구성 및 의존성 추가

* **Claude Code CLI 설치 및 로그인 (필수):**
  ```bash
  npm install -g @anthropic-ai/claude-code
  claude login            # OAuth 로그인 (Max/Pro 플랜 쿼터 사용)
  claude -p "ping"        # 설치 및 인증 확인
  ```
* **데이터 소스용 Python 라이브러리 설치:**
  ```bash
  pip install pykrx OpenDartReader finance-datareader
  ```
* **데이터 API 키 발급 및 `.env` 설정:**
  * 금융감독원 Open DART 인증키 (`DART_API_KEY`) — 필수
  * 한국은행 ECOS Open API 인증키 (`ECOS_API_KEY`) — 선택
  * LLM API 키(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` 등)는 **일체 설정하지 않습니다.**

---

## 2. 코드 수정 작업 리스트

### Task 1: Claude Code 헤드리스 LLM 어댑터 구현 (최우선, 전체 파이프라인의 전제)
* **대상 파일:**
  * 신규: `tradingagents/llm_clients/claude_code_client.py`
  * 수정: `tradingagents/llm_clients/factory.py`, `tradingagents/llm_clients/__init__.py`, `tradingagents/llm_clients/api_key_env.py`
* **작업 배경:**
  * TradingAgents 가 LLM 에 기대하는 패턴 중 `invoke` 와 `with_structured_output` 만 Claude Code 헤드리스로 매핑합니다. `bind_tools` 는 지원하지 않습니다 (Task 3 에서 분석가 노드를 사전조회 패턴으로 리팩터링하므로 불필요).
  * 외부 API 호출 없이 로컬 Claude Code 프로세스를 subprocess 로 구동합니다.
* **작업 내용:**
  * LangChain `BaseChatModel` 서브클래스 `ChatClaudeCodeHeadless` 를 작성해 `claude -p "프롬프트" --output-format json --model <sonnet|opus> --effort <level> --no-session-persistence --permission-mode plan` subprocess 호출을 LangChain 호환 인터페이스로 래핑합니다.
  * `plan` 모드로 호스트 파일 시스템/Bash 수정은 전면 차단합니다. MCP 툴 호출이 없으므로 permission 관련 추가 설정은 불필요합니다.
  * `with_structured_output(Schema)` → Pydantic 스키마를 JSON Schema 로 변환하여 `--json-schema` 옵션에 주입. Portfolio Manager/Trader/Research Manager 의 구조화 출력 경로(`tradingagents/agents/structured.py`)를 지원합니다.
  * `bind_tools(tools)` 호출 시 `NotImplementedError` 를 명확히 발생시킵니다. `structured.py` 가 free-text 폴백으로 처리하도록 두거나, 호출부에서 명시적으로 bind_tools 를 사용하지 않도록 Task 3 에서 교정합니다.
  * `factory.py` 를 Claude Code 단일 provider 로 축소하고 `provider_lower == "claude-code"` 분기만 남깁니다.
  * `api_key_env.py` 에서 LLM API 키 관련 로직을 제거합니다 (CLI 는 OAuth 토큰을 자체 관리).
  * config 키로부터 Claude Code CLI 인자(`--model`, `--effort`) 를 매핑합니다. **디폴트 조합 (균형):**
    * `TRADINGAGENTS_DEEP_THINK_LLM=sonnet` + `TRADINGAGENTS_EFFORT=high` → 리서처/매니저/트레이더/디베이터 등 깊은 추론
    * `TRADINGAGENTS_QUICK_THINK_LLM=haiku` + `TRADINGAGENTS_QUICK_EFFORT=medium` → 분석가의 데이터 요약·보고서 작성
    * `TRADINGAGENTS_QUICK_EFFORT` 는 신규 config 키입니다. deep 과 quick 에 서로 다른 effort 를 적용하기 위해 추가.
    * 사용자가 특정 분석을 더 깊게 하려면 `TRADINGAGENTS_DEEP_THINK_LLM=opus` 로 1회 오버라이드 가능. `default_config.py` 의 디폴트도 동일하게 조정.
  * **오류 처리 정책:**
    * **타임아웃**: `--effort` 레벨에 따른 가변 디폴트 (medium=300s, high=600s, max=1200s). 환경변수 `TRADINGAGENTS_CLAUDE_TIMEOUT` 로 오버라이드 가능.
    * **non-zero exit**: 1회 재시도 후 예외 전파. 일시적 ENOTFOUND 등은 흡수하되 반복 실패는 환경 문제로 간주.
    * **JSON 파싱 실패**: 어댑터는 예외 전파만, 재시도 안 함. `structured.py` 의 기존 free-text 폴백 경로가 처리.
    * **429 / 쿼터 초과**: 60초 대기 후 1회 재시도. 2회째 실패하면 "Max 플랜 쿼터 소진" 메시지와 함께 명확히 실패 전파 (지수 백오프로 분석이 수십 분 지연되는 것 방지).
  * **동시 실행 제한:** 모듈 레벨 세마포어(`threading.Semaphore` 또는 비동기 호출용 `asyncio.Semaphore`) 로 동시 실행 중인 `claude -p` 프로세스 수를 제한합니다. 환경변수 `TRADINGAGENTS_CLAUDE_CONCURRENCY` (디폴트 `2`) 로 조절. OAuth 쿼터 소진 및 머신 메모리 보호 (Node.js 런타임당 300~500MB) 용. 분석가 병렬 실행, 백테스트 종목 동시 실행 모두 동일 세마포어를 공유합니다.
  * **환경 격리 (`--bare` 미사용, 수동 격리):** Claude Code 가 자동 로드하는 숨은 상태(auto-memory, 상위 `CLAUDE.md`, hooks, 플러그인, SKILLS 등) 가 분석 결과의 결정론을 깨뜨리지 못하도록 어댑터가 명시적으로 격리합니다. `--bare` 는 OAuth 를 못 쓰게 하므로 Max 플랜 쿼터 전제와 상충해 사용하지 않습니다. 대신:
    * `--disable-slash-commands` 로 SKILLS/slash command 로딩 차단.
    * `--mcp-config` 는 명시적으로 빈 설정 또는 미지정 (Task 3 에서 MCP 포기했으므로 자연스럽게 적용됨).
    * `--exclude-dynamic-system-prompt-sections` 로 cwd/env/git status 등 호스트 종속 섹션 제거.
    * `--append-system-prompt` 로 TradingAgents 지침을 명시적으로 주입해 상위 `CLAUDE.md` 영향을 희석.
    * Docker 환경에서는 임시 HOME(`/tmp/claude-home`, Task 12) 에 빈 `CLAUDE.md` 를 두어 자동 발견을 무력화.
    * **Escape hatch:** 환경변수 `TRADINGAGENTS_CLAUDE_BARE=1` 설정 시 `--bare` 모드로 전환하되, 이 경우 `ANTHROPIC_API_KEY` 가 설정되어 있어야 함을 어댑터가 검증. 결정론이 중요한 디버깅/테스트 상황을 위한 escape hatch.

### Task 2: 기존 외부 LLM API 클라이언트 및 의존성 완전 제거
* **대상 파일:**
  * 삭제: `tradingagents/llm_clients/anthropic_client.py`, `openai_client.py`, `google_client.py`, `azure_client.py`, `bedrock_client.py`, `chatgpt_auth.py`, `capabilities.py`, `model_catalog.py`, `validators.py`
  * 수정: `tradingagents/llm_clients/factory.py`, `pyproject.toml`, `cli/prefs.py`, `cli/prompts.py`, `cli/selections.py`, `cli/run.py`
* **작업 내용:**
  * 위 LLM provider 클라이언트 파일들을 삭제합니다. Claude Code 어댑터에서 참조하는 공통 코드(`base_client.py` 의 `normalize_content` 등)만 남깁니다.
  * `pyproject.toml` 의 LLM SDK 의존성을 제거합니다: `langchain-anthropic`, `langchain-google-genai`, `langchain-openai`, `langchain-aws`(bedrock extra).
    * `langchain-core`, `langgraph`, `langgraph-checkpoint-sqlite` 는 유지 (LangGraph 오케스트레이션 자체는 그대로).
  * `factory.py` 의 `OPENAI_COMPATIBLE_PROVIDERS` 레지스트리, `is_openai_compatible`, `check_endpoint`, `REASONING_EFFORT_PROVIDERS` 등 멀티 provider 분기 코드를 삭제합니다.
  * CLI 쪽 provider 선택 흐름 제거:
    * `cli/prompts.py` 의 `_llm_provider_table`, `select_llm_provider` 함수 삭제.
    * `cli/selections.py` 의 `TRADINGAGENTS_LLM_PROVIDER` 체크·qwen/minimax/glm 지역 선택 로직 삭제.
    * `cli/prefs.py` 의 `llm_provider` 보존 로직 단순화 (고정값).
    * `cli/run.py` 의 provider 선택 조립 로직 삭제.
  * 관련 환경변수(`OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `AZURE_*`, `AWS_*`, `OLLAMA_BASE_URL`, `TRADINGAGENTS_LLM_PROVIDER`, `TRADINGAGENTS_LLM_BACKEND_URL` 등)에 대한 참조와 문서 설명을 모두 삭제합니다.
  * **깨진 테스트 삭제 (재작성은 Task 11 에서):** 다음 테스트 파일을 삭제합니다. 재작성은 Task 11 로 분리해 각 vendor/어댑터 구현 PR 에 묶음.
    * provider 관련: `test_anthropic_effort.py`, `test_azure_client.py`, `test_bedrock_provider.py`, `test_chatgpt_auth.py`, `test_chatgpt_provider.py`, `test_deepseek_reasoning.py`, `test_google_api_key.py`, `test_google_thinking_level.py`, `test_minimax.py`, `test_openai_compatible_provider.py`, `test_openai_reasoning_effort.py`, `test_openai_responses_base_url.py`, `test_openrouter_model_select.py`, `test_ollama_base_url.py`, `test_provider_registry.py`, `test_tier_providers.py`, `test_model_validation.py`, `test_capabilities.py`
    * 외부 LLM 공통: `test_api_key_env.py`, `test_llm_max_retries.py`, `test_llm_max_tokens.py`, `test_temperature_config.py`
    * vendor 테스트 (Task 4·5·6·7 에서 삭제될 구현에 묶인 것): `test_alpha_vantage_hardening.py`, `test_sec_edgar.py`, `test_reddit_fallback.py`, `test_stocktwits_resilience.py`, `test_fred.py`, `test_polymarket.py`, `test_yahoo_rate_limit.py`, `test_yahoo_snapshot.py`, `test_yfinance_stale_ohlcv_guard.py`
  * **유지되는 중립 테스트** (Task 2 범위 아님, 추후 Task 들에서 수정): `test_backtest.py`, `test_graph_end_to_end.py`, `test_structured_agents.py`, `test_analyst_execution.py`, `test_cli_*.py` 대부분, `test_date_boundaries.py`, `test_debate_opening.py`, `test_memory_*.py`, `test_checkpoint_*.py`, `test_prompt_integrity.py`, `test_report_html.py`, `test_reporting.py`, `test_ticker_symbol_handling.py`, `test_safe_ticker_component.py`, `test_instrument_identity.py`, `test_symbols.py`, `test_symbol_normalization_paths.py` 등.

### Task 3: 분석가 노드 사전조회 리팩터링 (툴 루프 제거)
* **대상 파일:**
  * 수정: `tradingagents/agents/analysts/turn.py`, `tradingagents/agents/analysts/market_analyst.py`, `fundamentals_analyst.py`, `news_analyst.py`, `sentiment_analyst.py`
  * 수정: `tradingagents/graph/setup.py` (ToolNode 삭제 또는 우회)
* **작업 배경:**
  * Claude Code 헤드리스는 `bind_tools` 를 지원하지 않고, MCP 서버로 브리지를 만들지 않습니다 (설계 결정, 상단 "툴 호출 방식" 참고).
  * 각 분석가의 툴 집합이 정적으로 정의되어 있어 LLM 의 동적 선택이 불필요하며, 사전조회로 축소하면 분석가당 Claude Code 호출을 3~5회에서 1회로 줄일 수 있습니다.
* **작업 내용:**
  * `turn.py` 의 `take_turn()` 을 삭제하거나 "사전조회된 데이터를 받아 단일 `llm.invoke()` 를 수행하는" 형태로 재작성합니다 — WRAP_UP 로직 포함 전부 제거.
  * 각 분석가 노드(`market_analyst.py` 등)에서 LLM 호출 전에 Python 이 모든 필요한 데이터를 미리 호출합니다. 예: market_analyst 는 `get_stock_data` + 11개 지표 전부 + `get_verified_market_snapshot` 선조회 → DataFrame/표를 Markdown 으로 포맷 → 프롬프트에 주입.
  * 프롬프트의 "너는 툴을 호출해서..." 문구를 "아래 사전조회된 데이터를 기반으로..." 로 교체합니다. 지표 선택 지침은 "데이터에서 가장 관련 있는 8개를 보고서에서 다루어라" 로 변경.
  * `graph/setup.py` 의 `ToolNode(list(spec.tools))` 노드와 그와 연결된 `continue_tool_use` 조건부 엣지를 삭제합니다. 분석가 노드는 단일 호출 후 바로 다음 단계로 넘어가도록 그래프를 단순화합니다.
  * `sentiment_analyst.py` 는 이미 bind_tools 를 쓰지 않으므로 (`sentiment_analyst.py:110` 주석) 참고 패턴으로 활용합니다.

### Task 4: 티커(Ticker) 유효성 검증 및 심볼 정규화 변경
* **대상 파일:**
  * 수정: `tradingagents/dataflows/symbols.py`, `cli/selections.py`, `cli/prompts.py` 중 티커 입력 검증부
* **작업 내용:**
  * `symbols.py` 의 미국/HK/상해 심볼 정규화 테이블(`_FOREX_CURRENCIES`, Yahoo 심볼 매핑 등)을 제거하고 한국거래소 전용 매핑으로 교체합니다.
  * 한국거래소 표준 **6자리 숫자 종목코드**(`^\d{6}$`)만 허용하는 검증 로직을 추가합니다 (보통주/우선주/ETF 모두 6자리이므로 동일 패턴 적용).
  * CLI 입력 프롬프트의 티커 예시 문자열(`AAPL`, `TSLA` 등)을 한국 종목(`005930` 삼성전자, `000660` SK하이닉스 등)으로 교체합니다.

### Task 5: 재무/공시 분석 도구 교체 (SEC EDGAR → DART)
* **대상 파일:**
  * 삭제: `tradingagents/dataflows/vendors/sec_edgar.py`
  * 신규: `tradingagents/dataflows/vendors/dart.py`
  * 수정: `tradingagents/dataflows/router.py` (vendor 등록), 재무 분석가 노드(`tradingagents/agents/analysts/fundamentals_analyst.py`) 의 사전조회 로직
* **작업 내용:**
  * `sec_edgar.py` 의 CIK 매핑/EDGAR API 클라이언트 로직을 삭제합니다.
  * `OpenDartReader` 를 연동해 6자리 종목코드의 최근 사업보고서/분기보고서를 조회하는 `vendors/dart.py` 를 작성합니다.
  * 주요 추출 지표: 최근 분기 매출액, 영업이익률, 부채비율, 재고자산 추이, 전환사채(CB) 발행 내역.
  * 추출된 데이터를 Markdown 표 또는 포맷된 문자열로 반환하여 Task 3 에서 분석가 노드가 프롬프트에 직접 주입합니다.

### Task 6: 시세 및 기술적 지표 도구 교체 (Alpha Vantage/Yahoo → pykrx)
* **대상 파일:**
  * 삭제: `tradingagents/dataflows/vendors/alpha_vantage/` (디렉터리 전체), `tradingagents/dataflows/vendors/yahoo/` (디렉터리 전체)
  * 신규: `tradingagents/dataflows/vendors/pykrx.py`
  * 수정: `tradingagents/dataflows/router.py`, `tradingagents/dataflows/symbols.py` (Yahoo 심볼 변환 제거), 기술적 분석가 노드(`tradingagents/agents/analysts/market_analyst.py`) 의 사전조회 로직
* **작업 내용:**
  * 미국 주식 시세 호출 함수를 `pykrx.stock.get_market_ohlcv_by_date` 로 대체합니다.
  * 기존 보조지표 연산 모듈(RSI, MACD, 이동평균선, 볼린저 밴드 — `stockstats` 기반) 에 한국 거래소 일봉 데이터프레임을 주입합니다.
  * 투자자별 수급 데이터(`pykrx.stock.get_market_net_purchases_of_equities_by_ticker`)를 추가해 외국인/기관 5거래일 순매수 동향을 분석 컨텍스트에 포함시킵니다.
  * Task 3 리팩터링에 맞춰 분석가 노드가 호출 1회로 모든 지표(11개 전량)를 선계산해 프롬프트에 주입할 수 있도록 함수 시그니처를 단순화합니다.

### Task 7: 거시경제 및 뉴스 도구 현지화
* **대상 파일:**
  * 삭제: `tradingagents/dataflows/vendors/reddit.py`, `tradingagents/dataflows/vendors/stocktwits.py`, `tradingagents/dataflows/vendors/fred.py`, `tradingagents/dataflows/vendors/polymarket.py`
  * 신규: `tradingagents/dataflows/vendors/naver_news.py`, `tradingagents/dataflows/vendors/ecos.py`
  * 수정: `tradingagents/dataflows/router.py`, 뉴스 분석가 (`tradingagents/agents/analysts/news_analyst.py`) 및 감성 분석가 (`tradingagents/agents/analysts/sentiment_analyst.py`) 의 사전조회 로직
* **작업 내용:**
  * Reddit, StockTwits, FRED, Polymarket 호출부를 삭제합니다.
  * 네이버 금융 주요 뉴스 헤드라인 크롤러(`naver_news.py`)를 작성해 노이즈(광고성 기사)를 제거하고 주요 이슈 5건을 요약 전달합니다.
  * 거시 지표는 한국은행 ECOS Open API(`ecos.py`) 호출 또는 환율·기준금리 정적 매핑으로 교체합니다.

### Task 8: 한국 거래소 캘린더 매핑 (백테스트 시점 격리)
* **대상 파일:**
  * 수정: `tradingagents/backtest.py` (단일 파일, 디렉터리 아님), `tradingagents/dataflows/date_window.py`
* **작업 내용:**
  * 미국 증시(NYSE) 휴장일 기준 캘린더를 한국거래소(KRX) 영업일 캘린더로 교체합니다.
  * `pykrx.stock.get_market_trading_days_by_range` 를 활용해 휴장일에 데이터 조회가 실패하지 않도록 인덱스를 보정합니다.
  * `date_window.py` 의 "현재 날짜" 처리 로직이 KRX 거래일 기준으로 동작하도록 조정합니다 (한국 공휴일 반영).

### Task 9: 시스템 프롬프트 현지화 및 한국어 출력 (인라인 프롬프트 수정)
* **i18n 원칙:** 사용자가 보는 모든 표준 출력(에이전트 리포트, CLI UI 메시지, 진행 상황, 에러 메시지) 은 한국어. 내부 코드값(enum, 라벨 매칭용 상수, 파싱 대상 토큰: BUY/SELL/HOLD 등) 은 영어 유지.
* **대상 파일 (에이전트 인라인 프롬프트):**
  * `tradingagents/agents/analysts/fundamentals_analyst.py`, `market_analyst.py`, `news_analyst.py`, `sentiment_analyst.py`
  * `tradingagents/agents/researchers/bull_researcher.py`, `bear_researcher.py`
  * `tradingagents/agents/managers/research_manager.py`, `portfolio_manager.py`
  * `tradingagents/agents/trader/trader.py`
  * `tradingagents/agents/risk_mgmt/aggressive_debator.py`, `conservative_debator.py`, `neutral_debator.py`
* **대상 파일 (출력 언어 디폴트 및 파서 조정):**
  * `tradingagents/default_config.py` — `"output_language": "English"` → `"Korean"` 변경
  * `tradingagents/agents/context.py` — `get_language_instruction()` 의 "예외 라벨" 지침을 "값(BUY/SELL/HOLD)은 영어 유지, 라벨은 한국어 표기" 로 변경 (예: `**등급**: BUY`, `**최종 거래 제안**: BUY`)
  * `tradingagents/agents/rating.py` — `Matches "Rating: X"` 정규식(파일 내 주석 참고) 에 한국어 라벨(`등급`, `최종 거래 제안`) 패턴 추가. BUY/SELL/HOLD 값 추출 로직은 변경 없음.
  * `tradingagents/agents/schemas.py` — `FINAL TRANSACTION PROPOSAL: **{action}**` 렌더링 템플릿(라인 194·211) 에 한국어 라벨 옵션 추가하거나, `output_language` 에 따라 라벨만 번역해 렌더.
  * `tradingagents/reporting.py` — `f"- Rating: {run_rating(...)}"` (라인 26) 라벨 한국어화.
  * `tests/test_rating*.py`, `test_structured_agent_prompts.py` 등 파서/렌더 관련 테스트 — 한국어 라벨 케이스 추가 (Task 11 에 반영)
* **대상 파일 (CLI UI 한국어화):**
  * `cli/display.py`, `cli/prompts.py`, `cli/selections.py`, `cli/run.py`, `cli/prefs.py` 등의 사용자 노출 문자열 전면 한국어 치환 (진행 메시지, 선택 프롬프트, 에러 메시지).
  * 다만 **CLI 플래그 이름/환경변수 이름/코드 식별자** 는 영어 유지 (예: `--output-format`, `TRADINGAGENTS_LLM_PROVIDER`).
  * Rich 콘솔 표/제목 등 한국어로 변경.
* **작업 내용:**
  * 각 에이전트의 인라인 시스템 프롬프트에 국내 증시 특유의 리스크(외국인/기관 수급 공백, 오버행 이슈, 관리종목/환기종목 요건, 공매도 금지 종목, 상·하한가 ±30% 제한 등) 지침을 추가합니다.
  * Task 3 리팩터링에 맞춰 분석가 프롬프트의 "툴을 호출해..." 문구를 "주어진 데이터를 기반으로..." 로 교체합니다.
  * 최종 리포트/토론/의사결정 출력 전체가 한국어로 생성되도록 `output_language` 디폴트와 `get_language_instruction()` 를 조정합니다.
  * 리포트 끝의 결정 라인 포맷: `**등급**: BUY/SELL/HOLD` + `**최종 거래 제안**: BUY/SELL/HOLD` — 라벨은 한국어, 값은 영어 유지. 파서가 두 포맷 모두 인식하도록 처리.

### Task 11: 테스트 재작성 (각 vendor/어댑터 구현 PR 에 묶어 순차 추가)
* **대상 파일 (신규):**
  * `tests/test_claude_code_client.py` — 어댑터 유닛 테스트 (subprocess 모킹, JSON 파싱, 타임아웃·재시도·세마포어·오류 처리 정책)
  * `tests/test_dart_vendor.py` — DART 조회 유닛/통합 테스트
  * `tests/test_pykrx_vendor.py` — pykrx 시세·수급·거래일 통합 테스트
  * `tests/test_naver_news_vendor.py` — 네이버 뉴스 크롤러 테스트 (ToS 준수 확인 포함)
  * `tests/test_ecos_vendor.py` — ECOS API 호출 테스트 (키 없을 때 정적 매핑 폴백)
* **대상 파일 (수정):**
  * `tests/test_analyst_execution.py` — Task 3 사전조회 패턴 반영, ToolNode 분기 삭제
  * `tests/test_graph_end_to_end.py` — ToolNode/조건부 엣지 제거된 그래프에 맞춤
  * `tests/test_backtest.py` — Task 8 KRX 캘린더 반영
  * `tests/test_structured_agents.py` — Claude Code 어댑터와의 호환 확인 (`--json-schema` 경유)
  * `tests/test_prompt_integrity.py` — Task 9 한국어 프롬프트 및 국내 리스크 지침 체크
  * `tests/test_ticker_symbol_handling.py`, `test_safe_ticker_component.py`, `test_symbols.py`, `test_symbol_normalization_paths.py` — Task 4 (6자리 숫자 종목코드) 반영
  * `tests/test_fundamentals_lookahead.py`, `test_fundamentals_units.py` — DART 소스로 교체
  * `tests/test_news_analyst_prompt.py`, `test_news_lookahead.py`, `test_social_lookahead.py` — 네이버 뉴스 소스로 교체
  * `tests/test_date_boundaries.py` — KRX 거래일 기준으로 조정
* **작업 운영 원칙:**
  * **각 vendor Task 의 DoD(Definition of Done) 에 "해당 테스트 작성 완료" 를 포함** 합니다. 예: Task 5 (DART) 완료 조건 = `vendors/dart.py` 구현 + `tests/test_dart_vendor.py` 통과.
  * Task 11 자체는 **집계용 체크리스트**. 별도 PR 하나로 묶지 않고 각 Task 와 함께 커밋.
  * Task 1 (어댑터) 완료 시점에 `tests/test_claude_code_client.py` 는 반드시 작성 완료되어야 함 — 이후 Task 들의 안전망 역할.

### Task 12: Docker 환경에 Claude Code CLI 통합 (API 경로 제거)
* **대상 파일:** `Dockerfile`, `docker-compose.yml`
* **작업 내용:**
  * `Dockerfile` 에 Node.js 설치 레이어와 `npm install -g @anthropic-ai/claude-code` 를 추가해 컨테이너 내부에서 `claude` CLI 를 사용 가능하도록 합니다.
  * OAuth 자격증명만 선택적으로 공유합니다 (호스트 `~/.claude` 전체 공유 금지):
    * 호스트의 `~/.claude/.credentials.json` (또는 Claude Code 가 OAuth 토큰을 보관하는 실제 파일) 만 컨테이너의 `/claude-auth/.credentials.json` 로 **읽기전용** 마운트.
    * 컨테이너 내부에 임시 HOME 디렉터리(`/tmp/claude-home`) 를 생성하고 `HOME=/tmp/claude-home` 환경변수를 지정. Claude Code CLI 가 세션 로그/캐시/리프레시 상태를 이 디렉터리에 쓰도록 유도.
    * 컨테이너 시작 시 `.credentials.json` 을 `$HOME/.claude/.credentials.json` 로 symlink 하거나 복사하는 entrypoint 스크립트 작성.
    * 호스트 `~/.claude` 가 컨테이너에서 오염되지 않으며, 컨테이너 종료 시 임시 상태가 소실됩니다.
  * **구현 전 검증 사항:** Claude Code 의 토큰 파일 실제 경로, HOME 재지정만으로 OAuth 가 정상 작동하는지(리프레시 토큰 쓰기 포함) 확인. 검증 실패 시 `~/.claude` 전체를 읽기쓰기로 마운트하는 옵션으로 백오프합니다 (호스트 오염 위험 수용).
  * 기존 `ollama`, `tradingagents-ollama` 서비스와 `ollama` 프로파일을 삭제합니다 (Claude Code 단일 백엔드).
  * `env_file: - .env` 는 유지하되, LLM API 키 관련 변수는 더 이상 참조되지 않음을 README/주석에 명시합니다.

### Task 14: 로컬 Astro + FastAPI 프론트엔드 (Neo Kinpaku 디자인)
* **대상 파일 (신규):**
  * `api/` — FastAPI 백엔드 (`main.py`, `config.py`, `models.py`, `run_store.py`, `runner.py`, `reports_store.py`, `routes/{health,symbols,runs,reports}.py`)
  * `web/` — Astro 프론트엔드 (`src/layouts/Base.astro`, `src/pages/{index,report}.astro`, `src/components/{SymbolSearch,RunPanel,ReportViewer}.{tsx,css}`, `src/styles/{kinpaku-tokens,kinpaku-kit,app}.css`)
  * `tradingagents/dataflows/krx_symbol_search.py` — CLI 와 웹이 공유하는 종목 검색 모듈
* **대상 파일 (수정):**
  * `tradingagents/graph/trading_graph.py` — 생성자에 `progress_callback` 추가, `_run_graph` 에서 run_start/node_complete/done 이벤트 emit
  * `cli/prompts.py` — `get_ticker()` 에 종목명 검색 플로우 추가 (6자리는 종전대로)
  * `pyproject.toml` — `[project.optional-dependencies].web` 추가 (`fastapi`, `uvicorn[standard]`, `sse-starlette`), `api*` 패키지 include
  * `.github/workflows/ci.yml` — test job 설치 명령을 `.[dev,web]` 로 확장
* **작업 배경:**
  * CLI 반복 비용 (종목코드 암기, 날짜/옵션 반복 입력, 리포트 수동 열람) 을 줄이기 위한 **로컬 전용 웹 UI**. 외부 배포/인증/멀티테넌시는 명시적으로 비범위.
  * 디자인 시스템은 [Impeccable Neo Kinpaku](https://github.com/pbakaus/impeccable) 를 vendored 로 통합해 로컬에서 oklch 토큰 번들링까지 검증 완료 (라이선스 Apache 2.0, attribution 주석 보존).
  * 기존 Task 13 (CLI 종목 검색) 은 공통 모듈 (`krx_symbol_search`) 하나로 CLI/웹 양쪽에 제공하므로 **이 에픽에 흡수**.
* **작업 내용:**
  * 공통 검색 모듈 (`krx_symbol_search`): pykrx 로 KOSPI/KOSDAQ 전종목 수집 (keyless), `~/.tradingagents/cache/krx_tickers_YYYYMMDD.json` 캐시. 6자리 숫자는 정확 매칭, 그 외는 startswith → contains 순 사전순 정렬.
  * FastAPI 백엔드: `/api/health`, `/api/symbols/search`, `/api/runs` (POST/GET/SSE), `/api/reports` (목록/단건). SSE 는 `sse-starlette` 로 replay + push.
  * 분석 실행: `asyncio.run_in_executor` 로 `TradingAgentsGraph.propagate(debug=True, progress_callback=emit)` 를 별도 스레드에서, 콜백은 `call_soon_threadsafe` 로 메인 루프 큐에 안전 전달.
  * 리포트 뷰어: 디스크 (`~/.tradingagents/logs/reports/<ticker>_<stamp>/`) 를 소스 오브 트루스로 삼아 프로세스 재시작 후에도 이력 복구. `report_id` 는 엄격 regex (`^\d{6}_\d{8}_\d{6}$`), 폴더 화이트리스트 + `resolve().relative_to(root)` 로 경로 traversal 방어.
  * Astro 프론트엔드: Impeccable kinpaku 토큰만 사용, React island (`client:load`) 로 자동완성/실행/뷰어 인터랙션. 마크다운은 `marked` + `DOMPurify` 런타임 sanitize.
  * CLI `get_ticker()` 확장: 비-숫자 입력을 `krx_symbol_search.search` 로 처리, 결과 수에 따라 자동 선택(1) / 번호 선택(2–20) / 재프롬프트(0 또는 >20).
* **범위 밖 (명시적):**
  * 원격 호스팅, 인증/로그인, 멀티테넌시.
  * WebSocket 양방향 통신 (SSE 단방향으로 충분).
  * 모바일 전용 UI (기본 반응형만).
* **DoD:**
  * `uvicorn api.main:app` + `cd web && npm run dev` 로 종목 검색 → 분석 → 리포트 열람 전 플로우 로컬 동작.
  * 기존 CLI 리그레션 0 (`pytest -q` 통과).
  * `.[dev,web]` CI 매트릭스 통과.
  * `README.md` 에 Astro+FastAPI 섹션 추가.
