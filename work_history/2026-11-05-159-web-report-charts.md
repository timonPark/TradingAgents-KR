# [#159] 웹 보고서 화면에서도 차트·한눈에 보기 표시

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/159
- PR: https://github.com/timonPark/TradingAgents-KR/pull/160
- 브랜치: feat/159-web-report-charts
- 작업 기간: 2026-11-05

## 수행한 변경

- `web/src/components/ReportFrame.tsx` + `.css` 신규: `GET /api/reports/{id}/download?format=html` 을 `fetch` 로 받아 `<iframe sandbox="" srcDoc>` 로 표시. 404(차트 기능 이전 보고서)·실패·로딩 상태 안내.
- `web/src/components/ReportViewer.tsx`: 맨 앞·기본 선택 탭 "차트 보고서" 추가 (파일 목록에 없는 가상 섹션).
- `web/src/components/RunPanel.tsx`: 분석 완료(`report_saved`) 뒤 같은 차트 보고서를 진행 화면에도 표시.

## 설계 결정 변경 사항

- 이슈 제안의 `GET /api/reports/{id}/view` 는 만들지 않았다. `fetch` 는 `Content-Disposition: attachment` 를 무시하므로 기존 다운로드 엔드포인트를 그대로 쓰면 API 변경 없이 같은 효과다 (경로 검증도 그대로 재사용).
- iframe 높이는 고정(80vh, 내부 스크롤). `sandbox=""`(스크립트·같은 출처 접근 차단)라 부모가 내용 높이를 읽을 수 없다.

## 검증 결과

- 실제 알테오젠 보고서(`196170_20261105_175009`)를 웹 화면(`/report?id=…`)에서 열어 "한눈에 보기"(판정 흐름·가격 레벨)가 iframe 안에 그려지는 것을 스크린샷으로 확인. (헤드리스 크롬은 site isolation 을 꺼야 iframe 이 캡처된다 — 기본 설정에서는 빈 화면으로 찍히는 캡처 한계.)
- `astro build` 통과, `ruff check .` 통과. 웹 쪽 테스트 프레임워크는 없다.

## 다음 작업 핸드오프

- PDF 다운로드는 차트가 깨짐 (WeasyPrint 가 페이지 CSS 변수/클래스를 인라인 SVG 에 적용하지 못함) — 별도 이슈.
