# [#64] Task 7c: router + sentiment_analyst 를 네이버뉴스로 전환

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/64
- PR: (작업 완료 후 추가)
- 상위 에픽: #61
- 브랜치: `feat/64-naver-news-integration`
- 작업 기간: 2026-11-03 ~

## 범위

Task 7a (#62, PR #68) 에서 작성한 `vendors/naver_news.py` 를 라우팅/분석가에 연결.
Yahoo / Alpha Vantage 뉴스 분기를 네이버뉴스 단일로 축소하고 sentiment_analyst 가
reddit/stocktwits 대신 네이버뉴스 기반 감성 분석을 수행하도록 재구성.

**scope 밖 (다음 단계):**
- 거시 지표 (fred → ECOS): Task 7d (#65)
- prediction_markets 제거: Task 7e (#66)
- 레거시 vendor 파일 전면 삭제: Task 7f (#67)

## 수행한 변경

### `tradingagents/dataflows/router.py`

- `yahoo.news` / `alpha_vantage.news` import 전부 제거.
- `naver_news.get_news` / `naver_news.get_global_news` 신규 import.
- `VENDOR_METHODS["get_news"]`, `VENDOR_METHODS["get_global_news"]` 를 **네이버뉴스
  단일 vendor** 로 축소.

### `tradingagents/default_config.py`

- `data_vendors.news_data`: `"yfinance"` → `"naver_news"`.

### `tradingagents/agents/analysts/sentiment_analyst.py` 전면 재작성

- 상류 3 소스 (Yahoo news + StockTwits + Reddit) → **네이버 금융 뉴스 단일** 로 축소.
- `fetch_stocktwits_messages`, `fetch_reddit_posts`, `jev_screen`, `subreddits_for`,
  `CRYPTO_SUBREDDITS`, `DEFAULT_SUBREDDITS` import 전부 제거.
- 선조회는 `get_news.func(ticker, start_date, end_date)` 1 회만 — tool wrapper
  통한 네이버뉴스 호출.
- 시스템 프롬프트 재구성:
  - "News headlines — Yahoo Finance" → "News headlines — 네이버 금융, past 7 days"
  - StockTwits / Reddit 블록 삭제, 각각에 딸린 해석 가이드 삭제.
  - KRX 특화 지침 추가: 공시 (실적 발표, 유상증자, 전환사채) 영향, 관리종목/감자/
    상장폐지 리스크 신호.
  - "소셜 신호 부재" 가 아닌 "뉴스 단일 소스" 로 confidence 하향 가이드.
- 반환 shape (SentimentReport) 변경 없음 — 다운스트림 리서처/트레이더 노드가 그대로
  소비 가능.

### 테스트 수정

- `tests/test_graph_end_to_end.py`: `offline` fixture 에서 reddit/stocktwits
  fetcher mocking 제거 (소스가 없어졌으므로).
- `tests/test_dataflows_config.py`: `news_data` 디폴트 검증을 `"naver_news"` 로.
- `tests/test_structured_agents.py::TestSentimentAnalystAgent::_stub_prefetched_sources`:
  소셜 fetcher stubbing 제거.
- `tests/test_structured_agent_prompts.py::test_sentiment_prompt_states_constraint`: 동일.
- `tests/test_post_screen.py`:
  `test_the_sentiment_analyst_hands_the_screen_to_both_social_fetchers` 삭제 —
  sentiment_analyst 가 더 이상 jev_screen 을 사용하지 않음. jev_screen 함수 자체는
  유지 (다른 소비자 가능성).

## 설계 결정 변경 사항

### Sentiment 를 뉴스 전용으로 재편 (code_artifact.md 비명시)

code_artifact.md Task 7 은 "뉴스 분석가" 전환만 명시하고 sentiment_analyst 처리는
명시하지 않음. StockTwits/Reddit 는 미국 증시 소셜 플랫폼이라 KRX 종목 커버리지가
없음 (하드 포크 ADR-0001 이 KR-only 선언). 두 옵션:
1. sentiment_analyst 삭제 → news_analyst 로 통합
2. sentiment_analyst 유지, 뉴스 전용 재편

**옵션 2 선택** — SentimentReport (band / score / confidence / narrative) 는 리서처
토론 라운드가 anchoring 하는 중요 신호. 뉴스 톤 분류 + 테마 식별로도 유의미한 센티
먼트 도출 가능. 다운스트림 소비자 (research_manager, trader) 변경 없음.

향후 Task (0 이후) 로 "네이버 금융 종목 토론방" 또는 KRX 커뮤니티 (팍스넷,
딱쿵 등) 소셜 신호 추가 가능.

### news_analyst 는 이번 PR 에서 변경 없음

news_analyst 는 `get_news` / `get_global_news` 를 호출 — 라우팅 전환만으로 자동
으로 네이버뉴스를 받음 (vendor shape 동일). 거시 지표 (fred → ECOS) 와 prediction
markets 제거는 Task 7d / 7e 로 분리.

### 레거시 vendor 파일 유지 (Task 7f 까지)

`vendors/yahoo/news.py`, `vendors/alpha_vantage/news.py`, `vendors/reddit.py`,
`vendors/stocktwits.py` 는 아직 **디스크에 남아있음**. 라우팅 참조는 끊겼지만
Task 7f (#67) 가 파일 삭제 담당. 이 PR 머지 후 import 실패 테스트가 하나도 없음을
확인했으므로 dead code 상태.

## 검증 결과

- `pytest -q` 전체 → **922 passed, 8 subtests passed**
- `ruff check tradingagents cli tests` → **All checks passed**

## 다음 작업 핸드오프

### Task 7d (#65): router + macro 범주를 ECOS 로
- `router.VENDOR_METHODS["get_macro_indicators"]` → `{"ecos": ecos.get_macro_data}` 단일
- `tools.py::get_macro_indicators` docstring 을 ECOS alias (base_rate, cpi, usd_krw, ...) 로
- `news_analyst._MACRO_INDICATORS` 를 ECOS alias 로
- `default_config.macro_data` → `"ecos"`

### Task 7e (#66): prediction_markets + polymarket 완전 제거
- `router.TOOLS_CATEGORIES["prediction_markets"]` 삭제
- `router.VENDOR_METHODS["get_prediction_markets"]` 삭제
- `tools.py::get_prediction_markets` @tool 삭제
- `news_analyst._PREDICTION_TOPICS` 삭제, 선조회 호출 삭제, 프롬프트 섹션 삭제
- `default_config.prediction_markets` 삭제

### Task 7f (#67): 레거시 vendor + 테스트 + crypto_base 전면 삭제
- 디렉터리 `vendors/yahoo/`, `vendors/alpha_vantage/` 전체 삭제
- 파일 `vendors/reddit.py`, `vendors/stocktwits.py`, `vendors/fred.py`,
  `vendors/polymarket.py` 삭제
- `symbols.py::crypto_base` 스텁 함수 삭제
- 관련 테스트 삭제 (`test_social_lookahead.py`, `test_naver_news_vendor.py` 외의
  reddit/stocktwits/fred/polymarket 테스트)

