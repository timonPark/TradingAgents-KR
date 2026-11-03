# [#107] Task 14b: FastAPI 백엔드 스캐폴드

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/107
- PR: (작업 완료 후 추가)
- 상위 에픽: #105
- 브랜치: `feat/107-fastapi-scaffold`
- 작업 기간: 2026-11-04

## 범위

Task 14 (#105) 하위 — Astro 프론트엔드 (`web/`, #108 머지됨) 가 호출할 **FastAPI 백엔드 스캐폴드**. 이 티켓은 **스캐폴드 + 기본 두 엔드포인트(health, symbols/search)** 만. runs/reports 는 14e/14f 에서.

## 수행한 변경

- `api/` 신규
  - `__init__.py`
  - `main.py` — `create_app()` + CORS 미들웨어 + 라우터 등록
  - `config.py` — 포트/CORS origin 환경변수 로딩
  - `models.py` — Pydantic 응답 스키마 (`SymbolHit`, `SymbolSearchResponse`)
  - `routes/__init__.py`
  - `routes/health.py` — `GET /api/health`
  - `routes/symbols.py` — `GET /api/symbols/search` (14a #106 모듈 호출)
- `tests/test_api_health.py` 신규
- `tests/test_api_symbols.py` 신규 (14a 모듈 모킹)
- `pyproject.toml`
  - `[project.optional-dependencies].web` 추가 — `fastapi`, `uvicorn[standard]`, `sse-starlette`
  - `[tool.setuptools.packages.find].include` 에 `api*` 추가
- `.github/workflows/ci.yml` — test job 설치 단계 `.[dev]` → `.[dev,web]` 로 변경 (api 테스트 커버리지)

## 설계 결정

### 왜 `api/` 를 루트 평면에 두나

`tradingagents/`, `cli/` 가 이미 루트 평면이고 `web/` 도 14c 에서 그렇게 뒀음. 일관성 유지.

### 왜 Pydantic 모델을 별도 파일 (`api/models.py`) 로 분리

- 라우터가 늘어날 때 import 경로가 안정
- `tradingagents.dataflows.krx_symbol_search.SymbolHit` 는 **frozen dataclass** (프레임워크 중립). Pydantic `SymbolHit` 는 **API wire schema**. 두 개를 분리해 **내부 도메인 타입이 HTTP 직렬화 가정에 끌려다니지 않도록** 함.

### CORS

`http://localhost:4321` (Astro dev 기본 포트) 만 허용. 환경변수 `TRADINGAGENTS_API_CORS_ORIGINS` 로 override (콤마 구분). 로컬 전용이라 credentials 는 비활성화.

### CI 설치에 `web` extra 추가

기존 `pip install -e ".[dev]"` 로는 `fastapi` 가 없어 API 테스트가 import 실패. `pytest.importorskip` 으로 skip 시킬 수도 있지만 **정상 CI 환경에서 API 테스트가 조용히 건너뛰이는 것은 부정적인 커버리지 시그널**. CI 를 `.[dev,web]` 로 바꿔 강제 실행.

`smoke-install` job 은 그대로 (`pip install .` 만) — runtime deps 가 import 가능한지 검증하는 역할이므로 web extra 없는 상태 유지가 올바름.

### `uvicorn` 기동 커맨드

- 개발: `uvicorn api.main:app --reload --port 8000`
- 상세 안내는 14g (#112) 의 README 업데이트에서

## 검증 결과

- `pytest tests/test_api_*.py -v` → **6 passed** (health 2 + symbols 4)
- `pytest -q` 전수 → **874 passed, 11 deselected** (14a 대비 +6, 회귀 없음)
- `ruff check api tests/test_api_*.py` → All checks passed
- 로컬 기동 smoke: `uvicorn api.main:app --port 18999` → `curl /api/health` → `{"status":"ok"}`

## 다음 작업 핸드오프

- #109 (14d): 이 symbols/search 엔드포인트를 Astro 홈에서 호출 — 검색 자동완성 아일랜드
- #110 (14e): `/api/runs` + SSE `/api/runs/{id}/events` — 이 scaffold 위에 라우터 추가
