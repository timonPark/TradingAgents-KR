# [#196] default_config 의 get_global_news 주석이 #189 이후 사실과 다름

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/196
- PR: (생성 후 기입)
- 브랜치: chore/196-global-news-comment
- 작업 기간: 2026-11-27

## 수행한 변경

- `tradingagents/default_config.py` 주석 1줄 수정
  - 전: `주요뉴스(get_global_news)는 naver_news 만 지원 (현재 엔드포인트 폐지).`
  - 후: `주요뉴스(get_global_news)는 naver_news 만 지원 (네이버 증권 JSON API, #189).`
- "naver_news 만 지원" 은 여전히 사실이라 유지 (`naver_api_hub` 에는 `get_global_news` 가 없음).
  #189 (PR #192) 로 `m.stock.naver.com/api/news/list?category=mainnews` 로 복구돼
  "엔드포인트 폐지" 부분만 틀렸다.

## 설계 결정 변경 사항

없음. 동작 변경 없는 주석 정리.

## 검증 결과

- `ruff check tradingagents cli tests` — 통과
- 위험도: 주석만 변경이라 파급 범위·변경 주기·민감도 해당 없음 → `risk:low`

## 다음 작업 핸드오프

- #194 (종목뉴스 502 쪽 단위 재시도 / 부분 결과) → #198 (빈 쪽 처리) 순으로 진행 예정.
