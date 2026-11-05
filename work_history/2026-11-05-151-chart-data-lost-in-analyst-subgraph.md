# [#151] 시장·거시 차트 원본이 분석가 서브그래프에서 사라짐

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/151
- PR: (작성 후 기입)
- 브랜치: fix/151-chart-data-lost-in-analyst-subgraph
- 작업 기간: 2026-11-05 ~ 2026-11-05

## 문제

PR #147(시장 분석가 차트)·#148(거시 지표 차트)을 머지했지만 실제 분석의 보고서에는 이 차트들이 나오지 않는다. 한눈에 보기(판정 흐름·가격 레벨)는 최종 결정 텍스트에서 읽으므로 영향이 없었다.

## 원인

각 분석가는 서브그래프(`graph/setup.py::_analyst_graph`)로 실행되고 서브그래프는 `output_schema` 에 선언된 키만 부모 상태로 내보낸다. 스키마가 `{report_key: str}` 뿐이라, 분석가 노드가 반환한 `market_data`/`macro_data` 가 최종 `final_state` 로 올라오지 못했다. `render_report` 는 `None` 을 받아 "원본 없는 예전 run" 경로(차트 영역 생략)로 갔다.

## 왜 못 잡았나

#147/#148 의 테스트는 `final_state` 를 직접 만들어 렌더러에 넘기거나 분석가 노드를 단독 호출해서 "노드 → 서브그래프 → 최종 상태" 구간을 통과하지 않았다. 전체 그래프 실행 테스트도 이 키를 확인하지 않았다. 다음 작업(#149)의 전체 실행 테스트에 차트 원본 키 확인을 추가하다가 발견했다.

## 수행한 변경

- `tradingagents/graph/analyst_execution.py` — `AnalystNodeSpec.data_key` 추가 (market → `market_data`, news → `macro_data`)
- `tradingagents/graph/setup.py` — 서브그래프 `output_schema` 에 `data_key` 포함
- `tests/test_analyst_execution.py` — 서브그래프를 실제로 통과하는 회귀 테스트(`invoke`), 데이터 키 없는 분석가는 보고서만 내보내는지
- `tests/test_graph_end_to_end.py` — 전체 그래프 실행의 최종 상태에 `market_data`/`macro_data` 가 있는지, 그 상태로 저장한 `complete_report.html` 에 차트 영역이 생기는지

## 설계 결정 변경 사항

없음.

## 검증 결과

- `pytest` 전체 통과 (1072), `ruff check .` 통과
- 수정(`setup.py`)을 되돌리면 새 테스트 3건이 실패하고 복원하면 통과하는 것을 확인

## 다음 작업 핸드오프

- 사용자 영향: 수정 후 **새 분석부터** 시장·거시 차트가 나온다. 이전에 생성한 보고서는 원본이 없어 차트가 없다.
- #149(재무 차트)는 `fundamentals_data` 를 같은 방식(`data_key`)으로 내보내야 한다.
- 교훈: 상태를 직접 만드는 단위 테스트만으로는 "노드가 반환한 키가 최종 상태에 남는가"를 검증할 수 없다. 상태 키를 새로 만들면 전체 그래프 실행 테스트로 확인한다.
