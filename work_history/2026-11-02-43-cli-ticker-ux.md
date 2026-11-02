# [#43] Task 4b: CLI 티커 입력 UX 한국 종목 예시로 교체

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/43
- PR: (작업 완료 후 추가)
- 상위 에픽: #41
- 브랜치: `feat/43-cli-ticker-ux`
- 작업 기간: 2026-11-02 ~

## 범위

Task 4a 로 `symbols.py` 가 KRX 전용으로 축소된 후, CLI 입력 UX 와 사용자 안내 메시지를 한국 종목 중심으로 정렬. 미국·홍콩·상해 티커 참조를 전수 정리.

## 수행한 변경

### `cli/prompts.py`

- `TICKER_INPUT_EXAMPLES` 확장:
  - 기존: `"005930 (삼성전자), 000660 (SK하이닉스), 035720 (카카오)"`
  - 신규: 추가 ETF 예시 `069500 (KODEX 200 ETF)` 포함
- `CRYPTO_SUFFIXES` 를 빈 튜플로 축소 (`()`) — KRX 포크는 암호자산 미지원. `detect_asset_type` 가 항상 `AssetType.STOCK` 반환.
- `get_ticker()` 메시지를 한국어로 교체:
  - 질문: `"KRX 종목코드를 입력하세요 (예: ...)"`
  - 검증 실패: `"KRX 6자리 숫자 종목코드만 지원합니다 (예: 005930 삼성전자)."`
  - 빈 입력/취소: `"티커를 입력하지 않아 종료합니다."` (영어 → 한국어)
- 빈 입력의 디폴트 티커를 `"SPY"` → `"005930"` 삼성전자로 변경

### `cli/main.py`

- `--ticker` 플래그 help 문구를 한국어 KRX 예시로:
  - 기존: `"Ticker to analyze, e.g. NVDA or 0700.HK; skips the prompt"`
  - 신규: `"분석할 KRX 종목코드 (예: 005930 삼성전자); 지정하면 프롬프트 생략"`
- `backtest` 명령의 `tickers` argument help:
  - 기존: `"Comma-separated tickers, e.g. NVDA,AAPL"`
  - 신규: `"쉼표로 구분된 KRX 종목코드 (예: 005930,000660,035720)"`
- 빈 티커 리스트 에러 메시지도 한국어로 교체

### `cli/selections.py`

- Step 1 티커 질문 박스 설명을 한국어 KRX 전용으로:
  - 기존: `"Enter the ticker (한국 종목코드 6자리 또는 상류 포맷)"`
  - 신규: `"KRX 종목코드를 입력하세요 (6자리 숫자, 예: 005930 삼성전자)"`

### `README.md`

- "지원 티커 형식" 섹션의 폴백 안내 문구를 **차단 안내** 로 전환:
  - 기존: `"미국 등 해외 종목은 upstream 의 Yahoo Finance 경로가 폴백으로 유지됩니다 (예: AAPL, 0700.HK)."`
  - 신규: `"미국·홍콩·상해 등 해외 종목은 **지원하지 않습니다** (Task 4, 하드 포크 결정 ADR-0001). KRX 외 티커를 입력하면 CLI 가 거부합니다."`

### 테스트 업데이트

- `tests/test_cli_commands.py::test_backtest_rejects_input_that_would_sweep_nothing`:
  - 테스트 입력 티커 `"NVDA"` → `"005930"`
  - 빈 티커 리스트 에러 체크 문구 `"ticker"` → `"종목코드"` (한국어화 반영)

## 설계 결정 변경 사항

### `CRYPTO_SUFFIXES` 빈 튜플화 vs 완전 삭제

`detect_asset_type` 와 `filter_analysts_for_asset_type` 가 아직 `AssetType.CRYPTO` 분기를 가지고 있어 (`cli/models.py`) 완전 삭제 대신 빈 튜플로 둬서 자연스럽게 모든 티커가 stock 으로 분류되도록 변경. Task 7 (뉴스/감성 vendor 교체) 또는 별도 cleanup PR 에서 CRYPTO 분기 전체 삭제 가능.

### i18n 적용 범위

CLAUDE.md §4.1 i18n 경계에 따라:
- **사용자 노출 메시지** 는 한국어 (질문/에러/도움말)
- **플래그 이름, 티커 값, 코드 식별자** 는 영어 유지 (`--ticker`, `005930` 등)

## 검증 결과

- `pytest -q` → **1040 passed, 8 subtests passed**
- `ruff check` → **All checks passed**
- `grep` 전수 확인: `cli/` 내 `AAPL`, `NVDA`, `TSLA`, `0700.HK`, `SPY` 참조 전부 제거됨

## Task 4 에픽 (#41) 종결

이 PR 머지 후 모든 하위 이슈 close 가능:
- #42 (4a) ✅ `symbols.py` 재작성 — 머지됨
- #43 (4b) 🟡 **이 PR** — CLI 티커 입력 UX

Task 5 (DART 교체), Task 6 (pykrx 교체), Task 7 (네이버뉴스/ECOS 교체) 로 진입 가능.

## 다음 작업 핸드오프

- **Task 5·6·7**: vendor 교체 (SEC EDGAR → DART, Yahoo/Alpha Vantage → pykrx, Reddit/StockTwits/FRED → 네이버뉴스/ECOS)
- **CRYPTO 분기 cleanup**: `AssetType.CRYPTO`, `detect_asset_type` 의 crypto 분기, `filter_analysts_for_asset_type` 의 crypto 로직은 Task 7 또는 별도 PR 에서 완전 삭제 고려
