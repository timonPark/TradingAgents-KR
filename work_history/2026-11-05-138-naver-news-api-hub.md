# [#138] 네이버 뉴스 엔드포인트 폐지 대응 (NAVER API HUB + 네이버 증권 JSON)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/138
- PR: https://github.com/timonPark/TradingAgents-KR/pull/141
- 브랜치: fix/138-naver-news-api-hub
- 작업 기간: 2026-11-05 ~ 2026-11-05

## 문제

2026-11-04 보고서(001210, 211270)에서 종목 뉴스·주요뉴스가 항상 0건이었고, 감성·뉴스 분석가가 이를 "실제로 보도가 없었다"고 해석함. 실제로는 `finance.naver.com/item/news_news.naver` 가 HTTP 410 (폐지), `news/mainnews.naver` 가 `stock.naver.com` 으로 리다이렉트되는데, vendor 가 실패를 삼키고 "해당 기간 뉴스가 없습니다" 를 반환한 것이 근본 원인.

같은 구간에 기사가 존재했음을 확인:
- 001210: 10/28 서울경제 "오늘의 메모" (국내CB 보통주추가상장)
- 211270: 11/03 "KPS 위성 시험장비 납품에 상한가" 등 다수 — 보고서의 "재료 없는 급등" 전제와 상반

## 수행한 변경

- `tradingagents/dataflows/vendors/naver_api_hub.py` 신규 — NAVER API HUB 뉴스 검색. 회사명 따옴표 쿼리·최신순, 제목에 회사명 또는 제목/요약에 종목코드가 있는 기사만 유지 (본문에 회사명이 스치는 무관 기사 제거), `<b>` 제거·엔티티 복원·중복 제거·상한 30건. 키 없음/인증 실패는 `VendorNotConfiguredError`, 한도 초과·서버/네트워크 오류는 `VendorUnavailableError`
- `tradingagents/dataflows/vendors/naver_news.py` — 종목 뉴스를 네이버 증권 JSON (`m.stock.naver.com/api/news/stock/{ticker}`) 으로 교체. `_fetch_html` 은 실패·리다이렉트 시 `VendorUnavailableError` (주요뉴스도 "없음" 위장 중단). 죽은 HTML 종목 뉴스 파서 제거
- `tradingagents/dataflows/router.py`, `tradingagents/default_config.py` — `get_news` 체인 `naver_api_hub,naver_news`
- `tradingagents/agents/analysts/sentiment_analyst.py` — 프롬프트에 `DATA_UNAVAILABLE` 는 수집 실패임을 명시
- `tests/test_naver_api_hub_vendor.py` 신규, `tests/test_naver_news_vendor.py` 개편, `tests/test_dataflows_config.py` 기본값 갱신
- `README.md` — 환경변수·키 발급·통합 테스트 표, `code_artifact.md` — Task 7 본문 갱신

## 설계 결정 변경 사항

`code_artifact.md` Task 7 의 "네이버 금융 헤드라인 크롤러" 에서 변경:
- 종목 뉴스 소스: HTML 크롤 → NAVER API HUB(1순위) + 네이버 증권 JSON(폴백). 이유: 기존 엔드포인트 폐지(410), 네이버 검색 오픈 API 는 2026-07-31 부터 개발자센터 신규 신청 차단(API HUB 이관).
- 실패 의미론: "0건" 과 "실패" 분리. 라우터의 `DATA_UNAVAILABLE` 체계 재사용.
- 주요뉴스는 이번 범위 제외 (대체 엔드포인트 미확인).

## 검증 결과

- `pytest` 전체 — 965 passed (신규 API HUB 테스트 포함)
- `pytest -m integration` (naver 두 파일) — 실호출 2건 passed
- `ruff check tradingagents cli tests` — 통과
- 라우터 실호출: 001210 → 6건 (10/28 "오늘의 메모[10월 29일]" 포함), 211270 → 16건 (11/03 KPS 장비 납품·상한가 기사 포함)

## 다음 작업 핸드오프

- NAVER API 이용약관 2026-09-07 개정: 개발자센터 공지 요약상 검색 API 결과의 AI 입력·저장 제한 조항이 있음. **원문 미확인.** 사용자 판단으로 진행. 적용 여부는 원문 확인 후 재검토.
- 비공식 증권 JSON 은 경로 변경 위험 — 실패를 0건으로 삼키지 않도록 처리해 둠.
- 주요뉴스 복구 이슈 (대체 엔드포인트 조사) — 별도 이슈 필요.
- DART 공시를 뉴스 분석가 사전조회에 연결 (대량보유·임원지분·CB 이벤트 캘린더) — 별도 이슈 필요.
- 서버(uvicorn) 재시작 및 `.env` 의 `NAVER_API_HUB_CLIENT_ID/SECRET` 필요.
- #139 pykrx 자동 로그인 이슈 — 종목명 조회(`krx_symbol_search`)는 FDR 기반이라 영향 없음.
