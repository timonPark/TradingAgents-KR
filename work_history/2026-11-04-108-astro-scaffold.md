# [#108] Task 14c: Astro 프론트엔드 스캐폴드 + Impeccable kit 통합

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/108
- PR: (작업 완료 후 추가)
- 상위 에픽: #105 (Task 14)
- 브랜치: `feat/108-astro-scaffold`
- 작업 기간: 2026-11-04 ~

## 범위

Task 14 (#105) 하위 — **Astro 프론트엔드 스캐폴드** 와 **Impeccable Neo Kinpaku 디자인 시스템** vendored 통합. 이 티켓은 **"뼈대와 디자인 셋업"** 만 담당; 실제 기능(검색/실행/리포트) 은 14d~14f 에서 추가.

리스크 우선 원칙에 따라 14b (FastAPI) 보다 먼저 진행 — Astro × Impeccable kit 궁합이 작동하는지, kinpaku-tokens 의 `oklch` 가 Astro 번들에 잘 녹아드는지 **먼저 검증**하기 위함.

## 수행한 변경

- `web/` 신규 디렉터리
  - `package.json`, `astro.config.mjs`, `tsconfig.json`
  - `src/layouts/Base.astro` — kinpaku 토큰 + kit CSS 로드
  - `src/pages/index.astro` — 홈 (워드마크 + hero + "분석 시작" placeholder 버튼)
  - `src/styles/kinpaku-tokens.css` — Impeccable vendored (Apache 2.0)
  - `src/styles/kinpaku-kit.css` — Impeccable vendored (Apache 2.0)
  - `src/styles/app.css` — 페이지 전역 커스텀 (최소)
  - `public/favicon.svg`
- `.gitignore` — `web/node_modules/`, `web/dist/`, `web/.astro/` 추가

## 설계 결정

### vendored 전략 (fetch 대신 복사)

- 소스: `/Users/2309-n0018/Project/impeccable/ui/component-review/vendor/kinpaku-tokens.css` (221 줄), `kinpaku-kit.css` (728 줄)
- 두 파일 모두 상단에 `/* VENDORED from impeccable-site/site/styles/... */` attribution 주석을 이미 가지고 있음 — 그대로 유지
- 라이선스: Apache 2.0 (impeccable) · 이 프로젝트와 호환
- **npm 패키지 또는 CDN 미사용** — 오프라인 빌드 보장, 로컬 환경에서 외부 의존 없음
- 업데이트는 수동 (impeccable 레포에서 CSS 가 바뀔 때만)

### light paper 모드 기본

Impeccable 최신 vendored tokens 는 **light paper** 모드가 기본 (`color-scheme: light`, 종이 질감 + 잉크 텍스트 + 다크 instrument). DESIGN.md 의 구버전 "dark lacquer 기본" 과 다름. vendored tokens 가 소스 오브 트루스이므로 그대로 따름.

### `web/` 를 모노레포 루트에 두는 이유

`apps/web/` + `apps/api/` 식 모노레포 레이아웃도 고려했지만, 기존 `tradingagents/` / `cli/` 가 이미 루트 평면 구조. 일관성 유지를 위해 `web/`, `api/` 도 루트 평면.

### 홈 페이지 뼈대 요소 (이 티켓 범위)

- 워드마크 "TRADINGAGENTS KR" (`.ks-wordmark`)
- Hero 텍스트 (디스플레이 폰트, h1)
- 짧은 리드 문단
- **Placeholder** CTA 버튼 (`.ks-button.ks-button-primary`) — 실제 라우팅 은 14d 에서

(종목 검색 자동완성, 분석 설정 폼, 실행 패널 등은 **이 티켓 범위 아님**.)

### Impeccable npx 설치는 선택

`npx impeccable install` 로 `/impeccable critique`, `/polish` 등 Claude Code 명령을 활성화할 수 있지만 이 PR 에선 **제외**. 후속 PR 에서 결정.

## 검증 결과

- `cd web && npm run build` → **1 page built in 442ms** (타입 체크 포함, 에러/경고 없음)
- 빌드 산출물 `web/dist/_astro/index.*.css` 에 Impeccable 토큰 반영 확인:
  - `ks-kinpaku` 14회 · `ks-patina` 15회 · `ks-paper` 16회 · `ks-ink` 26회 · `ks-font` 10회
- `npm run dev` 수동 확인은 리뷰어가 로컬에서 진행 (DoD 항목)
- Astro 7.4.5 + TypeScript strict (minimal template)

## `.gitignore` 결정

Astro 가 생성한 `web/.gitignore` 가 `node_modules/`, `dist/`, `.astro/`, `.env*` 를 모두 커버. 루트 `.gitignore` 에 중복 패턴을 추가하는 대신 **web 디렉터리 로컬 `.gitignore` 에 위임**. (이슈 본문의 DoD "루트 .gitignore 에 `web/node_modules/` 추가" 는 중복이므로 미적용.)

## 다음 작업 핸드오프

- #107 (14b): FastAPI 백엔드 스캐폴드 — 이 PR 머지 후 시작
- #109 (14d): 종목 검색 UI — 14b + 14c 가 모두 머지된 뒤
