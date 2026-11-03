# [#109] Task 14d: 종목 검색 UI (자동완성 + 결과 리스트)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/109
- PR: (작업 완료 후 추가)
- 상위 에픽: #105
- 브랜치: `feat/109-symbol-search-ui`
- 작업 기간: 2026-11-04

## 범위

Task 14 (#105) 하위 — 14b (#107, FastAPI) 의 `/api/symbols/search` 와 14c (#108, Astro) 의 홈 스캐폴드를 연결. **입력 → debounce → 자동완성 결과 → 번호/키보드 선택** 흐름 완성.

이 티켓은 **검색 UI 범위만**. "분석 시작" 라우팅은 14e 에서.

## 수행한 변경

- `web/package.json` — React/`@astrojs/react` 의존성 추가 (`npx astro add react --yes`)
- `web/astro.config.mjs` — `@astrojs/react` integration 등록
- `web/src/components/SymbolSearch.tsx` 신규 — 자동완성 React 아일랜드
- `web/src/components/SymbolSearch.css` 신규 — kinpaku 디자인 가드 적용
- `web/src/pages/index.astro` — hero 안에 `<SymbolSearch client:load />` 배치, placeholder CTA 를 **"선택된 종목으로 분석 시작"** 안내 상태로 교체
- `web/.env.example` 신규 — `PUBLIC_API_BASE` 설명

## 설계 결정

### 왜 React (Vue/Svelte 가 아닌)

Astro 아일랜드 중 React 가 가장 광범위하게 쓰이고, `@astrojs/react` 가 공식 패키지. 사용자가 다른 선호 표현한 적 없음.

### 왜 `client:load` (not `client:visible`)

홈 hero 바로 밑 **히어로의 메인 CTA** 성격 — 접속 즉시 interactive 해야 함. `client:visible` 은 스크롤 뒤에 보이는 요소에 적합.

### 디바운스 300ms, limit 20

- 300ms: 타이핑 중 과도한 API 호출 방지, UX 지연 느끼지 않는 범위
- 20: 결과 리스트가 화면에 자연스럽게 담기는 상한. 초과 시 **"더 좁혀서 검색하세요"** 힌트.

### API base URL 과 환경변수

- 기본값: `http://localhost:8000` (14b 의 uvicorn 기본 포트)
- `import.meta.env.PUBLIC_API_BASE` 로 override — `web/.env.example` 에 `PUBLIC_API_BASE=http://localhost:8000` 샘플
- Astro 는 `PUBLIC_` 접두사 변수만 브라우저 번들에 노출 — 서버 비밀 변수는 포함 안 됨

### 키보드 매핑

- `ArrowDown` / `ArrowUp`: 커서 이동 (wrap)
- `Enter`: 커서 아래 결과 선택
- `Escape`: 드롭다운 닫기
- 마우스 호버: 커서 동기

### `.ks-tag.is-ready` / `.is-neutral`

Impeccable kit 의 상태 태그 재활용:
- KOSPI → `.is-ready` (활성/승인 상태 뉘앙스)
- KOSDAQ → `.is-neutral` (중립)

색은 kinpaku-kit.css 가 정의. 하드코딩 안 함.

### abort 이전 요청

디바운스 타이머가 발화해 fetch 가 날아간 뒤 사용자가 계속 타이핑하면, 이전 요청을 `AbortController` 로 취소 — 응답 경합 방지.

## 검증 결과

- `cd web && npm run build` → **1 page built in 368ms**
- React island code-split 확인 — `dist/_astro/` 에 `SymbolSearch.*.js`, `react.*.js`, `client.*.js` 분리 생성
- 전수 `pytest -q` → **874 passed** (Python 리그레션 없음)
- `ruff check .` → clean
- 로컬 수동 (리뷰어 몫): `uvicorn api.main:app --port 8000` + `cd web && npm run dev` 동시 기동 → 홈에서 "삼성" 입력 → 자동완성 목록 + 선택 UX 확인

## 다음 작업 핸드오프

- #110 (14e): 선택된 종목 + 날짜/분석가 설정 + "분석 시작" 라우팅
- #112 (14g): CLI (`cli/prompts.py`) 에도 14a 모듈 연결
