# [#144] 보고서 차트 — 한국은행 거시 지표 + 한눈에 보기 판정 흐름

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/144 (이 PR 로 닫지 않음 — 가격 레벨·재무 차트 남음)
- PR: (작성 후 기입)
- 브랜치: feat/144-report-charts-macro-flow
- 작업 기간: 2026-11-05 ~ 2026-11-05

## 문제

PR #147 로 시장 분석가 차트(가격·볼린저·MACD·RSI·수급)는 들어갔지만, 뉴스 분석가의 한국은행(ECOS) 거시 지표와 에이전트별 판정 흐름("한눈에 보기") 차트가 남아 있었다.

## 수행한 변경

- `tradingagents/agents/state.py`, `analysts/news_analyst.py` — 지표별 ECOS 섹션을 `final_state["macro_data"]` (`{지표 alias: 섹션 문자열}`)로 보존. 프롬프트용 `macro` 문자열은 그대로.
- `tradingagents/charts.py`
  - `parse_ecos_section` (단위·`| 기간 | 값 |` 표, 일/월/분기 기간), `build_macro_charts` — 국고채 10년·원/달러·기준금리·CPI·실업률·소비자심리지수 선 차트. 수집 실패(`DATA_UNAVAILABLE`/`[prefetch failed`)·관측 없음·관측 1개는 `ChartGap` 으로 사유 표시, 나머지 지표는 계속 그림.
  - `build_verdict_flow` / `verdict_flow_chart` — 감성 분석가 → 리서치 매니저 → 트레이더 → 포트폴리오 매니저. **구조화된 판정 줄**(`전체 센티먼트`/`추천`/`최종 거래 제안`/`등급`)만 읽고 본문에서 의견을 추정하지 않는다. 읽지 못한 단계는 "판독 불가"로 남기고 건너뛰지 않는다. 방향은 색과 기호(▲ ■ ▼)로 함께 표시. 영어 값의 이전 보고서도 읽음. 2단계 미만이면 만들지 않음.
  - `render_charts_html(items, heading)` — 제목 생략(`None`) 지원.
- `tradingagents/report_html.py` — 뉴스 분석가 텍스트 뒤에 "거시 지표 차트", 본문 맨 앞에 "한눈에 보기" 섹션(목차 포함), 판정 흐름 CSS.
- 테스트: `tests/test_charts.py`(ECOS 입력은 실제 `ecos.get_macro_data` 포매터 출력, 판정 입력은 실제 `render_*` 출력), `test_report_html.py`, `test_structured_agents.py` 보강.

## 설계 결정 변경 사항

없음. 이슈 2단계의 "가격 레벨(지지/저항·청산 계획)"은 구조화된 값이 상태에 없어(LLM 본문에만 있음) 이번 범위에서 제외 — 이슈의 "구조화된 값이 있을 때만" 원칙에 따름. 리스크 토론 3인(공격/보수/중립)도 구조화된 판정이 없어 흐름에 넣지 않았다.

## 검증 결과

- `pytest` 전체 통과 (1061), `ruff check .` 통과
- 실제 ECOS 데이터(국고채·환율·기준금리·소비자심리)와 실제 렌더러 출력으로 보고서를 만들어 헤드리스 Chrome 에서 렌더 확인(CPI 는 실패 사유 표시 경로 확인)
- 판정 방향 매핑에 변형을 넣어 테스트 3건이 실패하는 것을 확인 후 복원

## 다음 작업 핸드오프

- #144 남은 항목: 가격 레벨(지지/저항·청산 계획) — PM/트레이더의 구조화 값(`entry_price`/`stop_loss`/`price_target`)을 상태에 보존해야 함. 재무 차트(손익 폭포·현금 브리지) — DART 재무제표 구조화 선행.
- 색은 페이지 토큰(`--up` 초록 / `--down` 빨강) 그대로. 한국 증시 관례(상승=빨강)와 반대 — 결정 필요.
- 이미 생성된 보고서에는 `macro_data` 가 없어 거시 차트가 없고, 판정 흐름은 본문 판정 줄에서 읽으므로 이전 보고서 형식이면 일부만 나올 수 있다.
