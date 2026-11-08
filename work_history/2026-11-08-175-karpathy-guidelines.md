# [#175] CLAUDE.md 에 작업 태도 원칙(Karpathy 지침) 추가

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/175
- PR: https://github.com/timonPark/TradingAgents-KR/pull/176
- 브랜치: docs/175-karpathy-guidelines
- 작업 기간: 2026-11-08

## 수행한 변경

- `CLAUDE.md`: §4.7 "작업 태도 원칙 (Karpathy 지침 기반)" 신규. 출처는 forrestchang/andrej-karpathy-skills 의 4개 원칙(코딩 전에 생각하기 / 단순함 우선 / 외과적 변경 / 목표 기반 실행)이며, 이 프로젝트 규칙에 맞춰 조정했다.
  - 이슈 범위·`code_artifact.md` 가 모호하면 구현 전에 확인.
  - 외부 경계(`claude` subprocess, 데이터 vendor 응답)는 "일어날 수 없는 에러 처리 금지" 의 예외.
  - 범위 밖 발견은 새 이슈 후보로 기록, 기존 dead code 는 삭제하지 않고 PR/핸드오프에 언급.
  - 외부 LLM SDK 제거처럼 이슈가 명시적으로 삭제를 요구한 경우는 외과적 변경 원칙의 대상이 아님.
  - 검증은 §4.3 (`ruff`, `pytest`) 와 `work_history/` 검증 결과에 연결.

## 설계 결정 변경 사항

없음. (`code_artifact.md` 와 무관한 문서 변경. 원본의 Cursor 규칙·`EXAMPLES.md`·플러그인 설치 안내는 이 프로젝트에 쓸 곳이 없어 가져오지 않았다.)

## 검증 결과

- 문서 변경만 있어 `pytest`/`ruff` 대상 없음.
- 기존 §1~§4.6 번호·내용 변경 없음 (diff 는 §4.6 과 "참조 문서" 사이 추가만).

## 다음 작업 핸드오프

- 없음. 운영하면서 4.7 이 실제로 PR 크기·질문 빈도에 영향을 주는지 보고 문구를 조정할 수 있다.
