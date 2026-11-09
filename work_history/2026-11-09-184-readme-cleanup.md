# [#184] README 정리 — WIP 제거, 완료 체크리스트 갱신, 절대경로 제거

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/184
- 상위 에픽: https://github.com/timonPark/TradingAgents-KR/issues/183 (Task 15)
- PR: (작성 후 기록)
- 브랜치: docs/184-readme-cleanup
- 작업 기간: 2026-11-09

## 수행한 변경

- `README.md`
  - `Status-WIP` 배지와 "⚠️ 진행 상태 (WIP)" 경고 삭제 (뒤따르던 중복 `---` 구분선도 정리).
  - "작업 체크리스트"(구 번호 Task 1~6, 전부 `[ ]`)를 `code_artifact.md` 기준 완료 항목 12개(Task 1~9, 11, 12, 14)로 교체. Task 10·13 은 `code_artifact.md` 에 없다(13 은 Task 14 에 흡수).
  - Quick Start 의 `/Users/2309-n0018/...` 절대경로 2곳을 `TradingAgents-KR` 기준 상대경로로 교체.

## 설계 결정 변경 사항

없음. 에픽 #183 의 범위(코드 변경 없음) 안에서 문서만 고쳤다.

## 검증 결과

- `grep -n '/Users/\|WIP' README.md` — 결과 없음.
- `ruff check tradingagents cli tests` — 통과 (문서만 바꿔서 테스트는 돌리지 않음).
- 체크리스트 대조: 에픽 #1·21·32·41·46·51·61·74·79·91·97·105 전부 CLOSED 확인.

## 다음 작업 핸드오프

- #186 (README 첫 화면 재구성) 이 같은 파일을 고친다. 이 PR 머지 후 그 위에서 작업하거나, 머지 전이면 이 브랜치에서 갈라서 시작한다.
- 이번 범위 밖으로 남긴 것: `git clone <this-repo-url>` placeholder (#186 에서 실제 URL 로), README 본문 중 "Task 14g / #112" 같은 내부 이슈 번호 표기.
