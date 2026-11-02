# [#42] Task 4a: symbols.py 재작성 (KRX 6자리 검증 + 미국 정규화 삭제)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/42
- PR: (작업 완료 후 추가)
- 상위 에픽: #41
- 브랜치: `feat/42-krx-symbols-rewrite`
- 작업 기간: 2026-11-02 ~

## 범위

`tradingagents/dataflows/symbols.py` 의 상류 Yahoo/HK/상해/forex/crypto 심볼 변환 테이블을 전부 삭제하고 KRX 6자리 숫자 전용 검증 함수를 추가합니다.

## 수행한 변경

### `tradingagents/dataflows/symbols.py` 재작성

**삭제된 심볼:**
- `_FOREX_CURRENCIES` (ISO-4217 통화 집합)
- `_CRYPTO_BASES` (BTC/ETH/SOL 등)
- `_ALIASES` (XAUUSD→GC=F, SPX500→^GSPC 등 ~30개 매핑)
- `_HK_CODE`, `_SHANGHAI_SH` 정규식
- `_CRYPTO_QUOTES` 상수
- `_normalize_crypto` 함수

**신규/변경:**
- `_KRX_TICKER_RE = re.compile(r"^\d{6}$")` — KRX 6자리 숫자 패턴
- `validate_krx_ticker(raw)` **신규** — KRX 전용 엄격 검증. 6자리 숫자 아니면 `ValueError` (한국어 에러 메시지, 예시 삼성전자/SK하이닉스/KODEX 200 포함).
- `normalize_symbol(raw)` **단순화** — lenient 하게 strip + upper 만. 상류 vendor 코드 (Yahoo/Alpha Vantage) 가 Task 6 전까지 이 함수를 호출하므로 호환성 유지. 사용자 입력 검증은 `validate_krx_ticker` 가 담당.
- `crypto_base(raw)` **스텁** — 항상 None 반환. StockTwits/Reddit vendor (Task 7 삭제 예정) 가 import 하므로 유지.
- `safe_ticker_component(value)` **변경 없음** — 파일시스템 경로 안전 가드. 상류와 동일한 넓은 문자 집합 (`[A-Za-z0-9._\-\^=+]`) 허용 (티커 외 run_id 등도 통과시킴).

### `cli/prompts.py`

- `normalize_ticker_symbol(ticker)` 가 `normalize_symbol` 대신 `validate_krx_ticker` 호출로 변경
- 상류의 `except Exception → fallback upper()` 삭제 — `ValueError` 를 그대로 propagate 해 `is_valid_ticker_input` 이 False 로 변환
- 결과: CLI 입력 레벨에서 **KRX 6자리 외 티커 전면 차단**

### `tradingagents/portfolio.py`

- `normalize_symbol` import 삭제
- `_canonical(ticker)` 신규 — 포트폴리오 비교용 strip + upper (대소문자 무시로 레거시 유연성 유지). 상류의 broker-alias 매핑 (BTCUSDT ≡ BTC-USD 등) 은 제거.
- `positions_in`, `render` 가 `_canonical` 사용

### `tradingagents/memory/settlement.py`

- `normalize_symbol` import 삭제
- `resolve_benchmark` 가 `explicit.strip()` 과 `ticker.strip().upper()` 사용 (단순화)

### 삭제된 테스트 파일 (7개)

상류의 US/forex/crypto/HK/상해 심볼 처리 또는 Task 7 (Reddit/StockTwits) 대상 테스트:
- `tests/test_symbols.py` — US/forex/HK/SH/crypto normalize_symbol 테스트
- `tests/test_symbol_normalization_paths.py` — US 심볼 변환 경로
- `tests/test_cli_symbol_handling.py` — US 티커 UI
- `tests/test_ticker_symbol_handling.py` — 거래소 접미사 보존
- `tests/test_crypto_asset_mode.py` — 암호자산 모드
- `tests/test_reddit_fallback.py` — Reddit vendor (Task 7 삭제 예정)
- `tests/test_stocktwits_resilience.py` — StockTwits vendor (Task 7 삭제 예정)

### 수정된 테스트

- `tests/test_memory_log.py`: `test_explicit_benchmark_is_resolved_like_any_other_symbol`, `test_resolve_benchmark_china_a_shares` 삭제 (Yahoo 심볼 alias 변환이 삭제됨)
- `tests/test_portfolio_context.py`: `test_a_holding_under_a_broker_alias_is_the_analyzed_instrument` (parametrized 4개) 와 `test_one_instrument_held_under_two_spellings_shows_both_holdings` 삭제 (US broker alias 로직 삭제됨)
- `tests/test_structured_agent_prompts.py`: `test_the_sentiment_prompt_names_the_subreddits_searched` 삭제 (crypto subreddit 분기 트리거 안 됨)

## 설계 결정 변경 사항

### `normalize_symbol` 과 `validate_krx_ticker` 분리

이슈 #42 는 `normalize_symbol` 을 엄격한 KRX 검증으로 교체하자고 명시했으나, Yahoo/Alpha Vantage vendor 코드 (`vendors/yahoo/market.py`, `vendors/yahoo/fundamentals.py`, `vendors/yahoo/ohlcv.py`) 가 Task 6 (pykrx 교체) 전까지 `normalize_symbol` 을 호출합니다. 두 가지 길이 있었습니다:

- (a) `normalize_symbol` 엄격 → vendor 코드 전부 깨짐 → Yahoo 관련 테스트 170+ 개 실패
- (b) `normalize_symbol` lenient 유지 + `validate_krx_ticker` 신규 → CLI 입력 레벨에서 KRX 강제, vendor 는 Task 6 가 처리

**(b) 를 선택** — Task 6 가 vendor 를 모두 삭제할 때 `normalize_symbol` 도 함께 제거하거나 `validate_krx_ticker` 로 통합합니다. 지금은 **CLI 입력 차단** 이라는 Task 4a 의 목표를 달성하면서 vendor 호환성을 유지하는 중간 상태입니다.

### 호환성 shim 정책

- `crypto_base` → 항상 None (Task 7 전까지 import 호환)
- `_canonical` → `_normalize_symbol` 호출 대신 자체 구현 (portfolio.py 자립)

## 검증 결과

- `pytest -q` → **1040 passed, 8 subtests passed** (삭제된 테스트 반영)
- `ruff check tradingagents cli tests` → **All checks passed**
- 수동 smoke:
  - `validate_krx_ticker("005930")` → "005930" ✓
  - `validate_krx_ticker("AAPL")` → `ValueError("KRX 종목코드는 6자리 숫자입니다 ...")` ✓
  - CLI `get_ticker()` 는 상호작용 테스트 필요 (Task 4b 범위)

## 다음 작업 핸드오프

### Task 4b (#43): CLI 티커 입력 UX 한국 종목 예시로 교체

- `cli/prompts.py` 티커 예시 메시지 재검토 (Task 2c 에서 이미 005930/000660/035720 로 교체되어 있음 — ETF 예시 추가 검토)
- `cli/selections.py` 티커 질문 박스 default `"005930"` 확인
- README/문서의 티커 예시 중 남은 미국 종목 정리
- grep 전수 확인 (`AAPL`, `NVDA`, `TSLA`, `0700.HK` 등)

### Task 6 (vendor 교체) 이후

- `normalize_symbol` 과 `crypto_base` 를 `symbols.py` 에서 제거
- `validate_krx_ticker` 로 통합 또는 유일 함수로 승격
