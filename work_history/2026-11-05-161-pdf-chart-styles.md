# [#161] PDF 다운로드에서 차트가 깨짐 — 인라인 SVG 스타일

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/161
- PR: https://github.com/timonPark/TradingAgents-KR/pull/162
- 브랜치: fix/161-pdf-chart-styles
- 작업 기간: 2026-11-05

## 수행한 변경

- `tradingagents/report_html.py`
  - `svg_print_css()`: `_CSS` 의 `.viz` 차트 규칙에서 `.viz `/`svg ` 접두사를 떼고 `var(--x)` 를 밝은 `:root` 팔레트 값으로 치환한 literal CSS. `font:` 단축 속성은 `font-weight/size/family` 로 풀어 쓴다.
  - `prepare_html_for_pdf(html)`: 각 `<svg>` 첫머리에 위 CSS 를 `<style>` 로 넣고, `</head>` 앞에 PDF 전용 보정(`.masthead .rating { white-space: nowrap }`)을 넣는다.
- `api/routes/reports.py`: `_render_pdf` 가 파일을 읽어 `prepare_html_for_pdf` 를 거친 뒤 WeasyPrint 로 변환.
- `tests/test_report_html.py`: literal 규칙·팔레트·주입·브라우저 HTML 불변·PDF 안 색상 연산자(rg) 테스트 5건.

## 원인과 설계 결정

- WeasyPrint(70) 는 페이지 CSS 를 인라인 SVG 에 적용하지 않는다 (선택자 형태·`var()` 여부와 무관). SVG 안의 `<style>`(literal 색)과 요소 속성만 적용된다. → 막대·판정 흐름 상자가 검정으로 채워졌다.
- WeasyPrint SVG 는 `font: 600 15px a, b, "c"` 단축 속성을 잘못 읽어 ▲▼ 글자가 거대해졌다 → 개별 속성으로 풀어 쓴다.
- 팔레트는 `@media print` 가 아니라 밝은 `:root` 값을 쓴다: print 는 `--accent` 를 검정으로 덮어써 `.s1`(잉크)·`.s2`(강조) 선이 구분되지 않는다.
- 브라우저용 `complete_report.html` 은 바꾸지 않는다 (다크 모드·CSS 변수 유지). PDF 변환 때만 손보므로 이미 저장된 보고서의 PDF 도 고쳐진다.
- 표지 `비중 축/소` 줄바꿈은 WeasyPrint flex 레이아웃 문제 → PDF 전용 `white-space: nowrap`.

## 검증 결과

- 실제 알테오젠 보고서(`196170_20261105_175009`) PDF 페이지 이미지 확인: 판정 흐름(▲ 약한 강세 → ▼ 비중 축소 …), 가격 이동평균·볼린저·MACD 선/막대·투자자 수급 막대가 색과 모양대로 나옴. 표지 등급 한 줄.
- 고치기 전/후 PDF 안 채우기 색: 이전 `{0 0 0}` 만 → 이후 초록(#087a59)·빨강(#b4372f) 포함 (테스트로 고정).
- `pytest` 1124 passed, `ruff check .` 통과.
- 변이 검사: SVG `<style>` 주입 제거 시 2건, `font:` 단축 풀기 제거 시 4건 실패.

## 다음 작업 핸드오프

- PDF 66쪽 (A4) — 길이/쪽 나눔 최적화는 별도 판단.
- 결정 대기: 색상 규칙(한국식 상승 빨강/하락 파랑), #152 되돌리기 여부.
