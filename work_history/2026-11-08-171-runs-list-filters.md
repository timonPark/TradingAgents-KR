# [#171] 분석 목록 API(GET /api/runs)에 종목·기준일·상태 필터와 보고서 본문 제외 옵션 추가

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/171
- PR: (PR 생성 후 기재)
- 브랜치: feat/171-runs-list-filters
- 작업 기간: 2026-11-08

## 수행한 변경

- `api/run_store.py`: `RunStore.list_recent` 에 선택 인자 `ticker`, `trade_date`, `status` 추가. **거른 뒤에** 최신순 `limit` 을 적용한다.
- `api/routes/runs.py`: `GET /api/runs` 에 쿼리 파라미터 `ticker`, `trade_date`, `status`(`pending|running|done|error`), `include_reports`(기본 `true`) 추가. `include_reports=false` 면 목록 항목의 `reports` 가 `{}` 로 나간다. `_snapshot` 에 `include_reports` 인자.
- `tests/test_api_runs.py`: 5건 추가 (조건 없을 때 기존과 동일, 세 필터와 AND 조합, 알 수 없는 status 422, 필터 후 limit, 본문 제외·단건 조회에는 본문 유지).

## 설계 결정 변경 사항

`code_artifact.md` 와 달라진 지점 없음. 이슈가 열어 둔 부분은 아래처럼 정했다.

- 조건을 안 주면 응답이 지금과 같다 (하위 호환). `reports` 는 **목록에서만** 뺀다 — `GET /api/runs/{id}` 단건은 그대로 본문을 준다.
- `status` 는 4개 값만 받고 그 밖의 값은 422. `ticker`/`trade_date` 는 형식 검사 없이 문자열 일치로만 거른다 (맞는 것이 없으면 빈 목록). 생성 요청(`POST`)과 달리 조회라서 형식 오류를 따로 거절할 이유가 없다고 봤다.
- 응답 필드를 줄이는 옵션은 `include_reports` 하나만 만들었다 (이슈 제안 그대로). 다른 필드 선택 기능은 만들지 않았다.

## 검증 결과

- `pytest` 전체 통과, 새 테스트는 구현 전 실패(red) 확인 후 통과. `ruff check tradingagents cli tests api` 통과.
- 테스트의 생성 시각은 직접 지정해 시계 해상도와 무관하게 순서를 고정했다.
- **이슈의 측정값(1.4MB → 감소량)은 이번에 다시 측정하지 않았다.** 이슈도 "속도보다 전송량과 오래된 분석을 못 찾는 점이 문제" 라고 했고, 본문을 빼면 항목당 `reports` 가 `{}` 가 되는 것은 테스트로 확인했다.

## 다음 작업 핸드오프

- 한계 (이슈의 "확인하지 못한 것" 그대로): `run_store` 는 프로세스 메모리라 서버를 다시 켜면 목록이 비고, 쌓이는 개수 제한·보존 규칙은 보지 않았다 (이 PR 에서도 안 바꿨다).
- krx-screener 는 이제 `GET /api/runs?ticker=…&trade_date=…&status=running&include_reports=false` 로 도는 분석을 가볍게 확인할 수 있다. #172(PR #177)로 서버가 중복을 직접 막으므로 클라이언트 우회가 필요 없어진 점과 함께 정리할 수 있다.
