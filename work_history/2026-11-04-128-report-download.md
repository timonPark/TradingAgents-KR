# [#128] Feat: 리포트 뷰어에 다운로드 (md/html/zip) 버튼 추가

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/128
- 브랜치: `feat/128-report-download`
- 작업 기간: 2026-11-04

## 범위

Task 14f (#120 머지) 로 리포트 뷰어는 추가됐지만 사용자가 파일로 저장할 방법이 없었음. `/report` 상단에 **다운로드 그룹** 신설.

## 수정

### `api/routes/reports.py`
- `GET /api/reports/{report_id}/download?format=md|html|zip` 신규
- `_safe_report_dir()` — regex + `resolve().relative_to(root)` 로 traversal 차단
- `md`: `complete_report.md` 를 `text/markdown; charset=utf-8` + `attachment` 로
- `html`: `complete_report.html` 그대로
- `zip`: 루트의 `complete_report.{md,html}` + 화이트리스트 섹션 (`analysts/research/trading/risk/portfolio`) 안의 `.md/.html` 만. 메모리 BytesIO, DEFLATED.
- 파일명: `trading_report_{report_id}.{ext}`

### `web/src/components/ReportViewer.tsx`
- `report-head` 하단에 **`.report-downloads`** 그룹 — 3개 `.ks-button-ghost` 링크
- `<a download>` 로 브라우저가 알아서 저장 다이얼로그 띄움

### `web/src/components/ReportViewer.css`
- `.report-downloads` 플렉스 랩 + gap 8px, ghost 버튼은 0.875rem / padding 축소

### `tests/test_api_reports.py`
- 신규 8개: md/html/zip 각각 attachment, filename, mime 검증. zip 은 실제로 열어 멤버 확인. 비-화이트리스트 폴더 제외. invalid report_id → 400, 알 수 없는 format → 422, 파일 없음 → 404.

## 검증

- `pytest tests/test_api_reports.py -v` → **16 passed** (기존 8 + 신규 8)
- `pytest -q` 전수 → **916 passed, 11 deselected** (회귀 없음)
- `ruff check .` → clean
- `cd web && npm run build` → 2 pages / 324ms
