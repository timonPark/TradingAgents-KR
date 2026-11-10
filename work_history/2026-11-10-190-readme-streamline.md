# [#190] README 전체 정돈 — 중복 섹션 통합, 내부 이슈/Task 표기 제거, 스펙 동기화

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/190
- PR: 
- 브랜치: docs/190-readme-streamline
- 작업 기간: 2026-11-10

## 수행한 변경

- `README.md`
  - 상단 소개 및 빠른 시작(Quick Start) 단순화, 면책 고지 상단 배치
  - 중복 섹션 통합: 로컬 웹 UI 안내, 출처(Based on / Upstream 관계), 면책 조항, DART 공시 설명 일원화
  - 내부 관리용 표기 제거: Task 1~14 완료 체크리스트, 본문 내 `Task 14g / #112`, `Task 2 (#21)` 등 이슈/Task 번호 제거
  - 코드베이스 스펙 일치화:
    - 패키지 설치를 `pip install -e .` 및 `pip install -e ".[web]"`으로 통합 (pyproject.toml 기반)
    - 환경변수 설명에 `KRX_ID`/`KRX_PW` 및 네이버 증권 폴백 설명 보강
    - 티커 정규식을 최신 영숫자 코드 지원(`^[0-9A-Z]{6}$`)으로 동기화
    - 제거된 `temperature` 대신 현재 LLM 어댑터의 `effort` / `quick_effort` 기준 설정법 안내
    - 하드 포크 정책에 맞춰 upstream 주기적 병합 관련 모순 문구 제거

## 설계 결정 변경 사항

없음. 에픽 #183 (Task 15) 범위 내의 문서 정돈.

## 검증 결과

- `ruff check tradingagents cli tests` — 통과 (All checks passed)
- `README.md` 내부 앵커 링크 유효성 확인
- 기존 493줄에서 259줄로 축소 (~47% 감축)

## 다음 작업 핸드오프

- 에픽 #183의 후속 태스크(#185 삼성전자 샘플 리포트 생성) 진행 시 README에 샘플 링크/이미지 연결 가능.
