# [#74] Task 8: KRX 거래소 캘린더 매핑 (단일 PR 로 통합)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/74 (epic),
  #75 (8a), #76 (8b), #77 (8c)
- PR: (작업 완료 후 추가)
- 브랜치: `feat/74-krx-calendar`
- 작업 기간: 2026-11-03 ~

## 범위

Task 8 scope 가 작아 하위 이슈 3개를 단일 PR 로 통합:
- 8a. `vendors/krx_calendar.py` 신규 작성
- 8b. `date_window.py` 를 KST 기반으로 + withhold_* dead code 삭제
- 8c. `backtest.py::iter_grid` 를 KRX 영업일 기반으로

## 라이브러리 선택: `exchange_calendars`

**선택 사유:**
- `XKRX` (Korean Exchange) 캘린더 내장 — 설날/추석/광복절/개천절 등 한국 공휴일
  자동 반영
- 순수 Python, API 키 불필요
- `Asia/Seoul` 타임존 지원
- 유지보수 활발 (pandas-market-calendars 와 함께 금융 캘린더 표준)

**대안 비교:**
- `pykrx.stock.get_previous_business_days` — 로그인 경로 포함, CI 에서 불안정
- `pandas_market_calendars` — XKRX 지원하지만 더 무거움 (exchanges 전 영역)
- 수동 공휴일 리스트 — 유지보수 부담, 설날/추석 음력 계산 복잡

## 수행한 변경

### `pyproject.toml`

- `exchange_calendars>=4.0` 명시 의존성 추가.

### `tradingagents/dataflows/krx_calendar.py` 신규

**공개 함수 (6개):**
- `is_trading_day(date_str)` — KRX 영업일인지 (주말/공휴일 자동 제외).
- `previous_trading_day(date_str)` — 바로 이전 영업일. 당일 포함 안 함.
- `next_trading_day(date_str)` — 바로 다음 영업일.
- `trading_days_in_range(start, end)` — 범위 내 모든 영업일 (오름차순).
- `current_trading_date()` — KST 기준 오늘 또는 가장 최근 영업일.
- `filter_to_trading_days(start, end, every_n_days)` — 영업일 리스트 샘플링.
- `to_pandas_index(start, end)` — pandas DatetimeIndex 로 (pykrx OHLCV join 용).

**모듈 수준:**
- `KST = pytz.timezone("Asia/Seoul")` — KST 상수.
- `_calendar()` — `exchange_calendars.get_calendar("XKRX")` lazy singleton
  (`@lru_cache(maxsize=1)`).

### `tradingagents/dataflows/date_window.py`

- `get_current_date()` 를 KST 타임존 기준으로 전환 (`datetime.now(_KST)`).
- 레거시 함수 3개 **전면 삭제**:
  - `withhold_live_profile` — Yahoo `Ticker.info` / Alpha Vantage `OVERVIEW` 전용
  - `withhold_undisclosed_trades` — Yahoo / Alpha Vantage insider 전용
  - `withhold_undated_statements` — Yahoo / Alpha Vantage statements 전용
- 모든 호출 사이트가 Task 7 vendor 삭제로 사라져 dead code 상태였음.
- 모듈 docstring 업데이트: KRX 전용 노트, 삭제 사유 명시.

### `tradingagents/backtest.py`

- `iter_grid`:
  - `is_trading_day` import 추가.
  - 캘린더 간격으로 샘플링한 뒤 영업일만 유지 — `--every 7` 로 월요일 샘플
    시 그 월요일이 공휴일이면 자동 생략.
  - docstring 재작성: KRX 영업일 자동 제외 명시.

### `tests/test_krx_calendar.py` 신규

**21개 테스트**:
- `is_trading_day` 평일/주말/한국 공휴일 (개천절, 한글날, 광복절, 신정, 어린이날) 매트릭스
- 잘못된 날짜 포맷 거부
- `previous_trading_day` 주말/추석 연휴 skip 검증
- `next_trading_day` 주말/연휴 skip 검증
- `trading_days_in_range` 2026-10월 (추석/개천절/한글날 밀집) 샘플 검증
- 범위 끝점 inclusive
- `filter_to_trading_days` 스텝 샘플링 + 0 거부
- `current_trading_date` 유효 영업일 반환
- `to_pandas_index` DatetimeIndex 반환

### `tests/test_backtest.py` 테스트 조정

- `test_grid_stops_at_today` — 토요일 (2026-01-10) 을 today 로 쓰던 걸 월요일
  (2026-01-12) 로 변경. 당시 그리드 결과도 trading-day-aware 로 조정.

## 설계 결정 변경 사항

### `exchange_calendars` vs `pykrx` 캘린더

code_artifact.md Task 8 은 `pykrx.stock.get_market_trading_days_by_range` 사용을
명시했으나 **exchange_calendars 로 변경** — 이유:
1. 로컬 테스트에서 `pykrx.stock.get_previous_business_days` 등 캘린더 API 가 KRX
   로그인 경로 또는 OHLCV JSON 응답 파싱 에러로 CI 환경에서 불안정.
2. `exchange_calendars` 는 순수 Python, 네트워크 호출/API 키 모두 불필요.
3. KRX 공휴일 (설날/추석 음력 계산 포함) 이 내장 캘린더로 유지보수됨.

### `iter_grid` 는 캘린더 스트라이드 + 영업일 필터

최초 구현에서 "매 N 영업일" (`filter_to_trading_days`) 방식으로 시도했으나
`--every 7` 가 "주간 샘플링" → "약 1.5주 샘플링" 으로 바뀌어 사용자 기대와 괴리.
**캘린더 간격으로 샘플 후 영업일만 유지** 방식으로 전환해 "주간" 의미 보존.
결과: Monday 를 start 로 `--every 7` 하면 Monday 들 중 공휴일인 날만 자동 생략.

### `withhold_*` dead code 삭제 (Task 8b 범위 확장)

code_artifact.md Task 8 은 캘린더만 명시하지만, 이번에 `date_window.py` 를 수정
하는 김에 Task 7 머지로 호출 사이트가 사라진 레거시 함수 3개도 정리. 약 60 줄
제거. KRX 전용 vendor (DART / pykrx / 네이버뉴스 / ECOS) 는 공시일 또는 영업일
기반 자체 point-in-time 로직을 갖고 있어 공통 withhold 추상화 불필요.

## 검증 결과

- `pytest tests/test_krx_calendar.py -v` → **21 passed**
- `pytest -q` 전체 → **850 passed**
- `ruff check tradingagents cli tests` → **All checks passed**
- 수동 smoke: `trading_days_in_range("2026-10-01", "2026-10-15")` 가 개천절
  (10/3), 추석 (10/5-10/8), 한글날 (10/9), 토요일 (10/10) 전부 자동 제외 확인.

## Task 8 에픽 (#74) 종결

이 PR 머지 후 모든 하위 이슈 close 가능:
- #75 (8a) ✅ `vendors/krx_calendar.py` 신규
- #76 (8b) ✅ `date_window.py` KST + withhold_* 삭제
- #77 (8c) ✅ `backtest.py::iter_grid` KRX 영업일 기반

## 다음 작업 핸드오프

### Task 9: 한국어 시스템 프롬프트
- 11개 에이전트 (분석가 4 + 리서처 2 + 매니저 2 + 트레이더 + 리스크 3) 의 인라인
  시스템 프롬프트 한국어화.
- KRX 특유 리스크 지침 추가 (상·하한가 ±30%, 관리종목, 공매도 금지, 외국인/
  기관 수급 영향, 환기종목).
- `output_language` 디폴트를 `"English"` → `"Korean"` 로.
- CLI UI (`cli/display.py`, `cli/prompts.py` 등) 한국어화.
- 파서/렌더 (`agents/rating.py`, `agents/schemas.py`, `reporting.py`) 한국어 라벨
  패턴 추가.

### Task 11: 테스트 재작성 (opt-in 통합 테스트)
### Task 12: Docker Claude Code 통합

