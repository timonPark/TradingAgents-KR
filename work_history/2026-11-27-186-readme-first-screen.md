# [#186] README 첫 화면 재구성 — 결과물 중심 소개 + 샘플 + Quick Start 단순화

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/186
- 상위 에픽: https://github.com/timonPark/TradingAgents-KR/issues/183
- PR: (생성 후 기입)
- 브랜치: docs/186-readme-first-screen
- 작업 기간: 2026-11-27

## 수행한 변경

- `README.md` 첫 화면을 이슈 순서대로 재구성
  1. 한 줄 소개 "DART 공시와 외국인·기관 수급을 반영한 AI 애널리스트 리포트." + 무엇을 하는지 두 문장
  2. 실제 결과물: `docs/examples/005930-samsung/` 의 스크린샷 2장을 나란히(각 49%), 최종 등급과 판정 흐름 한 줄,
     전체 리포트(`report.md`)·샘플 설명(`docs/examples/README.md`) 링크
  3. 면책 고지 (기존 문구 그대로, 위치만 샘플 바로 아래)
  4. Quick Start 3단계: 설치 → Claude Code 로그인 + DART 키 → `tradingagents`. 준비물(Python 3.11+, Claude Max/Pro,
     Open DART 키)을 먼저 적고, 플래그 실행·웹 UI·Docker·선택 키는 기존 섹션 링크로
  5. Based on: 기존 소개 문단(하드 포크, Claude Code 헤드리스)을 출처 문단으로 옮기고 인용 섹션 링크 추가
- Tauric 로고(폭 60%)를 맨 위에서 "기반 프로젝트 및 인용" 섹션 머리로 이동. Upstream·arXiv 배지는 맨 위 유지.
- Based on 문단의 `**Claude Code CLI 헤드리스(OAuth)**를` 강조가 GitHub 에서 깨지던 문제 수정
  (닫는 `**` 앞이 `)` 이고 뒤가 한글이면 강조로 인식되지 않음. 원래 README 에도 있던 문제).

## 설계 결정 변경 사항

- 로고 이동은 이슈에 없던 결정이다. 로고가 첫 화면 높이의 상당 부분을 차지해 "스크롤 없이 샘플이 보인다" 조건을
  맞출 수 없었다. 삭제가 아니라 인용 섹션으로 옮겨 출처 표기는 유지했다.
- 스크린샷은 원본(1100×1300)을 49% 폭으로 줄여 글자는 읽기 어렵다. 첫 화면에서는 "등급과 흐름이 담긴 리포트" 라는
  인상만 주고, 클릭하면 전체 리포트로 간다.
- 링크는 `report.html` 이 아니라 `report.md` 로 걸었다. GitHub 은 HTML 을 렌더링하지 않고 소스로 보여준다.

## 검증 결과

- 링크 검사 스크립트: README 의 상대 경로·`#앵커` 22개 모두 유효 (GitHub 슬러그 규칙으로 앵커 계산)
- 로컬 절대경로(`/Users/...`) 없음
- 화면 검증: GitHub Markdown API(`gh api markdown`, gfm)로 렌더링 → github-markdown-css → 헤드리스 Chrome 캡처
  - 1280×900: 배지·제목·소개·샘플 스크린샷 2장·등급 줄이 스크롤 없이 보이고 면책 문구가 바로 아래에 걸침
  - 렌더 결과에서 처리 안 된 `**` 없음 (수정 후)
  - 모바일(390px) 캡처는 헤드리스 Chrome 의 최소 창 폭 때문에 오른쪽이 잘려 판단 불가 — 확인 못함
- 저장소 홈에서는 README 가 파일 목록 아래에 나오므로, 여기서 말하는 "첫 화면" 은 README 영역의 첫 화면이다.
- 코드 변경 없음 → pytest·ruff 해당 없음
- 위험도: 문서만 변경. 다만 외부 방문자가 처음 보는 화면이라 파급 범위 1개 → `risk:low`

## 다음 작업 핸드오프

- 에픽 #183: 하위 이슈 #184·#185·#186 이 모두 끝나면 에픽 완료 조건을 사용자와 확인 후 닫는다.
  에픽 본문 체크리스트의 #184 가 이미 닫혔는데 `[ ]` 로 남아 있어 갱신 필요.
- 범위 밖 발견: 없음.
