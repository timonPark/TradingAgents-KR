# [#157] 종목 검색에서 코스닥 우량기업부(KOSDAQ GLOBAL) 50개 종목 누락

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/157
- PR: https://github.com/timonPark/TradingAgents-KR/pull/158
- 브랜치: fix/157-kosdaq-global-search
- 작업 기간: 2026-11-05

## 수행한 변경

- `tradingagents/dataflows/krx_symbol_search.py`
  - `_MARKET_ALIASES = {"KOSDAQ GLOBAL": "KOSDAQ"}` — FDR 이 우량기업부를 따로 내려주는 50종목(알테오젠·에코프로·에코프로비엠 등)을 KOSDAQ 으로 포함. KONEX 는 계속 제외.
  - 캐시 파일 이름 `krx_tickers_YYYYMMDD.json` → `krx_tickers_v2_YYYYMMDD.json`: 당일 옛 캐시(50종목 누락)를 재사용하지 않고 새로 받는다.
- `tests/test_krx_symbol_search.py`: 캐시 파일명 갱신 + 매핑·KONEX 제외·이름/코드 검색·옛 캐시 무시 테스트 4건.

## 설계 결정 변경 사항

없음.

## 검증 결과

- 실제 FDR 응답: 전종목 2,769건 (이전 2,719 + 50). `알테오젠`/`196170` → `196170 알테오젠 KOSDAQ`, `리노공업` → `058470 KOSDAQ`.
- `pytest` 1109 passed, `ruff check .` 통과.
- 변이 검사: 별칭 매핑을 비우면 3건, 캐시 이름을 되돌리면 3건 실패.

## 다음 작업 핸드오프

- 미등록 후보 이슈: DART 공시 → 뉴스 분석가, 주요뉴스(global news) 복구.
- 결정 대기: 색상 규칙(한국식 상승 빨강/하락 파랑), #152 되돌리기 여부.
