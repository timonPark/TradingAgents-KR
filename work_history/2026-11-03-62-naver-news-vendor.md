# [#62] Task 7a: vendors/naver_news.py 신규 작성 + 유닛 테스트

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/62
- PR: (작업 완료 후 추가)
- 상위 에픽: #61
- 브랜치: `feat/62-naver-news-vendor`
- 작업 기간: 2026-11-03 ~

## 범위

네이버 금융 HTML 뉴스 페이지를 KRX 종목 뉴스 소스로 사용. 상류 Yahoo/Alpha
Vantage news vendor 와 shape 호환하여 Task 7c (router/analyst 전환) 가 거의
수정 없이 drop-in 할 수 있도록 설계.

Task 7a 는 vendor 모듈 신규 작성만 담당. router 연결은 Task 7c.

## 접근 방식 결정

**네이버 금융 HTML 크롤러** 선택 (사용자 확인). API 키 불필요, KRX 특화 뉴스
직접 접근. BS4 로 파싱.

대안으로 네이버 검색 Open API 와 RSS 를 고려했으나:
- Open API: 금융 뉴스 전용 분류가 없어 노이즈 다수
- RSS: 종목별 필터링을 클라이언트에서 다시 해야 함

## 수행한 변경

### `pyproject.toml`

- `beautifulsoup4>=4.12` 명시 의존성 추가. yfinance 등의 transitive 로 이미 설치
  되어 있지만 vendors/naver_news.py 가 직접 import 하므로 선언.

### `tradingagents/dataflows/vendors/naver_news.py` 신규

**공개 함수:**
- `get_news(ticker, start_date, end_date)` → str — 상류 `yahoo.news.get_news` /
  `alpha_vantage.news.get_news` 호환. ``finance.naver.com/item/news_news.naver`` 를
  최대 5페이지 (약 100건) 순회, 날짜 범위 필터 + 노이즈 필터 적용.
- `get_global_news(as_of_date, look_back_days, limit)` → str — 상류
  `yahoo.news.get_global_news` / `alpha_vantage.news.get_global_news` 호환.
  ``finance.naver.com/news/mainnews.naver`` 를 날짜 × 페이지 순회, 중복 제목 제거.

**모듈 수준 헬퍼:**
- `_fetch_html(url)` — requests.get + 공통 에러 처리 + 인코딩 자동 복구 (euc-kr/
  utf-8 혼재 대응).
- `_parse_naver_date(text)` — 네이버 금융 날짜 포맷 (``YYYY.MM.DD HH:MM``,
  ``YYYY-MM-DD HH:MM``, ``MM/DD`` 축약) 수용.
- `_is_noise(title)` — ``[부고]/[인사]/[동정]/[포토]/[사진]/증시요약`` 등 노이즈
  필터.
- `_parse_item_news_table(html)` — 종목 뉴스 테이블 (``table.type5 tbody tr``)
  파싱.
- `_parse_main_news(html)` — 주요뉴스 (`ul.newsList li`, `dl.newsList dt`) 파싱.
- `_format_news_markdown(...)` — 분석가 프롬프트용 Markdown 포맷.

**반환 형식:**
```markdown
## 005930 뉴스 (2026-11-02 ~ 2026-11-03)

- **2026-11-03 14:30** | 머니투데이 | 삼성전자 4분기 실적 호조
  - https://finance.naver.com/item/news_read.naver?article_id=001
```

### `tests/test_naver_news_vendor.py` 신규

**21개 테스트**, 전부 `requests.get` 을 `patch` 로 모킹:
- 날짜 범위 필터링 (범위 밖 뉴스 제외)
- 노이즈 필터링 (`[포토]`, `[부고]` 등 제외)
- Markdown 헤더 렌더링
- 잘못된 날짜 형식 처리
- 빈 HTML / HTTP 500 / 네트워크 예외 → 사람 읽기 쉬운 안내 (분석가 run 중단 방지)
- `_parse_naver_date` 포맷 매트릭스 (parametrize)
- 주요뉴스: limit 준수, 중복 제거, 빈 HTML, 잘못된 날짜 처리

## 설계 결정 변경 사항

### 네이버 금융 HTML 크롤러 선택

사용자 확인. 대안 (Open 검색 API, RSS) 과 비교:
- Open API: 금융 뉴스 전용 분류 없음 → 노이즈 다수, Client ID/Secret 발급 필요
- RSS: 종목별 필터링을 클라이언트에서 다시 해야 함 (중복 크롤링)
- HTML 직접 파싱: API 키 불필요, KRX 종목·주요뉴스 범주 활용, 네이버 금융
  페이지 변경 시 셀렉터 조정 필요 (유지보수 비용 미미)

### 노이즈 필터 범위

code_artifact.md 는 "광고성 기사 제거 + 주요 이슈 5건 요약" 명시. 광고성 패턴 외에
``[포토]/[사진]/[부고]/[인사]/[동정]`` 등 투자 판단과 무관한 범주형 기사도 제외.
"증시요약" 묶음 기사는 특정 종목 분석 시 노이즈라 제거. 요약 개수 (5건) 는 Task 7c
(news_analyst 전환) 에서 분석가 쪽에서 결정 — vendor 는 범위 내 전부 반환.

### User-Agent 지정

네이버 금융은 UA 가 없으면 간혹 403 반환. 일반 Chrome UA 로 헤더 지정. 봇 감지가
강화되면 Task 11 통합 테스트가 먼저 실패하도록 설계.

### 날짜 범위 필터링 로직

종목 뉴스는 최신 순으로 반환되므로 가장 오래된 아이템이 `start_date` 보다 이전이면
조기 종료 (불필요한 페이지 조회 방지). 날짜 파싱 실패한 아이템은 보존 — 분석가가
직접 판단할 수 있도록.

## 검증 결과

- `pytest tests/test_naver_news_vendor.py -v` → **21 passed**
- `pytest -q` 전체 → **891 passed, 8 subtests passed**
- `ruff check tradingagents cli tests` → **All checks passed**

실제 네이버 금융 호출 통합 테스트는 Task 11 로 분산.

## 다음 작업 핸드오프

### Task 7c (#64): router + news_analyst + sentiment_analyst 전환
- `router.py`: `get_news` / `get_global_news` 분기를 `naver_news` 단일로
- `news_analyst.py` 사전조회는 상류와 동일 인터페이스라 vendor 교체만으로 작동
- `sentiment_analyst.py` 는 reddit/stocktwits 를 네이버 금융 종목 토론방 또는
  네이버뉴스 감성 분석으로 교체 — 네이버 금융에 종목별 토론방 URL 패턴 있음
- `default_config.news_data` → `"naver_news"`

