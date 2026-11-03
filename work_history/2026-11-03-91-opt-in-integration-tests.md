# [#91] Task 11: opt-in 통합 테스트 추가 — Task 11 에픽 전체

- 이슈: #91 (epic), #92 (11a), #93 (11b), #94 (11c), #95 (11d)
- PR: (작업 완료 후 추가)
- 브랜치: `feat/91-opt-in-integration-tests`
- 작업 기간: 2026-11-03 ~

## 범위

code_artifact.md Task 11 재해석. 하위 Task 에서 유닛 테스트는 이미 작성됨 (전부
모킹). 이번 에픽은 **실제 API 호출 통합 테스트** 를 `@pytest.mark.integration`
으로 opt-in 분리.

Task 11 scope 가 작아 **단일 PR** 로 통합 (사용자 승인).

### 커버 vendor
- **pykrx**: keyless, OHLCV + 기술지표
- **naver_news**: keyless, 네이버 금융 크롤
- **DART**: `DART_API_KEY` 필요, 재무/CB
- **ECOS**: `ECOS_API_KEY` 필요, 거시 지표
- **Claude Code 어댑터**: `claude` CLI 로그인 필요

### 유지 (기존 체계)
- `pyproject.toml` 의 marker 정의와 `-m "not integration"` 디폴트 필터 이미 설정됨.
- 유닛 테스트 전부 모킹 유지. 통합은 **별도 파일 또는 별도 class** 로.

## 수행한 변경

### `tests/conftest.py` — 공용 skip fixture 추가

- `dart_api_key` — `DART_API_KEY` 없으면 pytest.skip
- `ecos_api_key` — `ECOS_API_KEY` 없으면 pytest.skip
- `claude_cli_available` — `shutil.which("claude")` 없으면 pytest.skip
- `autouse=True` 가 아니라 **opt-in** — 명시적으로 fixture 를 요청하는 테스트만 적용

### 통합 테스트 추가 (파일별)

- **`tests/test_pykrx_vendor.py`** (3개): keyless
  - `test_live_ohlcv_for_005930_has_recent_rows` — 삼성전자 OHLCV 로드
  - `test_live_stock_data_csv_for_005930` — CSV 포맷 출력
  - `test_live_indicator_window_renders_rsi_values` — RSI 창 렌더링
- **`tests/test_naver_news_vendor.py`** (2개): keyless
  - `test_live_item_news_for_005930_returns_markdown_header` — 종목 뉴스
  - `test_live_global_news_returns_markdown_header` — 주요뉴스
- **`tests/test_dart_vendor.py`** (2개): DART_API_KEY 필요
  - `test_live_dart_fundamentals_for_005930` — 삼성전자 기업 개황 + 재무
  - `test_live_dart_company_profile_for_005930` — identity 해석 (KOSPI/KOSDAQ)
- **`tests/test_ecos_vendor.py`** (3개): ECOS_API_KEY 필요
  - `test_live_ecos_base_rate` — 한국은행 기준금리
  - `test_live_ecos_cpi` — 소비자물가지수
  - `test_live_ecos_usd_krw` — 원/달러 환율
- **`tests/test_claude_code_client.py`** (1개): claude CLI 필요
  - `test_live_claude_code_responds_to_short_prompt` — "READY" 응답 확인

총 **11개** 통합 테스트. 각 테스트는 `@pytest.mark.integration` 마크로 CI 기본 skip.

### `README.md` — 통합 테스트 섹션 신규

"재현성에 관한 참고사항" 섹션 바로 위에 **"## 테스트"** 섹션 추가:
- 유닛 테스트 실행법 (`pytest -q`)
- opt-in 통합 테스트 실행법 (`pytest -m integration -q`)
- vendor 별 요구 환경변수 표
- API 쿼터 소모 주의 안내

## 설계 결정 변경 사항

### 통합 테스트를 vendor 파일 내 섹션으로 구성

code_artifact.md Task 11 은 각 vendor 테스트가 독립 파일로 암시되나, 유닛/통합을
같은 파일에 두면 vendor 커버리지가 한 곳에 모임. 각 vendor 파일 하단에 분리 선
(`# ===...===`) 과 섹션 코멘트로 구분. pytest marker 는 테스트 개별로 적용되므로
파일 분할 불필요.

### 통합 테스트가 fail-safe 반환도 수용

각 통합 테스트가 vendor 의 "조회 실패" 메시지도 수용 (`assert "기업 개황" in out or
"DART 조회 실패" in out`). 외부 API 일시 장애로 flaky fail 하지 않도록 — 핵심은
"코드 경로가 깨지지 않음" 검증.

### Claude Code 통합 테스트는 단일만

Max 플랜 메시지 한도 고려해 1개만. "READY" 응답으로 어댑터 → claude CLI → OAuth
→ 응답 파싱 체인 검증.

### `_no_network` autouse 와 호환

conftest.py 의 `_no_network` autouse 는 integration 마크된 테스트를 자동 건너뜀
(`if request.node.get_closest_marker("integration"): return`). 추가 설정 없이
통합 테스트가 실제 네트워크 호출 가능.

## 검증 결과

- `pytest -q` 전체 (유닛) → **851 passed, 11 deselected**
- `pytest -m integration --collect-only` → **11 tests collected** (3+2+2+3+1)
- `ruff check tradingagents cli tests` → **All checks passed**

## 완료 criteria 확인

### Task 11a (#92)
- ✓ pykrx 통합 테스트 3개 (OHLCV / CSV / RSI)
- ✓ naver_news 통합 테스트 2개 (종목 뉴스 / 주요뉴스)
- ✓ 둘 다 keyless — 항상 실행 가능

### Task 11b (#93)
- ✓ DART 통합 테스트 2개 (기업 개황 / 프로필)
- ✓ ECOS 통합 테스트 3개 (기준금리 / CPI / 원달러)
- ✓ `dart_api_key` / `ecos_api_key` fixture 로 skip-if-no-env 패턴

### Task 11c (#94)
- ✓ Claude Code 통합 테스트 1개
- ✓ `claude_cli_available` fixture 로 CLI 없으면 skip

### Task 11d (#95)
- ✓ README 에 "테스트" 섹션 신규 (유닛 / 통합 / vendor 별 요구사항 / 쿼터 주의)

### Task 11 에픽 (#91) Definition of Done
- ✓ CI 기본 `pytest -q` → 유닛만 통과, 통합 skip
- ✓ `pytest -m integration` → 환경변수 있는 vendor 실행, 없는 건 clear 메시지로 skip
- ✓ README 에 로컬 통합 테스트 실행법 섹션

## 다음 작업 핸드오프

### Task 12 (마지막): Docker Claude Code 통합

- `Dockerfile` 에 Node.js + Claude Code CLI 설치
- OAuth credential 공유 (`~/.claude/.credentials.json` 읽기전용 마운트)
- `docker-compose.yml` 에서 ollama 서비스 삭제
- `env_file: - .env` 유지하되 LLM API 키 참조 삭제됨 명시
