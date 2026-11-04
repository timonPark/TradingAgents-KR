# [#137] ECOS vendor get_scrubbed params 누락 수정

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/137
- PR: (생성 후 기입)
- 브랜치: fix/137-ecos-get-scrubbed-params
- 작업 기간: 2026-11-04 ~ 2026-11-04

## 문제

웹 UI 실행(run `de9ddc825516`, 211270, 2026-11-04)의 뉴스 분석 리포트에서 ECOS 거시 지표 6개가 전부 "조회 실패"로 표시됨.

원인: `tradingagents/dataflows/vendors/ecos.py` 의 `_fetch()` 가 `get_scrubbed(url, timeout=..., secret=...)` 로 호출 — `net.get_scrubbed` 의 필수 keyword-only 인자 `params` 누락으로 모든 호출이 네트워크 도달 전에 `TypeError` 발생. Task 7b (#69) 작성 당시부터 존재.

테스트가 못 잡은 이유: `tests/test_ecos_vendor.py` 가 `get_scrubbed` 를 통째로 모킹해 시그니처 불일치가 드러나지 않음.

### 추가 발견: 일별 시계열 최근값 누락

params 수정 후 재생성한 리포트에서 기준금리가 2026-01-22, 국고채 10년·환율이 2026-03-03 에서 멈춰 "약 8개월 지연" 으로 보고됨. 원인: `_fetch()` 가 요청 행 범위를 `1 ~ MAX_ROWS*2(=80)` 로 고정. ECOS 는 구간의 **오래된 쪽부터** 행을 주므로 1년치 일별 시계열에서 처음 80행만 받고 최근 데이터는 잘림. 월별(12행)·분기별은 영향 없음.

## 수행한 변경

- `tradingagents/dataflows/vendors/ecos.py` — `get_scrubbed(..., params={}, ...)` 로 수정 (ECOS 는 키·조회조건을 URL 경로에 넣으므로 쿼리 파라미터 없음)
- `tradingagents/dataflows/vendors/ecos.py` — 요청 행 수를 `FETCH_ROW_LIMIT = 10000` 으로 분리. 구간 전체를 받고 표시 단계에서 최근 `MAX_ROWS` 만 남김
- `tests/test_ecos_vendor.py` — `test_fetch_calls_real_get_scrubbed_signature` 추가. `requests.get` 만 모킹하고 실제 `get_scrubbed` 를 거쳐 시그니처 회귀를 잡음
- `tests/test_ecos_vendor.py` — `test_fetch_requests_whole_window_for_daily_series` 추가. 요청 URL 의 종료 행 번호가 1년치 일별 행 수 이상인지 확인

## 설계 결정 변경 사항

없음.

## 검증 결과

- `pytest tests/test_ecos_vendor.py` — 34 passed (params 신규 테스트는 수정 전 코드에서 FAILED 확인)
- `pytest tests/test_ecos_vendor.py -m integration` — 실제 ECOS API 3건 passed (기준금리·CPI·원/달러)
- `ruff check tradingagents cli tests` — 통과
- 실제 호출 최근값 (2026-11-04 기준): 기준금리 3.00% (20261102), 국고채 10년 3.968 (20261104), 원/달러 1,341.20 (20261104), CPI 120.73 (202610)
- run `de9ddc825516` 의 News Analyst 리포트만 재생성해 `~/.tradingagents/logs/reports/211270_20261104_223628/` 에 반영 (다른 리포트·최종 결정은 원본 유지)

## 다음 작업 핸드오프

- 실행 중인 uvicorn 서버는 수정 전 코드로 떠 있으므로 재시작해야 이후 실행에 반영됨.
- 별도 이슈 후보: pykrx 가 import 시 자동 로그인 + 실패 재시도 → 비밀번호 오류 시 KRX 계정 잠금(CD007) 유발.
- 별도 이슈 후보: Naver 금융 뉴스 엔드포인트 폐지. `item/news_news.naver` 는 HTTP 410 ("이 페이지는 더 이상 제공되지 않습니다"), `news/mainnews.naver` 는 `stock.naver.com/news/mainnews` 로 리다이렉트 → 종목·주요 뉴스 0건. `vendors/naver_news.py` 재작성 필요.
