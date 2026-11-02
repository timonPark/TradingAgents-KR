# [#33] Task 3a: 공통 인프라 + market_analyst 사전조회 전환

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/33
- PR: (작업 완료 후 추가)
- 상위 에픽: #32
- 브랜치: `feat/33-market-analyst-prefetch`
- 작업 기간: 2026-11-02 ~

## 범위

Task 3 (분석가 노드 사전조회 리팩터링, ADR-0002) 의 **첫 분석가 전환**. 공통 helper 를 도입하고 market_analyst 를 전환합니다. 다른 분석가들(fundamentals/news) 은 아직 `take_turn` 사용 — Task 3b (#34), 3c (#35) 에서 전환, 3d (#36) 에서 ToolNode/take_turn 최종 삭제.

## 수행한 변경

### 공통 인프라 — `tradingagents/agents/analysts/turn.py`

- `invoke_once(prompt, llm, messages)` 신규 추가:
  - 사전조회 패턴 분석가용 — 단일 LLM 호출
  - 사전조회 데이터는 호출부가 `prompt.partial(...)` 로 이미 주입했다는 전제
  - 반환은 `(result, result.content)` 로 기존 `take_turn` 과 호환
- 기존 `take_turn()` 과 `WRAP_UP` 는 유지 (news/fundamentals 분석가가 Task 3b/3c 전까지 사용)
- 모듈 docstring 에 Task 3 전환 설명 추가

### market_analyst 전환 — `tradingagents/agents/analysts/market_analyst.py`

- `_INDICATORS` 상수 신규 — 12개 기술적 지표 전량 (사용자가 선택할 수 없으니 Python 이 전부 선계산해 프롬프트에 주입)
- `_OHLCV_WINDOW_DAYS = 365` — 200 SMA 등 장기 지표 안정화에 ~250 거래일 필요하므로 넉넉히 1년
- `_ohlcv_start_date(trade_date)` — trade_date 로부터 1년 전 날짜
- `_prefetch_market_data(ticker, trade_date)` — 세 함수 (`get_stock_data`, `get_indicators`, `get_verified_market_snapshot`) 를 `.invoke({...})` 로 직접 호출. 각 함수 실패 시 분석가 전체 중단 대신 섹션에 에러 메시지를 담아 반환 (fail-safe).
- `_render_prefetched(data)` — 선조회 데이터를 Markdown 블록으로 포맷
- `create_market_analyst(llm)` 리라이트:
  - 분석가 노드 진입 시 Python 이 데이터 선조회
  - 프롬프트 시스템 메시지를 "데이터가 사전조회되어 있다; 지표 선택만 하라" 로 교체
  - `take_turn(prompt, llm, TOOLS, messages)` → `invoke_once(prompt, llm, messages)` 로 교체
  - `{tool_names}` 플레이스홀더 제거, `{prefetched}` 플레이스홀더 추가
- `TOOLS` 상수는 유지 (문서화 용도, Task 3d 가 완전 삭제할 때까지)

### 그래프 구조 — `tradingagents/graph/analyst_execution.py`

- `ANALYST_NODE_SPECS["market"]` 에서 `tools=market_analyst.TOOLS` 제거 → `tools=()` (디폴트)
- 이로 인해 `_analyst_graph(spec, ...)` 가 market 분석가에게는 ToolNode/조건부 엣지를 **구성하지 않음** (fast path: `graph.add_edge("agent", END)`)
- `market_analyst` import 제거

### 테스트 업데이트

Task 3a 는 market 전환이므로 다음 테스트들을 수치 조정:
- `tests/test_structured_agent_prompts.py::test_tool_using_analysts_keep_their_date_guidance`: 체크 대상에서 `market` 제거. 주석에 Task 3 순차 전환 안내.
- `tests/test_graph_end_to_end.py::test_an_analyst_that_keeps_calling_tools_writes_its_report_at_the_limit`: `len(tool_turns) == 3*3` → `2*3` (market 가 더 이상 tool 사용 안 함)
- `tests/test_graph_end_to_end.py::test_the_last_turn_is_offered_no_tools_and_reads_its_tool_results_as_text`: `len(wrap_ups) == 3` → `2`
- `tests/test_graph_end_to_end.py::test_a_debug_run_prints_the_analysts_work_and_reaches_the_same_decision`: 체크 대상에서 `get_stock_data` 제거, `get_news` 추가 (news 가 아직 tool 사용)

## 설계 결정 변경 사항

### Fail-safe 선조회

`_prefetch_market_data` 는 각 함수 호출을 `try/except` 로 감싸고 실패 시 에러 메시지를 섹션에 담아 반환합니다. 분석가 전체를 중단시키지 않고 LLM 이 "데이터 없음" 을 보고서에 명시할 수 있도록 — Task 1 어댑터의 free-text 폴백 철학과 일관.

### `TOOLS` 상수 유지

market_analyst 는 더 이상 `bind_tools` 를 호출하지 않지만 `TOOLS` 상수는 **문서화 용도로 유지**. 코드 리더가 "이 분석가가 어떤 데이터 함수를 쓰는가?" 즉시 알 수 있도록. Task 3d (#36) 에서 ToolNode/take_turn 전면 삭제 시 함께 제거 검토.

## 검증 결과

- `pytest -q` → **1159 passed, 8 subtests passed** (전체 스위트)
- `ruff check tradingagents cli tests` → **All checks passed**
- Smoke: `_ohlcv_start_date("2026-09-23")` → `"2025-09-23"` 정상
- 분석가 임포트 및 helper 동작 확인

E2E Claude Code 호출 테스트는 실제 데이터 vendor 가 아직 Yahoo/Alpha Vantage 라 KRX 종목에서 안 돌아감 — Task 6 (pykrx) 완료 후 end-to-end 실측 가능.

## 다음 작업 핸드오프

### Task 3b (#34): fundamentals_analyst 사전조회 전환
- 같은 패턴 적용. 재무/공시 데이터 (`get_fundamentals`, `get_balance_sheet`, `get_income_statement`, `get_cashflow`, `get_insider_transactions`) 선조회.
- `ANALYST_NODE_SPECS["fundamentals"]` 의 `tools=` 제거.

### Task 3c (#35): news_analyst 사전조회 전환
- 뉴스 데이터 (`get_news`, `get_global_news`, `get_macro_indicators`, `get_prediction_markets`) 선조회.
- `ANALYST_NODE_SPECS["news"]` 의 `tools=` 제거.

### Task 3d (#36): sentiment 감사 + 최종 삭제
- sentiment_analyst 는 이미 bind_tools 미사용 (`sentiment_analyst.py:110`) 이라 선조회 패턴에 부합. 미세 정리만.
- `turn.py` 삭제 — `invoke_once` 를 다른 공통 위치로 이동
- `graph/setup.py` 에서 `ToolNode` import, `graph.add_node("tools", ...)`, 조건부 엣지 전부 삭제
- `WRAP_UP` 상수 삭제
- 삭제한 테스트들을 Task 11 로 재작성 (각 분석가 유닛)
