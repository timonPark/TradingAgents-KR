# [#26] Task 2f: 환경변수 참조 전수 삭제 (문서 + conftest)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/26
- PR: (작업 완료 후 추가)
- 상위 에픽: #21
- 브랜치: `feat/26-env-docs-finalize`
- 작업 기간: 2026-11-02 ~

## 범위

코드/문서 전반에서 외부 LLM API 키 환경변수 참조를 삭제. 사용자가 `.env` 에 더 이상 넣지 않을 변수들의 문서/주석도 정리.

Task 2 에픽의 **마지막 정리** — 이 PR 머지 후 에픽 #21 종결 가능.

## 수행한 변경

### `tests/conftest.py`

`_API_KEY_ENV_VARS` 를 14개 → 2개로 축소:
- 삭제: `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `XAI_API_KEY`, `DEEPSEEK_API_KEY`, `DASHSCOPE_API_KEY`, `DASHSCOPE_CN_API_KEY`, `ZHIPU_API_KEY`, `ZHIPU_CN_API_KEY`, `MINIMAX_API_KEY`, `MINIMAX_CN_API_KEY`, `OPENROUTER_API_KEY`, `AZURE_OPENAI_API_KEY`
- 유지: `ALPHA_VANTAGE_API_KEY` (아직 유지되는 alpha_vantage vendor 가 사용 — Task 6 에서 pykrx 로 교체 시 제거), `ANTHROPIC_API_KEY` (`TRADINGAGENTS_CLAUDE_BARE=1` escape hatch 에서만 사용 — CLAUDE.md §4.6)

### `README.md`

**설치 섹션 재구성 (4~6절):**
- **신설 4절**: "Claude Code CLI 설치 및 로그인 (필수)" — `npm install -g @anthropic-ai/claude-code`, `claude login`, `claude -p "ping"` 세 명령 안내
- **기존 4절 → 5절**: 한국 데이터 소스용 라이브러리
- **기존 5절 → 6절**: API 키 설정 — LLM 키 (OpenAI/Anthropic/Google) **삭제**, DART/ECOS 만 유지
- 명시적 경고 추가: "LLM API 키는 설정하지 마세요. ... Task 2 (#21) 로 코드베이스에서 제거되었고 참조되지 않습니다"

**Python API 사용 예시 수정:**
- `config["llm_provider"] = "anthropic"` → config 로 변경 불가 (claude-code 고정) 명시
- 모델명을 Claude Code alias (`sonnet`/`opus`/`haiku`) 로 교체
- `effort`, `quick_effort` 설정 예시 추가
- `output_language` 디폴트가 Korean 임을 명시

**"커스터마이징 범위" 테이블에 LLM 백엔드 row 추가:**
- 상류: "Anthropic/OpenAI/Google/Azure/Bedrock 등 15+ provider"
- 포크: "**Claude Code 헤드리스 단일** (OAuth, Max/Pro 플랜 쿼터, ADR-0001)"

### 다른 문서

- **`CHANGELOG.md`**: 변경 없음. 이것은 상류의 역사적 변경 기록이라 포크의 서사와 섞으면 안 됨. 포크 전용 CHANGELOG 는 별도 Task 에서 고려.
- **`code_artifact.md`**: 변경 없음. 이것은 계획 문서로 LLM API 키들이 "제거 대상" 으로 언급되는 것은 정상.
- **`requirements.txt`**: 변경 없음. pyproject.toml 에 위임 (`.` 하나만).

### 주석 / 레거시 참조

소스 전역에서 `grep` 으로 남은 참조 확인:
- 코드: `claude_code_client.py` 의 `ANTHROPIC_API_KEY` (escape hatch, 유지) 만 남음
- 데이터 vendor: `alpha_vantage/common.py` 의 `ALPHA_VANTAGE_API_KEY` (Task 6 삭제 예정, 유지)
- 문서: README 의 경고 라인, CHANGELOG 의 역사 기록 — 전부 의도된 참조

## 설계 결정 변경 사항

없음. 이슈 #26 명세대로.

**`CHANGELOG.md` 를 건드리지 않은 이유:** 상류의 역사적 릴리스 기록을 포크에서 "삭제됨" 으로 수정하면 정보 손실 — 상류 기여자의 작업 맥락이 보존되어야 합니다. 포크의 변경 서사는 별도 `CHANGELOG-KR.md` 를 Task 11 이후 공개 성숙 시점에 작성하는 것이 자연스럽습니다.

## 검증 결과

- `pytest -q` → **1159 passed, 8 subtests passed**
- `ruff check tradingagents cli tests` → **All checks passed**
- `grep` 전수 확인: 외부 LLM API 키 환경변수 참조는 (a) README 의 "설정 금지" 경고, (b) `claude_code_client.py` 의 `ANTHROPIC_API_KEY` escape hatch, (c) `alpha_vantage/common.py` 의 `ALPHA_VANTAGE_API_KEY` (Task 6 전까지 유지), (d) `code_artifact.md`/`CHANGELOG.md` 의 역사/계획 문서만 남음.

## 다음 작업 핸드오프

### Task 2 에픽 (#21) 종결 조건

이 PR 머지 후 모든 하위 이슈가 close 됨:
- #22 (2a) ✅ 머지됨
- #23 (2b) ✅ 머지됨
- #27 (2c) ✅ 머지됨
- #24 (2d) ✅ 머지됨
- #25 (2e) ✅ 머지됨
- #26 (2f) → 이 PR

에픽 #21 close 후 다음 작업:
- **Task 3**: 분석가 노드 사전조회 리팩터링 (ToolNode 제거) — ADR-0002 반영
- **Task 4**: 티커 정규식 (6자리 숫자)
- **Task 5**: DART 교체 (SEC EDGAR 제거)
- **Task 6**: pykrx 교체 (Alpha Vantage/Yahoo 제거)
- **Task 7**: 네이버뉴스·ECOS 교체 (Reddit/StockTwits/FRED 제거)
- **Task 8**: KRX 캘린더
- **Task 9**: 시스템 프롬프트 한국어화 + 국내 리스크 지침
- **Task 10**: ~~이동됨~~
- **Task 11**: 테스트 재작성 (각 vendor PR 에 묶임)
- **Task 12**: Docker Claude Code 통합
