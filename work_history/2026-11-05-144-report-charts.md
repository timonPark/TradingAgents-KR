# [#144] 보고서 HTML 차트 — 1단계 (인프라 + 시장 분석가 차트)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/144 (이 PR 로 닫지 않음 — 2·3단계와 ECOS 차트 남음)
- PR: https://github.com/timonPark/TradingAgents-KR/pull/147
- 브랜치: feat/144-report-charts
- 작업 기간: 2026-11-05 ~ 2026-11-05

## 문제

이전에 공유된 보고서에는 SVG 차트가 9~10개 있었지만 현재 파이프라인의 `complete_report.html` 에는 차트가 없다(로고 1개). 차트 생성 코드가 저장소에 없었고, `render_report` 는 에이전트 마크다운만 받아 원본 수치가 없다. 시장 분석가의 사전조회 결과는 프롬프트에만 주입되고 버려졌다.

## 수행한 변경

- `tradingagents/agents/state.py`, `analysts/market_analyst.py` — 사전조회 원본(`ohlcv`/`indicators`/`investor_flow` 문자열)을 `final_state["market_data"]` 로 보존. 차트에 쓰지 않는 스냅샷은 제외.
- `tradingagents/charts.py` 신규 (순수 함수, I/O 없음)
  - 파서: `parse_ohlcv`, `parse_indicator`(N/A 건너뜀, `boll` 이 `boll_ub` 블록을 먹지 않음), `parse_investor_flow`(KRX 표·네이버 합계 행 두 형식)
  - SVG: `line_chart`, `histogram_chart`, `investor_flow_chart` (정적 인라인 SVG, `role="img"` + `aria-label`, 선은 색 외에 모양도 다름)
  - `build_market_charts`: 가격+50/200일 이동평균, 볼린저 밴드(최근 30일), MACD 히스토그램, RSI(30/70), 투자주체별 순매수(KRX 억 원·세부 포함 / 네이버 주)
  - 실패는 빈 차트가 아니라 `ChartGap`("차트 없음 — 사유")으로 표시. `market_data` 가 없으면(예전 run) 차트 영역 자체를 만들지 않음.
- `tradingagents/report_html.py` — 시장 분석가 텍스트 뒤에 차트 삽입, 차트 CSS(페이지 변수 사용, 라이트/다크). CSP 변경 없음(스크립트·외부 리소스 없음).
- `tests/test_charts.py` 신규(24), `test_report_html.py`·`test_structured_agents.py` 보강. 파서 입력은 가능한 한 실제 포매터 출력(`naver_investor.get_investor_flow`, KRX 시리즈 `to_markdown`)으로 만들어 vendor 형식 변경을 잡는다.

## 설계 결정 변경 사항

없음. 단, 차트 데이터는 LLM 본문이 아니라 사전조회 원본에서만 그린다는 원칙을 이슈에 명시했고 그대로 구현.
이동평균은 OHLCV 종가에서 직접 계산(단순 산술이라 vendor 값과 동일), 볼린저·MACD·RSI 는 vendor 지표 값을 파싱.

## 검증 결과

- `pytest` 전체 통과 (1040), `ruff check .` 통과
- 실제 데이터(`034020` OHLCV·지표)로 보고서 페이지를 생성해 헤드리스 Chrome 으로 렌더 확인
- 파서에 변형(헤더 매칭)을 넣어 테스트가 실제로 실패하는지 확인

## 다음 작업 핸드오프

- #144 남은 항목: ECOS 시계열 차트(국고채·환율, 뉴스 분석가 매크로 데이터 보존 필요), 2단계(한눈에 보기 판정 흐름·가격 레벨), 3단계(재무 — DART 재무제표 구조화 선행).
- 색: 페이지 기존 토큰(`--up` 초록 / `--down` 빨강)을 그대로 썼다. 한국 증시 관례(상승=빨강)와 반대라 바꿀지 결정 필요.
- 이미 생성된 보고서에는 `market_data` 가 없어 차트가 없다. 새 분석부터 표시.
