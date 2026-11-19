# [#189] 글로벌 뉴스 조회 실패 — 네이버 주요뉴스 엔드포인트 이전 대응

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/189
- PR: https://github.com/timonPark/TradingAgents-KR/pull/192
- 브랜치: fix/189-naver-global-news
- 작업 기간: 2026-11-19

## 수행한 변경

- `tradingagents/dataflows/vendors/naver_news.py`
  - `get_global_news` 를 폐지된 `finance.naver.com/news/mainnews.naver` (HTML 크롤) 에서
    `https://m.stock.naver.com/api/news/list?category=mainnews` (JSON) 로 교체.
  - 새 API 는 `date` 등 날짜 파라미터를 **무시**하고 항상 최신순이라, 최신순으로 페이지를 넘기며
    기준일 창(`as_of - (look_back-1)일 00:00` ~ `as_of 24:00`)에 들어오는 기사만 수집.
    기준일보다 새로운 기사는 건너뛰고, 창 시작보다 오래된 기사가 나오면 멈춘다.
  - 조회 한도(`_MAIN_NEWS_MAX_PAGES=60`, 약 1주일치) 안에서 기준일에 닿지 못하면
    "주요뉴스 없음" 이 아니라 `VendorUnavailableError` (한도 초과 사유 명시).
  - JSON 오류 처리를 `_get_json_list` 로 추출해 `_fetch_stock_news_json` 과 공유 (동작·메시지 동일).
  - 이 변경으로 안 쓰이게 된 `_fetch_html`, `_parse_main_news`, `_parse_naver_date`, `_BASE`,
    `bs4`/`urllib.parse`/`re` import 제거.
- `tests/test_naver_news_vendor.py`
  - 주요뉴스 테스트를 JSON 구조 기준으로 교체 (창 필터, 페이지 넘김, 한도 초과, 노이즈·중복, 오류 경로).
  - 삭제된 `_parse_naver_date` 테스트 제거.
  - 실제 API 통합 테스트(`-m integration`) 1건 추가.

## 설계 결정 변경 사항

없음. (`code_artifact.md` 계획 변경 없음. 이슈 제안 중 "대체 불가 시 화면 노출" 은 대체 엔드포인트를
찾았으므로 해당 없음.)

## 검증 결과

- `pytest tests/test_naver_news_vendor.py` — 29 passed
- `pytest tests/test_naver_news_vendor.py -m integration` — 2 passed (실제 네이버 API)
- `pytest` 전체 — 1282 passed
- `ruff check tradingagents cli tests` — 통과
- 수동 확인: `route_to_vendor("get_global_news", "2026-11-19", 1, 3)` 가 실제 기사 3건 반환,
  과거 기준일(2026-11-16) 도 기사 반환, 2026-10-01 은 한도 초과 오류.
- 웹 UI 화면 검증은 수행하지 않음 (vendor 계층 변경, UI 변경 없음).

## 다음 작업 핸드오프

- 과거 기준일 + 고유동성 종목 문제는 #188 에서 별도 처리 (종목 뉴스는 이 PR 범위 밖).
- 발견 사항(범위 밖): `bs4` 는 이 파일에서 더 이상 쓰이지 않는다. 다른 모듈의 사용 여부 확인 후
  `pyproject.toml` 의존성 정리 여부는 별도 판단.
