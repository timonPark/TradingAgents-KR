# [#12] Chore: .github/ 상류 흔적 전면 정리

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/12
- PR: (작업 완료 후 추가)
- 브랜치: `chore/12-cleanup-upstream-github-artifacts`
- 작업 기간: 2026-11-02 ~

## 범위

하드 포크(ADR-0001) 로 상류(TauricResearch/TradingAgents) 추적을 포기한 상태이지만, `.github/` 디렉터리에는 상류의 미국 시장/다중 provider 가정이 그대로 남아있어 사용자 혼란과 CI 불일치를 유발하는 흔적을 정리합니다.

Task 1 (Claude Code 어댑터 구현) 과 **완전히 독립** 적인 설정 정리 작업입니다. main 에서 직접 분기했습니다.

## 수행한 변경

### 1. `.github/workflows/ci.yml`
CI 매트릭스의 non-UTC 타임존 셀을 `America/New_York` → `Asia/Seoul` 로 교체.

- 상류 의도: "UTC 외의 타임존 환경에서도 테스트가 깨지지 않는지 확인" — 좋은 의도.
- 상류의 대표 타임존 선택: NYSE 시장 기준 뉴욕 — **포크에서는 틀림**.
- 포크의 target 운영 타임존: KST (`Asia/Seoul`) — KRX 시장 기준.
- 주석에도 "Asia/Seoul: this fork's target production timezone (KRX markets)" 명시.

### 2. `.github/workflows/release-assets.yml`
주석 안의 pip install 예시 URL 을 상류(`TauricResearch/TradingAgents`) → 포크(`timonPark/TradingAgents-KR`) 로 교체.

워크플로우 자체는 포크의 release 에서도 재사용 가능 (버전 체크, wheel 빌드, release attach 로직 전부 저장소 중립).

### 3. `.github/ISSUE_TEMPLATE/` 디렉터리 전체 삭제
네 파일 삭제: `config.yml`, `bug-report.yml`, `data-issue.yml`, `feature-request.yml`.

재작성이 아닌 삭제로 결정한 이유:
- `config.yml` — discussions/security advisories 링크가 전부 상류 저장소를 가리키며, 포크에 해당 공간을 열 계획이 미정.
- `bug-report.yml` — 포크가 아직 Task 1 수준이라 외부 bug 제보를 받을 단계가 아님. 홍콩 티커(`0700.HK`) 예시 등 무관.
- `data-issue.yml` — 데이터 소스 선택지(StockTwits/Reddit/FRED/Insider transactions/Prediction markets) 가 포크에서 전부 제거/교체 예정이라 상류 템플릿을 그대로 두면 거짓 선택지를 노출.
- `feature-request.yml` — **"OpenAI-compatible provider 로 새 LLM 추가 가능" 안내가 하드 포크 결정(ADR-0001) 과 정면 배치**. 사용자가 provider 추가 요청을 보내는 노이즈 유발. 가장 심각한 흔적.

포크가 공개용으로 성숙하는 시점에 **한국 투자자 대상으로 처음부터 재작성** 하는 것이 상류 템플릿 수정보다 깔끔.

## 설계 결정 변경 사항

없음. code_artifact.md 와 CLAUDE.md 결정에 맞춘 정합성 작업.

## 검증 결과

- 로컬 `pytest` — 변경 사항이 Python 코드에 영향 없음 (CI/템플릿 설정만 수정)
- `ruff check` — 변경 사항이 .yml 파일만 수정 (ruff 범위 외)
- CI 실행 결과 (PR 후 확인):
  - `tests (py3.12, Asia/Seoul)` 셀이 녹색이어야 함 (타임존 변경 후에도 테스트 통과)
  - 다른 매트릭스 셀 (3.11/3.12/3.13/3.14 UTC) 녹색 유지

## 다음 작업 핸드오프

- `tests/test_memory_log.py:1130, 1215` 의 `tz="America/New_York"` 는 **이 PR 범위 밖**. Task 8 (KRX 캘린더 매핑) 작업 시 함께 수정.
- `README.md:44` 의 `NYSE → KRX` 비교표는 설명 문맥이라 **그대로 유지**.
- Task 1b (#3) 작업은 Task 1a (PR #11) 머지 후 재개 (stacked PR 문제로 보류 중).
