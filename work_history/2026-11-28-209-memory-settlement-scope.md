# [#209] Memory Log 정산이 단일 종목 실행을 오래 붙잡는 문제

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/209
- PR: https://github.com/timonPark/TradingAgents-KR/pull/214
- 브랜치: fix/209-memory-settlement-scope
- 작업 기간: 2026-11-28

## 조사 결과

- 실제 메모리 로그(`~/.tradingagents/memory/trading_memory.md`): 전체 427건, 대기 130건.
  - 128건이 2026-11-20 결정(종목 128개 × 1건). 이슈 본문의 "11-13 백테스트" 추정은 틀렸다.
  - 이 128건은 아직 보유 기간(5거래일)이 끝나지 않아 지금은 가격만 확인하고 넘어간다. 가격 확인은 종목당 약 0.04초(캐시)로 부담이 없다.
- 병목은 결정 1건마다 `claude -p` 로 쓰는 반성(reflection)이다 (건당 약 80초). 11-30 무렵 128건이 한꺼번에 기한이 되면, 그 다음 실행 하나가 약 3시간을 반성에 쓴다.
- 실행이 실제로 쓰는 교훈은 본 종목 최대 5건 + 타 종목 최근 3건뿐(`get_past_context`)이다. 타 종목을 한 실행에서 전부 정산할 이유는 약하다. 다만 분석이 멈춘 종목의 결정이 영영 대기로 남지 않게 하는 #1445 의 의도는 유지해야 한다.

## 수행한 변경

사용자와 방향 확인: **본 종목은 전부, 타 종목은 실행당 반성 3건까지**.

- `tradingagents/memory/settlement.py`
  - `Settlement.reflections` 추가: 요청한 반성(모델 호출) 수. 성공·실패 모두 센다.
  - `settle_pending(..., limit=None)`: 반성 요청 수 상한. 정산 기한이 안 된 결정은 반성을 부르지 않으므로 상한에 세지 않는다.
  - `settle_all_pending(..., ticker=None, other_limit=None)`: `ticker` 를 먼저 전부 정산한 뒤, 타 종목은 가장 오래된 결정부터 `other_limit` 건까지만 반성한다. 인자를 주지 않으면 종전처럼 전 종목을 정산한다(스케줄러·외부 호출 호환).
- `tradingagents/graph/trading_graph.py`
  - `_OTHER_TICKER_REFLECTIONS_PER_RUN = 3` 상수.
  - `_memory_step` 이 `ticker=분석 종목, other_limit=3` 으로 호출한다.
  - `settle_all_pending` 메서드에 같은 인자를 전달한다.
- 테스트
  - `tests/test_memory_log.py`
    - 본 종목은 전부 정산하고 타 종목은 3건까지만 정산하는지(오래된 것부터)
    - 남은 건이 다음 실행에서 정산되는지
    - 반성 실패도 상한에 세는지(장애 시 수백 번 호출 방지)
    - 기한이 안 된 결정이 상한을 쓰지 않는지
    - 상한이 없으면 종전처럼 모두 정산하는지
  - `tests/test_graph_end_to_end.py`
    - Memory Log 단계가 분석 종목과 상한을 넘기는지
    - 기존 mock 시그니처 갱신(`locked(**_)`)
  - `tests/test_memory_log.py`: 기존 mock 람다 시그니처 갱신

## 설계 결정 변경 사항

없음 (`code_artifact.md` 범위 밖, upstream #1445 동작에 실행당 상한만 추가).

## 검증 결과

- `ruff check tradingagents cli tests` — 통과
- `pytest` — 1315 passed
- 실제 메모리 로그 사본으로 시뮬레이션: 대기 130건이 모두 기한이 됐다고 가정하고 반성 호출 수를 셌다(`fetch_returns` 고정, 반성 호출 수만 계수).

  | | 대기 | 반성 호출 | 예상 시간(건당 80초) |
  |---|---|---|---|
  | 수정 전 | 130 → 0 | 130회 | 약 173분 |
  | 수정 후 실행 1회 (005930) | 130 → 125 | 5회 (본 종목 2 + 타 종목 3) | 약 7분, 분석가와 동시 진행 |

## 위험도

`risk:medium`
- 파급 범위: 모든 실행의 Memory Log 단계에 영향을 준다.
- 민감도: LLM(claude) 호출 경로다.
- 변경 주기: 정산 모듈은 오래 안정적이던 코드라 해당하지 않는다.

## 다음 작업 핸드오프

- 타 종목 결정 125건을 실행당 3건씩 처리하면 다 정산하는 데 약 42번의 실행이 필요하다. 한꺼번에 정리하려면 `graph.settle_all_pending()`(상한 없음)을 직접 부르는 정산 전용 CLI 명령이 있으면 편하다. 필요할 때 이슈로 등록한다.
- 정산 진행 상황(남은 건수)을 웹 UI 에 보여 주는 것은 범위 밖으로 두었다.
