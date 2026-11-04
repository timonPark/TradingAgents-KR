# [#128] Feat: 리포트 뷰어에 다운로드 (md/html/pdf) 버튼 추가

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/128
- 브랜치: `feat/128-report-download`
- 작업 기간: 2026-11-04

## 범위

Task 14f (#120 머지) 로 리포트 뷰어는 추가됐지만 사용자가 파일로 저장할 방법이 없었음. `/report` 상단에 **다운로드 그룹** 신설.

## 수정

### `api/routes/reports.py`
- `GET /api/reports/{report_id}/download?format=md|html|pdf` 신규
- `_safe_report_dir()` — regex + `resolve().relative_to(root)` 로 traversal 차단
- `md`: `complete_report.md` 를 `text/markdown; charset=utf-8` + `attachment`
- `html`: `complete_report.html` 그대로
- `pdf`: `complete_report.html` 을 **WeasyPrint** 로 변환. `base_url` 을 리포트 디렉터리로 지정해 상대 경로 이미지도 처리. weasyprint 미설치 시 503 + 설치 안내
- 파일명: `trading_report_{report_id}.{ext}`

**사용자 요청에 따라 ZIP 포맷 제외**, 대신 PDF 추가.

### `pyproject.toml`
- `[web]` extra 에 `weasyprint>=62.0` 추가

### `web/src/components/ReportViewer.tsx`
- `report-head` 하단에 **`.report-downloads`** 그룹 — 3개 `.ks-button-ghost` 링크 (md · html · pdf)
- `<a download>` 로 브라우저가 알아서 저장 다이얼로그 띄움

### `web/src/components/ReportViewer.css`
- `.report-downloads` 플렉스 랩 + gap 8px, ghost 버튼은 0.875rem / padding 축소

### `tests/test_api_reports.py`
- 신규 8개: md/html/pdf 각각 attachment, filename, mime 검증. PDF 는 `%PDF` magic 과 크기로 실제 변환 확인. invalid report_id → 400, 알 수 없는 format → 422, 파일 없음 → 404
- `pytest.importorskip("weasyprint")` 로 미설치 환경 보호

## 검증

- `pytest tests/test_api_reports.py -v` → **16 passed** (기존 8 + 신규 8)
- `pytest -q` 전수 → **916 passed, 11 deselected** (회귀 없음)
- `ruff check .` → clean
- `cd web && npm run build` → 2 pages / 346ms
- PDF 변환 smoke: 한글 포함 HTML → 2.7MB PDF 생성 확인 (`%PDF` magic OK)
