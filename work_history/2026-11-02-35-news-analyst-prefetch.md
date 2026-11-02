# [#35] Task 3c: news_analyst 사전조회 전환

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/35
- PR: (작업 완료 후 추가)
- 상위 에픽: #32
- 브랜치: `feat/35-news-analyst-prefetch`
- 작업 기간: 2026-11-02 ~

## 범위

Task 3a/3b 와 동일 패턴을 news_analyst 에 적용. 모든 분석가 (market/fundamentals/news) 가 사전조회 패턴으로 전환되어 **더 이상 tool-using 분석가가 남지 않습니다** — Task 3d (#36) 가 ToolNode/take_turn/WRAP_UP 전면 삭제 가능 상태.

## 수행한 변경

### `news_analyst.py` 리라이트

- `_NEWS_WINDOW_DAYS = 7` — 최근 1주일 뉴스 창
- `_MACRO_INDICATORS` 튜플 — 선조회할 거시 지표 (cpi/core_pce/unemployment/fed_funds_rate/10y_treasury/yield_curve)
- `_PREDICTION_TOPICS` 튜플 — 선조회할 예측 시장 토픽 ("Fed rate cut", "recession 2026")
- `_news_window(trade_date)` — (start_date, end_date) 1주일 창 반환
- `_prefetch_news_data(ticker, trade_date)`:
  - `get_news`, `get_global_news` 선조회
  - 거시 지표는 `_MACRO_INDICATORS` 전부를 돌며 각각 선조회해 섹션별로 모음
  - 예측 시장은 `_PREDICTION_TOPICS` 전부를 돌며 각각 선조회
  - 각 실패는 섹션 에러 메시지로 다운그레이드 (fail-safe)
- `_render_prefetched(data, asset_label)` — Markdown 블록 포맷 (crypto/stock 대응)
- `create_news_analyst(llm)`: `take_turn` → `invoke_once`, 프롬프트 선조회 데이터 주입

### `analyst_execution.py`

- `ANALYST_NODE_SPECS["news"]` 의 `tools=news_analyst.TOOLS` 제거 → `tools=()`
- `news_analyst` 미사용 import 제거 (**분석가 import 전부 제거됨**)

### 테스트 조정

- `test_structured_agent_prompts.py::test_tool_using_analysts_keep_their_date_guidance` **삭제** (주석으로 교체) — 더 이상 tool-using 분석가가 없음.
- `test_news_analyst_prompt.py::test_news_prompt_matches_get_news_signature` 를 `test_news_module_uses_window_not_query` 로 교체 — "프롬프트에 서명 명시" 검증에서 "선조회 코드가 query 를 재도입하지 않음" 검증으로 전환.
- `test_graph_end_to_end.py`:
  - `tool_turns 1*3 → 0`
  - `wrap_ups 1 → 0`
  - debug run 에서 `get_news` 체크 제거, 보고서 생성 성공만 검증

## 설계 결정 변경 사항

### 예측 시장 토픽 선정

LLM 이 원래 자유 입력으로 `get_prediction_markets(topic, ...)` 를 호출하던 흐름 — 사전조회에서는 고정 토픽을 사용해야 함. 원래 프롬프트에 예시로 나오던 "Fed rate cut", "recession 2026" 을 그대로 사용. 추가 토픽이 필요하면 `_PREDICTION_TOPICS` 를 확장.

### 거시 지표 선정

원래 프롬프트가 추천하던 핵심 지표 (cpi/core_pce/unemployment/fed_funds_rate/10y_treasury/yield_curve) 를 그대로 사전조회. 각 지표를 별도 호출해 섹션별로 모아 Markdown 블록으로 포맷.

## 검증 결과

- `pytest -q` → **1158 passed, 8 subtests passed** (전환으로 하나의 테스트 삭제됨)
- `ruff check` → **All checks passed**

## 다음 작업 핸드오프

### Task 3d (#36): sentiment 감사 + 최종 삭제

이번 PR 로 **모든 분석가가 사전조회 패턴으로 전환 완료**. Task 3d 가 실행할 삭제 작업:

1. **sentiment_analyst 감사**: 이미 bind_tools 미사용. 필요 시 패턴 정리.
2. **`turn.py` 삭제** — `invoke_once` 를 `agents/__init__.py` 또는 신규 `agents/invoke.py` 로 이동. `WRAP_UP`, `take_turn`, `_as_text` 제거.
3. **`graph/setup.py` 정리**:
   - `from langgraph.prebuilt import ToolNode` import 삭제
   - `_tools_or_done`, `_analyst_graph` 의 tool 분기 로직 삭제 (모든 spec 이 tools=() 이므로 fast-path 만 남음)
   - `WRAP_UP` import 제거
4. **각 분석가의 `TOOLS` 상수 삭제** 또는 유지 결정 (문서화 가치만 있음)
5. **`analyst_execution.py::AnalystNodeSpec.tools` 필드 삭제** — 사용처 없음
6. **test_graph_end_to_end.py 의 Task 3c 로 비워진 테스트 3개 삭제 또는 재작성**

이번 전환 완료로 **분석가당 Claude Code 호출 3~5회 → 1회 축소** 가 달성됨 (ADR-0002 목표).
