# ADR-0002: 분석가 노드 사전조회 패턴 채택 (LangGraph ToolNode·MCP 미사용)

- 상태: Accepted
- 날짜: 2026-11-02
- 관련 이슈/문서: `code_artifact.md` Task 3, [[CLAUDE.md]] 금지사항 §4.6, [[GLOSSARY.md]] "사전조회 패턴"

## 문제 상황 (Context)

상류 TauricResearch/TradingAgents 는 분석가 노드가 LangChain `llm.bind_tools(tools)` 로 Python 함수를 LLM 에 바인딩하고, LangGraph `ToolNode` 가 실행하는 패턴을 사용한다 (`tradingagents/agents/analysts/turn.py:26`, `tradingagents/graph/setup.py:85`). 분석가가 "먼저 get_stock_data 호출 → 결과 보고 get_indicators 호출" 식으로 라운드를 돌며 보고서를 완성한다.

이 포크는 LLM 백엔드로 Claude Code 헤드리스를 선택했다 (ADR-0001). Claude Code 는 별도 subprocess 로 실행되므로 Python 함수 객체를 직접 바인딩할 수 없다. 두 가지 브리지 방안을 검토했다:

1. **MCP 서버 브리지**: pykrx/DART 함수를 MCP 프로토콜로 노출하고 `claude -p --mcp-config` 로 등록. LLM 이 MCP 툴을 호출하면 서버가 Python 함수를 실행.
2. **사전조회 + 프롬프트 주입**: 분석가 노드 진입 전에 Python 이 필요한 데이터를 미리 조회해 프롬프트 문자열에 주입. LLM 은 데이터를 받아 보고서만 작성.

실제 상류 코드를 확인한 결과:
- 분석가의 툴 집합은 **정적으로 하드코딩** 되어 있다 (`market_analyst.py:8`: `TOOLS = (get_stock_data, get_indicators, get_verified_market_snapshot)`).
- `bind_tools` 를 호출하는 지점은 `turn.py:26` **단 한 곳** 이며, 분석가 4개만 거쳐 간다 (리서처·디베이터·매니저·트레이더는 툴 없이 동작).
- Claude Code subprocess 콜드 스타트는 호출당 2~10초. 분석가당 3~5회 호출이면 1회 분석에 수십 분 추가.

LLM 의 "동적 툴 선택" 이 주는 가치는 **툴 집합이 고정** 인 이 상황에서 사실상 없다. MCP 서버는 자유도를 보존하지만 그 자유도가 쓰이지 않는다.

## 결정 (Decision)

**MCP 서버 브리지를 포기하고 사전조회 + 프롬프트 주입 패턴을 채택한다.**

- `tradingagents/agents/analysts/turn.py` 의 `take_turn()` 과 WRAP_UP 로직을 삭제한다. 분석가는 단일 LLM 호출로 완결.
- `tradingagents/graph/setup.py` 의 `ToolNode(list(spec.tools))` 노드와 조건부 엣지(`continue_tool_use`) 를 삭제한다.
- 분석가 노드(`market_analyst.py`, `fundamentals_analyst.py`, `news_analyst.py`, `sentiment_analyst.py`) 는 LLM 호출 전에 Python 이 필요한 모든 데이터를 선조회해 Markdown 표/문자열로 포맷 후 프롬프트에 주입한다.
- 어댑터의 `ChatClaudeCodeHeadless.bind_tools(tools)` 는 `NotImplementedError` 를 명확히 발생시킨다 — 호출 자체를 에러로 가시화.
- 분석가 프롬프트의 "툴을 호출해..." 문구를 "주어진 데이터를 기반으로..." 로 교체한다.

## 결과 (Consequences)

**긍정:**
- 분석가당 Claude Code 호출이 **3~5회 → 1회** 로 감소. 분석 1건 지연시간 수십 분 → 수 분.
- MCP 서버 구현/배포/디버깅 부담 전무 — 단일 Python 스택에서 모든 데이터 흐름 추적 가능.
- Claude Code `--permission-mode plan` 과 충돌 없음 (MCP 툴 호출 자체가 사라지므로 승인 모델 고민 불필요).
- Docker 통합 단순화 — MCP 서버 프로세스 생명주기 관리 불필요.
- 테스트가 단순해진다 — 분석가 노드는 "입력 데이터 → 출력 보고서" 결정론적 함수.

**부정:**
- LLM 이 "지표 11개 중 8개만 선택적으로 가져오기" 같은 동적 선택을 할 수 없다. Python 이 11개 전부 선계산하고, LLM 은 "보고서에서 다룰 지표 선택" 만 수행.
- 프롬프트 크기가 증가한다 — 사전조회 데이터 전체가 매 호출마다 전송.
- 상류의 ToolNode 기반 신기능과 호환성 상실 (하드 포크 결정과 일관됨 — ADR-0001).

**완화책:**
- pykrx + stockstats 전 지표 계산 비용은 밀리초 수준으로 과잉 계산 부담 없음.
- Claude Sonnet 4.6 / Haiku 4.5 의 긴 컨텍스트 윈도우가 증가한 프롬프트를 충분히 수용.
- 복잡한 분석이 필요하면 사전조회 단계에서 데이터를 요약·필터링해 주입 가능.

## 고려된 대안 (Alternatives Considered)

**(1) MCP stdio 서버 (단일 또는 다중)**
- 기각 사유: Claude Code subprocess 호출마다 MCP 서버가 콜드 스타트 → 지연 증폭. 분석가 호출 횟수 자체는 그대로이므로 사전조회 대비 느림. 분석가 툴이 정적 집합이라 MCP 가 주는 "동적 발견" 이점이 쓰이지 않음.

**(2) MCP HTTP 서버 (상주)**
- 기각 사유: 콜드 스타트는 제거되지만 분석가당 LLM 호출 횟수(3~5회) 는 그대로 유지. 사전조회 방식의 지연 이점(호출 1회) 을 못 얻음. HTTP 전송 레이어 추가로 복잡도만 증가.

**(3) 텍스트 매개 툴콜 (LLM 이 `TOOL_CALL foo(...)` 출력 → Python 이 파싱 후 실행)**
- 기각 사유: 파싱 취약성 (LLM 이 포맷 어긴 응답 생성 시 전체 실패). 라운드마다 Claude Code 호출로 역시 느림. 안정성 대비 이점 없음.
