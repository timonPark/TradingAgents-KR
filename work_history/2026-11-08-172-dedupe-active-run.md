# [#172] 같은 종목·기준일 분석이 이미 돌고 있으면 새로 시작하지 않기

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/172
- PR: (PR 생성 후 기재)
- 브랜치: feat/172-dedupe-active-run
- 작업 기간: 2026-11-08

## 수행한 변경

- `api/run_store.py`: `RunStore.find_active(ticker, trade_date)` 신규 — 같은 종목·기준일의 `pending`/`running` 분석을 반환 (없으면 `None`).
- `api/routes/runs.py`: `POST /api/runs` 가 시작 전에 `find_active` 를 확인한다. 이미 있으면 새로 시작하지 않고 `{run_id: <기존>, already_running: true}` 를 **200** 으로 반환. 새로 시작하면 기존대로 **201**, `already_running: false`. `RunCreated` 에 `already_running` 필드 추가(기본 false).
- `tests/test_api_runs.py`: 7건 추가 (중복 시 기존 run 반환·새 그래프 미시작, pending 중복, 설정이 달라도 중복, 다른 종목/기준일은 새 분석, done/error 는 중복 아님).

## 설계 결정 변경 사항

이슈 #172 가 "서버 쪽 결정" 으로 남긴 항목들을 아래처럼 정했다 (`code_artifact.md` 계획과 충돌하는 것은 없음).

- **(a) 기존 `run_id` 반환(200) 채택, (b) 409 는 채택하지 않음.** 클라이언트 변경이 가장 적다. 웹 `RunPanel.tsx` 는 `response.ok` 만 보므로 200 도 그대로 동작하고, 기존 run 의 SSE 를 replay 로 이어 받는다. krx-screener 는 `already_running` 으로 새로 시작했는지 구별할 수 있다.
- **설정(`effort`, `analysts`, 모델)이 달라도 같은 종목·기준일이면 같은 분석으로 본다.** 상태 로그가 `results_dir/{종목}/TradingAgentsStrategy_logs/full_states_log_{기준일}.json` (`trading_graph.py`) 로 설정과 무관한 경로라서, 설정이 달라도 동시에 돌리면 서로 덮어쓴다. 이슈에서 "추정" 이던 덮어쓰기 경로는 코드로 확인했고, 실제로 겹쳐 돌려 보지는 않았다.
- 기존에 돌고 있는 분석과 다른 설정을 요청해도 그 설정은 무시된다 (응답이 `already_running: true` 이므로 클라이언트가 알 수 있다).

## 검증 결과

- `pytest` 1205 passed (25 deselected, 기존 live 테스트), 새 테스트 7건은 구현 전에 실패(red) 확인 후 통과.
- `ruff check tradingagents cli tests api` — 통과.
- 확인과 등록 사이에 `await` 가 없어 단일 이벤트 루프에서는 동시 요청이 끼어들지 못한다 (코드 경로로 확인, 별도 동시성 테스트는 없음).

## 다음 작업 핸드오프

- 한계 (이슈의 "확인하지 못한 것" 그대로): `run_store` 가 프로세스 메모리라서 워커를 여러 개 띄우면 워커끼리 서로 보이지 않아 중복 방지가 되지 않는다. `--reload` 재시작 시에는 상태가 사라진다. 이번 PR 에서도 확인·해결하지 않았다.
- 한계: 어떤 이유로 `running` 에서 끝나지 못한 분석(스레드가 영영 안 끝남)이 있으면 같은 종목·기준일 요청이 계속 그 `run_id` 로 연결된다. 취소 API(#173) 가 생기면 해소 경로가 된다.
- #171(목록 필터)이 들어오면 krx-screener 의 `GET /api/runs` 우회가 필요 없어진다.
