# [#145] 보고서·UI 의 영어 등급·라벨 한국어 표기

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/145
- PR: (작성 후 기입)
- 브랜치: feat/145-korean-rating-display
- 작업 기간: 2026-11-05 ~ 2026-11-05

## 문제

보고서 제목 배지가 `Underweight`, 본문에 `Underweight`·`SELL` 반복, 센티먼트 머리글이 `Overall Sentiment: Mixed` / `Confidence: Medium` 등 사용자 노출 텍스트에 영어가 남아 있었다. ADR-0003 이 "파서·백테스트 호환" 을 이유로 값을 영어로 유지했기 때문.

## 수행한 변경

- `tradingagents/agents/rating.py` — `RATING_KO`, `display_rating()`, `canonical_rating()` 추가. 파서(`extract_rating`)가 한국어 값(`비중 확대`/`비중 축소` 두 단어 포함)을 영어 값과 같은 등급으로 읽음. **내부 값은 영어 그대로**.
- `tradingagents/agents/schemas.py` — 한국어 모드에서 추천/액션/등급/최종 거래 제안 값을 한국어로 렌더. 센티먼트 머리글을 `**전체 센티먼트:** **혼조** (점수: 5.2/10)` / `**신뢰도:** 중간` 으로 (`SENTIMENT_BAND_KO`, `CONFIDENCE_KO`). 영어 모드는 기존대로.
- `tradingagents/reporting.py`, `tradingagents/report_html.py` — 헤더 `- 등급:` 과 제목 배지·페이지 타이틀을 한국어로.
- `api/reports_store.py`, `api/routes/reports.py` — 헤더의 등급을 한국어/영어 모두 읽어 영어 값(`decision`)을 반환 → 이전 보고서도 동작.
- `web/src/utils/rating.ts` 신규 + `ReportViewer.tsx`/`RunPanel.tsx` — 결정 표시 한국어화.
- 프롬프트(`context.py`, `research_manager.py`, `portfolio_manager.py`, `trader.py`, `sentiment_analyst.py`) — 본문 서술은 한국어 표기, 구조화 필드(enum) 값은 영어 유지.
- `docs/adr/0004-korean-rating-display-values.md` 신규, `CLAUDE.md` §4.1·`GLOSSARY.md` 갱신.
- 테스트: 파서(한국어 값·두 단어·영어 호환), 렌더(한국어/영어 모드), 한국어 렌더 라인의 파서 왕복, API 헤더 호환, 프롬프트 지침.

## 설계 결정 변경 사항

ADR-0003 의 "결정 라인 값은 영어" 를 ADR-0004 로 대체. 근거: 한국어→내부 값 변환을 파서 한 곳에서 흡수하면 다운스트림(백테스트·메모리 로그·`final_rating`·API) 변경이 필요 없다. `code_artifact.md` Task 9 의 결정 라인 포맷 설명(`값은 영어 유지`)은 머지 시점에 반영.

## 검증 결과

- `pytest` 전체 통과, `ruff check tradingagents cli tests api` 통과
- `cd web && npm run build` 통과
- 새 run 의 보고서 확인은 PR 머지 전 수동 확인 필요 (아래 핸드오프)

## 다음 작업 핸드오프

- 이미 생성된 보고서(영어 배지)는 재생성하지 않음. 새 분석부터 한국어.
- 본문 서술의 한국어 표기는 프롬프트 지침에 의존하므로 LLM 이 가끔 영어를 쓸 수 있다 — 실제 run 에서 잔존 여부 확인.
- #144 (차트) 의 판정 흐름 차트는 `display_rating()` 을 써야 한다.
