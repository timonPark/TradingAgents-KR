# [#106] Task 14a: KRX 종목명 검색 공통 모듈

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/106
- PR: (작업 완료 후 추가)
- 상위 에픽: #105 (Task 14: Astro + FastAPI 로컬 프론트엔드)
- 브랜치: `feat/106-krx-symbol-search`
- 작업 기간: 2026-11-04 ~

## 범위

Task 14 (#105) 하위 — CLI (`cli/prompts.py`) 와 웹 API (`api/routes/symbols.py`) 가 공유할 **KRX 종목명 → 종목코드 검색 모듈** 신규 구현.

기존 Task 13 (CLI 종목 검색) 은 Task 14 에 흡수. CLI/웹이 동일한 Python 모듈을 임포트해 사용 — 중복 구현 없음.

## 수행한 변경

- `tradingagents/dataflows/krx_symbol_search.py` 신규
- `tests/test_krx_symbol_search.py` 신규 (pykrx 모킹)

## 설계 결정

### 데이터 소스: `pykrx.stock.get_market_ticker_list` + `get_market_ticker_name`

- **keyless** — KRX 로그인 자격증명 불필요 (OHLCV 와 동일, `vendors/pykrx.py` 각주 참조)
- KOSPI + KOSDAQ 전종목 수집. KONEX 는 분석 대상 아님 (ADR 확인 필요 시 추후 포함)

### 캐시 전략: 하루 1회 JSON 캐시

- 경로: `~/.tradingagents/cache/krx_tickers_YYYYMMDD.json`
- 환경변수 `TRADINGAGENTS_CACHE_DIR` 로 base 경로 override 가능 (기존 `default_config.py` 규약과 일관)
- 캐시 키는 **KRX 영업일** (`krx_calendar.current_trading_date()`). 매일 갱신 시 신규 상장/폐지 반영.
- 캐시 손상(JSON 파싱 오류, 스키마 불일치) 시 재생성.

### 검색 알고리즘

1. 6자리 숫자 입력 → 정확 매칭 (단일 결과)
2. 그 외 문자열 → 종목명 대상 부분 매칭 (대소문자 무시)
3. 정렬: `startswith` 결과 우선, 그 다음 `contains`. 각 그룹 내 종목명 알파벳/가나다 사전순
4. `limit` (기본 20) 개까지 반환

가나다 정렬은 Python 기본 유니코드 비교로 충분 — 로케일 의존 없음.

### 왜 "시가총액 순" 이 아닌 "사전순" 인가

시가총액을 가져오려면 `get_market_cap_by_ticker` 추가 호출이 필요하고 이는 KRX 로그인 요구 API. **keyless** 유지하려고 사전순으로 단순화. 추후 정밀한 ranking 이 필요하면 별도 티켓.

### 공개 API

```python
@dataclass(frozen=True)
class SymbolHit:
    ticker: str          # 6자리
    name: str
    market: Literal["KOSPI", "KOSDAQ"]

def search(query: str, limit: int = 20, as_of: date | None = None) -> list[SymbolHit]: ...
def list_all(as_of: date | None = None) -> list[SymbolHit]: ...
```

## 검증 결과

- `pytest tests/test_krx_symbol_search.py -q` → **17 passed**
- `pytest -q` (전수) → **868 passed, 11 deselected** (통합 테스트 제외, 회귀 없음)
- `ruff check tradingagents/dataflows/krx_symbol_search.py tests/test_krx_symbol_search.py` → **All checks passed**

## 다음 작업 핸드오프

- #107 (14b): FastAPI 백엔드 스캐폴드 — 이 모듈의 `search()` 를 `/api/symbols/search` 엔드포인트에서 호출
- #112 (14g): CLI `cli/prompts.py` 에도 이 모듈 연결
