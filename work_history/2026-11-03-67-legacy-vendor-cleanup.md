# [#67] Task 7f: 레거시 vendor + 테스트 + crypto_base 전면 삭제

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/67
- PR: (작업 완료 후 추가)
- 상위 에픽: #61
- 브랜치: `feat/67-legacy-vendor-cleanup`
- 작업 기간: 2026-11-03 ~

## 범위

Task 7a-e 로 모든 라우팅/도구/분석가 참조가 끊긴 레거시 vendor 파일과 테스트를
전면 삭제. Task 7 에픽 (#61) 종결 단계.

## 사전 확인

모든 삭제 대상이 **dead code** 상태 — grep 결과 외부 참조는 삭제 대상 파일 내부
간 참조만 남음 (reddit/stocktwits 가 symbols.crypto_base 를 import, yahoo/news 가
yahoo/common 을 import 등). 외부 코드가 참조하지 않으므로 안전 삭제.

## 수행한 변경

### 레거시 vendor 파일 전면 삭제

**단일 파일:**
- `tradingagents/dataflows/vendors/fred.py`
- `tradingagents/dataflows/vendors/polymarket.py`
- `tradingagents/dataflows/vendors/reddit.py`
- `tradingagents/dataflows/vendors/stocktwits.py`

**디렉터리:**
- `tradingagents/dataflows/vendors/yahoo/` 전체 (news.py, common.py, __init__.py)
- `tradingagents/dataflows/vendors/alpha_vantage/` 전체 (news.py, common.py, __init__.py)

Task 6e (#56) 에서 유예됐던 뉴스 서브모듈과 공통 유틸이 이번 PR 에서 완전 소멸.

### `tradingagents/dataflows/symbols.py`

- `crypto_base` 스텁 함수 삭제 — 유일 소비자였던 reddit.py / stocktwits.py 가
  삭제됨.
- 모듈 docstring 업데이트: 공개 함수 섹션에서 `crypto_base` 제거, 삭제 로직 목록
  에 추가.

### 레거시 테스트 전면 삭제

- `tests/test_fred.py`
- `tests/test_news_lookahead.py` (yahoo news lookahead)
- `tests/test_social_lookahead.py` (reddit + stocktwits)
- `tests/test_vendor_errors.py` (alpha_vantage.common 전용)

약 84개 테스트가 제거됐지만, 삭제된 vendor 들의 커버리지라 모두 손실 없음 (대체
vendor 들의 커버리지는 Task 7a/7b/Task 5/6 에서 이미 작성됨).

## 설계 결정 변경 사항

### 외부 참조 사전 확인

삭제 전 `grep` 으로 `from tradingagents.dataflows.vendors.{reddit, stocktwits, fred,
polymarket, yahoo, alpha_vantage}` 또는 `crypto_base` 를 import 하는 외부 코드가
있는지 확인. 모든 결과가 **삭제 대상 파일 간 내부 참조** 뿐이었음 (reddit.py 가
crypto_base 를 import 하는 식). 외부 참조 0 → 안전 삭제.

### 테스트 삭제 범위

code_artifact.md Task 7 Definition of Done 은 "Reddit/StockTwits/FRED/Polymarket
완전 삭제" 명시. 각 vendor 전용 테스트도 동반 삭제. 테스트가 커버하던 behavior
는:
- `test_fred.py` → vendors/fred.py 가 삭제됐으므로 behavior 자체가 없음
- `test_news_lookahead.py` → yahoo.news 가 삭제됐으므로 behavior 자체가 없음
- `test_social_lookahead.py` → reddit/stocktwits 가 삭제됐으므로 behavior 자체가 없음
- `test_vendor_errors.py` → alpha_vantage.common 가 삭제됐으므로 behavior 자체가 없음

대체 vendor 들 (naver_news, ecos, pykrx, dart) 은 각각 자체 테스트 세트 보유.

## 검증 결과

- `pytest -q` 전체 → **829 passed** (삭제된 84개 테스트 반영)
- `ruff check tradingagents cli tests` → **All checks passed**

### 삭제 통계
- 삭제된 vendor 파일: 4개 (fred/polymarket/reddit/stocktwits) + 2개 디렉터리 (yahoo + alpha_vantage, 각 3-4개 파일)
- 삭제된 심볼 유틸: `symbols.crypto_base`
- 삭제된 테스트 파일: 4개 (약 84개 테스트)

## Task 7 에픽 (#61) 종결

이 PR 머지 후 모든 하위 이슈 close 가능:
- #62 (7a) ✅ 머지 (PR #68) — 네이버뉴스 vendor 신규
- #63 (7b) ✅ 머지 (PR #69) — ECOS vendor 신규
- #64 (7c) ✅ 머지 (PR #70) — router + sentiment_analyst 를 네이버뉴스로
- #65 (7d) ✅ 머지 (PR #71) — router + news_analyst 를 ECOS 로
- #66 (7e) ✅ 머지 (PR #72) — prediction_markets 범주 + 도구 제거
- #67 (7f) 🟡 **이 PR** — 레거시 vendor + crypto_base 전면 삭제

## 다음 작업 (Task 8 이후)

- **Task 8**: KRX 거래소 캘린더 매핑. `date_window.py` 가 KRX 영업일 기준으로 동작.
- **Task 9**: 한국어 시스템 프롬프트 (분석가/리서처/트레이더 프롬프트 한국어화 + KRX 특유 리스크 지침).
- **Task 11**: 테스트 재작성 (통합 테스트 분산 — 실제 API 호출 테스트는 opt-in).
- **Task 12**: Docker Claude Code 통합.

