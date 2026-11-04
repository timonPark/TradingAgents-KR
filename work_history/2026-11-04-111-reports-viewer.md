# [#111] Task 14f: 리포트 뷰어 + 과거 이력 사이드바

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/111
- 상위 에픽: #105
- 브랜치: `feat/111-reports-viewer`
- 작업 기간: 2026-11-04

## 범위

완료된 분석의 리포트 트리 (`{results_dir}/reports/{ticker}_{stamp}/`) 를 웹에서 열람. 사이드바에서 과거 이력을 넘겨보며 각 리포트의 섹션 (complete/analysts/research/trading/risk/portfolio) 을 탭으로 전환.

## 수행한 변경

### 백엔드
- `api/routes/reports.py` 신규
  - `GET /api/reports?limit=50` — 최근 리포트 트리 목록 (사이드바용)
  - `GET /api/reports/{report_id}` — 단건 리포트 파일 트리
- `api/main.py` — reports 라우터 등록
- `api/reports_store.py` 신규 — `results_dir/reports/` 를 스캔해 리포트 목록/파일을 리턴 (14a 공통 검색으로 ticker→name 보강)

### 프론트엔드
- `web/src/pages/report.astro` 신규 — 리포트 페이지 레이아웃
- `web/src/components/ReportViewer.tsx` 신규 — 사이드바 + 탭 + 마크다운 뷰어 (React island)
- `web/src/components/ReportViewer.css` 신규 — kinpaku
- `web/package.json` — `marked` + `dompurify` 추가 (XSS 방지용 sanitize)

## 설계 결정

### 리포트 ID = `{ticker}_{stamp}` 디렉터리명 그대로
- `{save_path}` 가 `~/.tradingagents/logs/reports/<ticker>_<YYYYMMDD_HHMMSS>/` 패턴 (`trading_graph.default_report_path`)
- 그 디렉터리 이름을 API 수준의 `report_id` 로 그대로 쓴다 — URL-safe, 추적 간단

### 경로 traversal 방어
- `report_id` 는 엄격 regex 로 검증: `^\d{6}_\d{8}_\d{6}$`
- 파일 path 는 `complete_report.md` 또는 `{section}/{file}.md` 패턴만 허용 — `..`, 절대경로, 심볼릭 링크 거부
- `os.path.commonpath` 체크로 results_dir 바깥 접근 방지

### decision 추출
- `complete_report.md` 상단의 `- 등급: Buy` 라인에서 파싱
- 매칭 실패 시 `null`

### 사이드바 집계는 디스크 스캔
- 인메모리 run store (#110) 는 프로세스 수명만 유지되므로, **디스크 리포트 트리** 를 ground truth 로 삼는다 (프로세스 재시작 후에도 이력 복구)

### 클라이언트 측 라우팅 (쿼리 파라미터)
- Astro 동적 라우트 (`[report_id].astro`) 는 static build 시 알려진 path 만 가능
- **로컬 전용** 이라 쿼리 파라미터 `?id=` 로 충분. URL: `/report?id=005930_20261104_083001`

### 마크다운 렌더: `marked` + `dompurify`
- Astro 의 내장 마크다운은 **build-time** 만 — 런타임 렌더가 필요
- `marked` 가 빠르고 작음, `DOMPurify` 로 XSS sanitize

## 검증 결과

- `pytest tests/test_api_reports.py -v` → **8 passed**
- `pytest -q` 전수 → **893 passed, 11 deselected** (회귀 없음)
- `ruff check .` → clean
- `cd web && npm run build` → 2 pages built in 333ms

## 다음 작업 핸드오프

- #112 (14g): CLI (`cli/prompts.py`) 에 14a 공통 검색 모듈 연결 + README / code_artifact.md 반영
