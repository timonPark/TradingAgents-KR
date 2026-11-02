# [#34] Task 3b: fundamentals_analyst 사전조회 전환

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/34
- PR: (작업 완료 후 추가)
- 상위 에픽: #32
- 브랜치: `feat/34-fundamentals-analyst-prefetch`
- 작업 기간: 2026-11-02 ~

## 범위

Task 3a (#33) 에서 확립한 사전조회 패턴을 fundamentals_analyst 에 적용. market_analyst 와 동일한 흐름을 재무/공시 데이터로 재사용.

## 수행한 변경

### `tradingagents/agents/analysts/fundamentals_analyst.py` 리라이트

- `_prefetch_fundamentals_data(ticker, trade_date)` 신규:
  - `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_insider_transactions` 를 `.invoke({...})` 로 직접 호출
  - balance_sheet / cashflow / income_statement 는 `freq="quarterly"` — 분기 리포팅이 최신 트렌드를 더 잘 반영
  - 각 함수 실패 시 섹션에 에러 메시지만 담아 반환 (fail-safe, market_analyst 와 동일 패턴)
- `_render_prefetched(data)` 신규 — Markdown 블록 포맷
- `create_fundamentals_analyst(llm)` 리라이트:
  - 분석가 노드 진입 시 Python 이 데이터 선조회
  - 프롬프트를 "data pre-fetched; do not call tools" 로 교체
  - `take_turn` → `invoke_once`
- `TOOLS` 상수는 문서화 용도로 유지

### `tradingagents/graph/analyst_execution.py`

- `ANALYST_NODE_SPECS["fundamentals"]` 에서 `tools=fundamentals_analyst.TOOLS` 제거 → `tools=()`
- `fundamentals_analyst` 미사용 import 제거

### 테스트 수치 조정

- `test_an_analyst_that_keeps_calling_tools_writes_its_report_at_the_limit`: `tool_turns 2*3 → 1*3` (news 하나만 tool-using)
- `test_the_last_turn_is_offered_no_tools_and_reads_its_tool_results_as_text`: `wrap_ups 2 → 1`
- `test_a_debug_run_prints_the_analysts_work_and_reaches_the_same_decision`: `get_balance_sheet` 체크 삭제, `get_news` 만 유지
- `test_the_analysts_run_at_the_same_time`: `ScriptedModel._generate` 가 **모든 호출에서** 쓰레드 수집하도록 변경 (사전조회 분석가도 병렬 실행 사실 유지). `self.tools` 조건 삭제 — 사전조회 전환 분석가는 `bind_tools` 를 호출 안 하므로 `self.tools` 가 비어있음.

## 설계 결정 변경 사항

### `ScriptedModel._generate` 테스트 fixture 변경

사전조회 분석가는 `bind_tools` 를 호출하지 않으므로 ScriptedModel 의 `self.tools` 가 비어있어 기존 `threads.add` 분기가 실행되지 않습니다. `test_the_analysts_run_at_the_same_time` 가 깨지는 걸 막기 위해 **tools 유무와 무관하게 모든 `_generate` 호출에서 쓰레드를 수집** 하도록 변경. 테스트 의도("분석가가 병렬로 돈다") 는 변하지 않음 — 측정 대상만 "tool-bound 호출" → "모든 LLM 호출" 로 넓어짐.

## 검증 결과

- `pytest -q` → **1159 passed, 8 subtests passed**
- `ruff check` → **All checks passed**

## 다음 작업 핸드오프

### Task 3c (#35): news_analyst 사전조회 전환
동일 패턴. 뉴스 데이터 (`get_news`, `get_global_news`, `get_macro_indicators`, `get_prediction_markets`) 선조회. `ANALYST_NODE_SPECS["news"]` 의 `tools=` 제거.
Task 3c 완료 시점: `len(tool_turns) == 0`, `wrap_ups == 0`, `get_news` 체크 삭제.

### Task 3d (#36): sentiment 감사 + 최종 삭제
- sentiment_analyst 패턴 미세 정리
- `turn.py` 삭제 (`invoke_once` 를 다른 공통 위치로)
- `graph/setup.py` 에서 `ToolNode`, `graph.add_node("tools", ...)`, 조건부 엣지, `WRAP_UP` import 전부 삭제
- 이번 PR 에서 수치 조정한 테스트들을 완전 삭제 또는 Task 11 로 분산
- 각 분석가의 `TOOLS` 상수 (`market_analyst`, `fundamentals_analyst`, `news_analyst`) 삭제
