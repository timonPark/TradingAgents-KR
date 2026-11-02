# [#36] Task 3d: sentiment 감사 + ToolNode / take_turn / WRAP_UP 전면 삭제

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/36
- PR: (작업 완료 후 추가)
- 상위 에픽: #32
- 브랜치: `feat/36-toolnode-removal`
- 작업 기간: 2026-11-02 ~

## 범위

Task 3 에픽의 마지막 하위 이슈. 모든 분석가가 사전조회 패턴으로 전환된 상태에서 레거시 ToolNode / `take_turn` / `WRAP_UP` / 조건부 tool 엣지 / `max_tool_rounds` config 를 **전면 삭제**. sentiment_analyst 는 이미 bind_tools 미사용이라 감사만.

## 수행한 변경

### `turn.py` → `invoke.py` 이름 변경 + 내용 축소

- `tradingagents/agents/analysts/turn.py` **삭제**
- `tradingagents/agents/analysts/invoke.py` **신규** — `invoke_once` 함수만 포함 (약 10줄)
- 삭제된 심볼: `take_turn`, `WRAP_UP`, `_as_text`, 관련 imports (`AIMessage`, `HumanMessage`, `ToolMessage`, `json`)
- market/fundamentals/news 분석가의 import 경로 업데이트

### `graph/setup.py` 전면 정리

- `from langgraph.prebuilt import ToolNode` **삭제**
- `from langchain_core.messages import HumanMessage` **삭제** (더 이상 WRAP_UP 메시지를 조립할 필요 없음)
- `from tradingagents.agents.analysts.turn import WRAP_UP` **삭제**
- `from collections import Counter` **삭제**
- `_tools_or_done()` 함수 **삭제** (조건부 엣지 로직)
- `_analyst_graph()` **재작성**: 모든 spec 이 사전조회 전환되었으므로 fast-path 하나만 — `START → agent → END`. `max_tool_rounds` 매개변수와 WRAP_UP/calls/rounds 헬퍼 삭제.
- `GraphSetup.__init__` 에서 `max_tool_rounds` 매개변수 삭제

### `graph/trading_graph.py`

- `max_tool_rounds` config 추출과 `2 * max_tool_rounds + 2 >= max_recur_limit` 검증 로직 삭제
- `GraphSetup(..., max_tool_rounds)` 생성 인자 삭제

### `default_config.py`

- `_ENV_OVERRIDES` 에서 `TRADINGAGENTS_MAX_TOOL_ROUNDS` 매핑 삭제
- `build_default_config` 에서 `"max_tool_rounds": 20` 디폴트 삭제

### `graph/analyst_execution.py`

- `AnalystNodeSpec.tools: tuple = ()` **필드 삭제** — 모든 spec 이 더 이상 참조 안 함
- 각 spec 선언에서 `tools=()` 문구 정리, Task 3a/3b/3c 전환 주석 통합

### 분석가 파일에서 `TOOLS` 상수 삭제

- `market_analyst.py`, `fundamentals_analyst.py`, `news_analyst.py` 의 `TOOLS = (...)` 상수와 그 주석 삭제. 어차피 더 이상 참조되지 않음.

### 테스트 삭제 및 정리

**삭제된 테스트 (3개):**
- `test_an_analyst_that_keeps_calling_tools_writes_its_report_at_the_limit` (#1420)
- `test_the_last_turn_is_offered_no_tools_and_reads_its_tool_results_as_text`
- `test_a_tool_limit_the_recursion_limit_cannot_hold_is_refused`

**삭제된 fixture:**
- `LoopingModel` 클래스 — 위 3개 테스트에서만 사용되던 tool-loop 시뮬레이터

**수정된 테스트:**
- `test_a_debug_run_prints_the_analysts_work_and_reaches_the_same_decision` → `test_a_debug_run_streams_the_analysts_and_reaches_the_same_decision` (tool call 로그 체크 제거, 스트리밍이 동작하는지만 유지)

### sentiment_analyst 감사

- `sentiment_analyst.py` 는 이미 bind_tools 를 호출하지 않고 Reddit/StockTwits/get_news 를 선조회하는 패턴 (`sentiment_analyst.py:110` 주석 참조).
- `invoke.py` 로 전환이 필요한 부분 없음 — `structured.py` 기반 structured output 흐름을 그대로 유지.
- 변경 사항 없음.

## 설계 결정 변경 사항

### `turn.py` → `invoke.py` 리네이밍

파일 이름 `turn.py` 는 `take_turn()` 함수에서 유래했는데, 그 함수가 삭제되었으므로 이름이 더 이상 의미 없음. `invoke.py` 로 리네이밍해 **"분석가가 단일 LLM 호출을 하는 단위"** 를 더 정확히 표현.

## 검증 결과

- `pytest -q` → **1155 passed, 8 subtests passed** (삭제된 3개 테스트 반영)
- `ruff check` → **All checks passed**

## Task 3 에픽 (#32) 종결

이 PR 머지 후 Task 3 에픽의 모든 하위 이슈 close 가능:

- #33 (3a) ✅ market_analyst 전환 — 머지됨
- #34 (3b) ✅ fundamentals_analyst 전환 — 머지됨
- #35 (3c) ✅ news_analyst 전환 — 머지됨
- #36 (3d) **이 PR** — sentiment 감사 + ToolNode/take_turn/WRAP_UP 전면 삭제

**ADR-0002 목표 달성:**
- MCP 서버 브리지 없이도 분석가 노드가 작동
- 분석가당 Claude Code 호출 **3~5회 → 1회**
- LangGraph 그래프 구조 단순화 (각 분석가 서브그래프가 2노드 → 1노드)

## 다음 작업 핸드오프

### Task 4 (티커 유효성 검증) 또는 Task 5·6·7 (데이터 vendor 교체)

데이터 레이어 교체 작업으로 진입. Task 4~8 이 vendor 함수의 **구현** 을 KRX 전용으로 바꾸되 **인터페이스는 유지** 하므로 분석가 선조회 코드는 재변경 불필요. Task 3 에서 확립한 사전조회 패턴 위에서 동작.
