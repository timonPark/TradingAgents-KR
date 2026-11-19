# [#188] 과거 기준일에 고유동성 종목 뉴스가 0건 — 조회 한도 도달과 무보도 구분

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/188
- PR: https://github.com/timonPark/TradingAgents-KR/pull/193
- 브랜치: fix/188-naver-news-window
- 작업 기간: 2026-11-19

## 수행한 변경

- `tradingagents/dataflows/vendors/naver_api_hub.py`
  - 최신 N건(5쪽×100) 안에서 기간 시작까지 못 읽으면 일부만 돌려주지 않고 `VendorUnavailableError`
    ("조회 한도"). 라우터가 더 깊게 읽는 다음 vendor(`naver_news`)로 넘긴다.
- `tradingagents/dataflows/vendors/naver_news.py` (`get_news`, 종목뉴스)
  - 읽는 양을 20건×5쪽(100건) → 20건×100쪽(서버 상한 2000건)으로 확대.
  - 한도에 걸려 기간 시작까지 못 갔을 때:
    - 기간 끝에도 못 닿음 → `VendorUnavailableError` (라우터가 `DATA_UNAVAILABLE` 로 보고)
    - 기간 일부만 닿음 → 조회된 기사 + "조회 한도로 YYYY-MM-DD 이후 기사만 조회됨 … 기사 없음으로
      해석하지 마세요" 경고를 헤더 아래에 표시 (`_format_news_markdown(note=)` 추가)
  - 소스를 끝까지 읽은 경우(짧은 쪽·빈 쪽)만 정상적인 "뉴스 없음".
  - 반환 30건 상한(`_STOCK_NEWS_MAX_ITEMS`, API HUB 와 동일)을 두고, 채우면 더 읽지 않는다.
    (읽는 양을 늘리면서 프롬프트가 수천 건으로 커지는 것을 막기 위함)
- 테스트: `tests/test_naver_news_vendor.py`, `tests/test_naver_api_hub_vendor.py`
  - 한도 초과 실패 / 일부 커버리지 경고 / 짧은 쪽=뉴스 없음 / 30건 조기 종료 / pageSize 고정 /
    라우터 폴백 테스트 추가 (예전 코드에서는 5건 실패, 새 코드에서 통과).
  - 실제 API 통합 테스트(`test_live_api_hub_returns_matched_articles`)를 삼성전자 → 금호전기(001210)로 변경.
    삼성전자 14일치는 설계상 API HUB 한도를 넘어 실패하는 요청이다.

## 조사로 확인한 외부 API 사실

- API HUB 검색: `start` 최대 1000, `display` 최대 100, 날짜 필터 없음 (`startDate`/`endDate`/`pd` 는 무시).
  삼성전자 1000건 ≈ 약 하루치.
- 네이버 증권 종목뉴스 JSON: 날짜 파라미터 없음, 총 2000건 상한. `pageSize=20` 은 100쪽까지 끊김 없이
  이어지고 101쪽에서 HTTP 400. `pageSize=50` 은 쪽 사이에 빈 구간(7~10쪽)과 중복이 생겨 쓸 수 없고,
  `100` 은 비-JSON 응답. 쪽 사이 일부 중복은 기존 제목 중복 제거로 걸러진다.
- 삼성전자 2000건 ≈ 4.4일치(2026-11-15 08:35 까지). 100회 호출 ≈ 8초.

## 설계 결정 변경 사항

없음. (`code_artifact.md` 계획 변경 없음.) 이슈 제안 중 "기간을 좁히는 수단 확인" 은 두 API 모두
날짜 필터가 없음을 확인했고, "한도 도달과 무보도 구분" 으로 해결했다.

## 검증 결과

- `pytest tests/test_naver_news_vendor.py tests/test_naver_api_hub_vendor.py` — 58 passed
- `pytest -m integration` (두 파일, 실제 API) — 3 passed
- `pytest` 전체 — 1290 passed, `ruff check tradingagents cli tests` — 통과
- 실제 라우터 호출(삼성전자, 7일 창, 기준일 오늘로부터 N일 전):
  - 0·1·3일 전: 기준일 부근 기사 30건
  - 5·7일 전: `DATA_UNAVAILABLE` + 사유 ("조회 한도(최신 2000건, 가장 오래된 기사 2026-11-15 08:35) …")
- 웹 UI (Aside 브라우저, 삼성전자, 뉴스 분석가만, effort `low`):
  - 기준일 2026-11-16: "종목 뉴스 분석" 에 2026-11-16 기사(3분기 누적 매출 500조원, 외국인 순매도,
    하이닉스 7.89% 하락 등)가 반영됨. (수정 전 화면은 직접 보지 않음 — 이슈 #188 은 같은 유형의
    과거 기준일에서 0건이었다고 보고. 2026-10-01 기준 실행에서는 수정 전 "기업 뉴스: 없음" 을 확인했다.)
  - 기준일 2026-11-12: 리포트 맨 앞 "데이터 공백" 에 "네이버 증권 뉴스 조회 한도 안에서
    2026-11-05~11-12 기간에 닿지 못했습니다" 가 명시되고 종목 뉴스는 평가하지 않음.
  - 백엔드 로그: API HUB 한도 초과 → `trying next vendor` → `naver_news` 성공/실패 경로 확인.
  - 검증 후 쿼터 절약을 위해 두 실행 모두 취소.

## 다음 작업 핸드오프

- 기사량이 많은 종목은 반환 30건이 기준일 당일 최근 몇 시간치뿐이다 (예: 삼성전자 11-16 기준 → 11-16 18:29~23:36).
  기간 전체를 고르게 대표하지 못하는 한계는 이번 범위 밖 — 새 이슈 후보.
- `tradingagents/default_config.py:136` 주석 "주요뉴스(get_global_news)는 naver_news 만 지원 (현재 엔드포인트 폐지)"
  는 #189 로 해소돼 사실과 다르다. 이번 이슈와 무관해 손대지 않았다 — 별도 정리 필요.
- 종목뉴스 0건 vs 수집 한도 구분은 이제 vendor 응답에 있지만, 웹 UI 가 "조회 한도" 경고를
  별도로 강조하지는 않는다 (리포트 본문에 분석가가 서술하는 방식).
