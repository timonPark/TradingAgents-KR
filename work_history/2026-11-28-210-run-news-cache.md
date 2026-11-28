# [#210] 한 실행 안에서 종목뉴스 get_news 결과 재사용

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/210
- PR: https://github.com/timonPark/TradingAgents-KR/pull/215
- 브랜치: feat/210-run-news-cache
- 작업 기간: 2026-11-28

## 수행한 변경

- `tradingagents/dataflows/run_cache.py` 신규
  - 실행 범위 캐시: `ContextVar` 하나에 dict 를 둔다.
  - `cached(key, fetch, keep)`: 범위 안에서는 키별 첫 결과를 재사용하고, 범위 밖에서는 매번 조회한다.
  - 분석가는 병렬로 돌므로 키마다 잠금을 둔다. 동시에 같은 키를 조회하면 나중 호출이 먼저 호출의 결과를 기다린다(vendor 1회).
  - `keep` 이 거짓인 결과와 예외는 저장하지 않는다.
- `tradingagents/dataflows/config.py`: `run_config` / `run_config_context` 가 실행마다 새 캐시를 연다. 실행 경로 3곳(`propagate`, `stream_run`, 웹 UI 용 스트림)이 모두 이 둘을 거친다.
- `tradingagents/agents/tools.py` `get_news`
  - 날짜 창을 정규화(`as_of_window`)한 뒤 `("get_news", ticker, start, end)` 키로 캐시한다.
  - `DATA_UNAVAILABLE` 결과는 저장하지 않는다.
  - 범위는 이슈대로 종목뉴스만이다. 다른 도구는 건드리지 않았다.
- 테스트
  - `tests/test_run_cache.py` 신규 9건
    - 범위 밖에서는 매번 조회, 범위 안에서는 재사용, 키 분리
    - 실행 간 비공유(`run_config` / `run_config_context` 둘 다)
    - 실패 결과와 예외는 저장하지 않음
    - 병렬 호출 시 1회 조회
    - 뉴스 분석가(`invoke` + trade_date)와 감성 분석가(`.func`)의 같은 기간 조회 재사용
  - `tests/test_graph_end_to_end.py` 2건
    - 전체 실행(`propagate`)과 스트림 실행(`stream_run`)에서 종목뉴스 vendor 호출이 1회인지
    - 다음 실행은 새로 조회하는지
    - 캐시를 빼면 이 테스트가 `2 == 1` 로 실패함을 확인했다.

## 설계 결정 변경 사항

없음.

## 검증 결과

- `ruff check tradingagents cli tests` — 통과
- `pytest` — 1326 passed
- 실제 네이버 API 측정(LLM 호출 없음). 005930, 기준일 2026-11-26 으로 뉴스 분석가 + 감성 분석가 사전조회를 한 실행 범위에서 돌렸다. API HUB 는 500건 한도로 넘어가고 `naver_news` 가 응답했다(#212).

  | | 종목뉴스 HTTP 요청 | 시간 | 두 분석가 결과 동일 |
  |---|---|---|---|
  | 수정 전 | 210회 | 22.0초 | 예 |
  | 수정 후 | 105회 | 7.5초 | 예 |

## 위험도

`risk:medium`
- 파급 범위: 모든 실행의 실행 범위 진입점(`run_config`)을 거친다.
- 민감도: 데이터 vendor 연동 경로다.
- 변경 주기: config 모듈은 안정적인 코드지만 변경이 작아 해당하지 않는 것으로 본다.

## 다음 작업 핸드오프

- 측정 중에도 API HUB 가 500건 한도로 매번 실패해 `naver_news` 로 넘어갔다. 실패한 API HUB 호출(5쪽)도 매번 쓰이므로 #212 에서 다룬다.
