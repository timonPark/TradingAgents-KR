# [#85] Task 9f: CLI UI 한국어화 — Task 9 에픽 마지막 단계

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/85
- PR: (작업 완료 후 추가)
- 상위 에픽: #79
- 브랜치: `feat/85-cli-ui-korean`
- 작업 기간: 2026-11-03 ~

## 범위

CLI 사용자 노출 문자열 전수 한국어 치환.

### 대상 파일 (약 2,263 lines)
- `cli/prompts.py` (349) — Task 4b 에서 티커 입력 UX 는 이미 한국어화. 나머지 조사.
- `cli/selections.py` (260) — 단계별 질문 박스 (Task 4b 에서 Step 1 티커는 이미 한국어)
- `cli/display.py` (622) — Rich 콘솔 표/제목/진행 메시지
- `cli/run.py` (465) — run_analysis 진행 메시지
- `cli/prefs.py` (92) — 사용자 preferences 관련
- `cli/main.py` (164) — Task 4b 에서 티커 플래그 help 는 이미 한국어. 나머지 조사.
- `cli/stats_handler.py` (76)
- `cli/updates.py` (220)

### 유지 (i18n 경계 ADR-0003)
- CLI 플래그 이름 (`--ticker`, `--analysts`, `--output-format` 등)
- 환경변수 이름 (`TRADINGAGENTS_LLM_PROVIDER`, `DART_API_KEY` 등)
- 코드 식별자 (파이썬 함수/변수/모듈명)
- Rich 콘솔의 CSS 스타일/색상 이름

## 수행한 변경

### `cli/prompts.py`
- `ANALYST_CHOICES` 표시명을 한국어로 ("시장 분석가 (Market)" 등). enum 값 영어 유지.
- `_CLAUDE_MODELS` 설명 한국어화 (Sonnet/Opus/Haiku 티어 설명).
- `_EFFORT_LEVELS` 레벨 설명 한국어화 (High/Medium/Low/Xhigh/Max).
- `select_analysts` / `select_research_depth` / `_require_text` / `_prompt_custom_model_id`
  / `_select_model` / `ask_effort` / `ask_output_language` 프롬프트 메시지 한국어화.
- 티어 라벨 (`"심층 추론"` / `"간이 추론"`) 로직 추가 — mode="deep" / "quick" 분기.

### `cli/selections.py`
- 환영 패널 제목/부제목 ("TradingAgents-KR 에 오신 것을 환영합니다") 한국어.
- 워크플로 단계 "I. 분석가 팀 → II. 리서치 팀 → ..." 한국어.
- 7단계 질문 박스 (`1단계: 종목코드` ~ `7b단계: 간이 추론 Effort`) 한국어.
- 환경변수 pre-filled 메시지 ("[green]✓ 환경변수에서 ...:[/green]") 한국어.
- 날짜 파싱 에러 "오류:" 한국어.

### `cli/display.py`
- `_AGENT_DISPLAY_NAMES` dict 신규 — 영어 노드 ID → 한국어 표시명 매핑. `agent_status`
  keys 와 LangGraph 노드 이름이 일치해야 하므로 **내부 키는 영어 유지**, 표시만 매핑.
- `_TEAM_DISPLAY_NAMES` dict 신규 — 팀 영어 ID → 한국어 표시명.
- `_STATUS_DISPLAY_NAMES` dict 신규 — pending/in_progress/completed/error → 한국어.
- Welcome 패널 제목 한국어 ("TradingAgents-KR CLI 에 오신 것을 환영합니다").
- 테이블 컬럼 ("팀/에이전트/상태", "시각/유형/내용"), 패널 제목 ("진행 상황",
  "메시지 & 툴", "현재 보고서") 한국어.
- 통계 라벨 ("에이전트: ", "LLM 호출: ", "툴 호출: ", "토큰: ", "보고서: ") 한국어.
- `section_titles` dict 섹션 명 (시장/감성/뉴스/재무 분석, 리서치 팀 결정 등) 한국어.
- `display_complete_report` 섹션 헤더 (I~V) + 각 에이전트 패널 타이틀 한국어.

### `cli/run.py`
- `_announce_checkpoint_state` 메시지 ("저장된 run 을 이어서 실행합니다",
  "분석을 새로 시작합니다") 한국어.
- `_build_run_config` 환경변수 override 메시지 한국어.
- `run_analysis` 터미널 없음 안내, 선택 요약 ("종목코드:", "분석일:", "선택된 분석가:")
  한국어.
- 리서치 팀 / 리스크 디베이터 섹션 헤더 ("### 강세 리서처 분석" 등) 한국어.
- 분석 완료 메시지 ("분석 완료!") 한국어.
- 재검토 알림 메시지 한국어.
- `_offer_reports` 저장/HTML/브라우저/표시 질문 전부 한국어.

### `cli/main.py`
- app `help` 메시지 한국어 ("TradingAgents-KR CLI: 한국 증시 멀티에이전트 LLM 트레이딩
  프레임워크").
- `analyze` / `backtest` 모든 flag `help` 메시지 한국어화 (단, 플래그 이름 / 환경변수
  이름 / 코드 식별자는 영어 유지).
- `analyze` 함수 docstring 한국어.
- `backtest` 함수 docstring 한국어.
- 체크포인트 삭제 메시지, 에러 메시지, 완료 메시지 ("실패:", "settle 안 됨:") 한국어.
- Windows 콘솔 없음 에러 한국어.

### `cli/updates.py`
- 업데이트 패널 제목 "What's new" → "새 소식" 한국어.

### 테스트 조정
- `tests/test_cli_memory_log.py::test_the_cli_run_says_whether_it_resumed`:
  - parametrize 에 한국어 등가 문구 ("저장된 run 을 이어서", "분석을 새로 시작") 추가.
- `tests/test_cli_memory_log.py::test_a_run_without_checkpointing_says_nothing_about_resuming`:
  - 한국어 "이어서" / "새로 시작" 체크도 추가.
- `tests/test_cli_no_console.py::test_missing_console_prints_actionable_message`:
  - "Windows 콘솔을 사용할 수 없습니다" 로 기대값.
- `tests/test_cli_headless.py` (4개 테스트):
  - 질문 매핑 ("Save report" → "보고서를 저장", "Save path" → "저장 경로",
    "HTML" 유지, "browser" → "브라우저", "Display full report" → "전체 보고서를
    화면에 표시") 한국어 치환.
  - `_a_page_the_browser_cannot_open_is_pointed_to` 의 split delimiter 한국어 변경.
- `tests/test_rating_integrity.py::test_the_cli_says_when_a_run_produced_no_usable_rating`:
  - "review" 또는 "재검토" 매칭.

## 설계 결정 변경 사항

### 내부 식별자 vs 표시명 분리 (display.py)

display.py 의 `agent_status` dict keys 는 LangGraph 노드 이름 ("Market Analyst",
"Bull Researcher" 등) 과 일치해야 함. 테이블/패널에 이 영어 키를 그대로 보이는 대신
`_AGENT_DISPLAY_NAMES` 매핑 테이블을 추가해 렌더 시점에 한국어 번역. 코드 전체를
한국어 키로 바꾸는 대신 **얇은 번역 레이어** 로 처리 — 유지보수 범위 축소 +
그래프 라우팅 깨짐 방지.

### `TraderAgent` 표시명 / 노드 ID 불일치는 reporting.py 와 일관

Task 9c 에서 `reporting.py::_SECTIONS` 도 노드 ID (영어) 와 표시명 (한국어) 을
분리. display.py 가 같은 패턴을 따름 — 두 모듈의 i18n 전략 일관성 유지.

### `output_language = "Korean"` 메뉴 1순위

`ask_output_language` 선택 메뉴에서 Korean 을 **첫 번째** 로 두고 "(Korean, 기본값)"
표시. KRX 전용 포크의 디폴트가 Korean 이라는 점을 UI 에서 즉시 명확히.

## 검증 결과

- `pytest -q` 전체 → **851 passed**
- `ruff check tradingagents cli tests` → **All checks passed**

## 완료 criteria 확인

### Task 9f (#85)
- ✓ `cli/display.py` (622 lines) — Rich 콘솔 표/제목/진행 메시지/통계 전부 한국어
- ✓ `cli/prompts.py` (349 lines) — 7단계 질문/모델/에이전트 선택 메뉴 전부 한국어
- ✓ `cli/selections.py` (260 lines) — Welcome 패널 + 7단계 질문 박스 전부 한국어
- ✓ `cli/run.py` (465 lines) — 분석 진행 메시지, 체크포인트 안내, 보고서 저장
  질문 전부 한국어
- ✓ `cli/main.py` — 모든 flag help, docstring, 에러/완료 메시지 한국어
- ✓ `cli/updates.py` — 패널 제목 한국어
- ✓ **CLI 플래그 이름** (`--ticker`, `--analysts`, `--save` 등) 영어 유지
- ✓ **환경변수 이름** (`TRADINGAGENTS_LLM_PROVIDER` 등) 영어 유지
- ✓ **코드 식별자** (함수/변수/모듈/노드 ID) 영어 유지
- ✓ Rich 콘솔 스타일/색상 이름 (`fg:magenta`, `border_style="green"`) 영어 유지

## 다음 작업 핸드오프

### Task 9 에픽 종결

이 PR 머지 후 Task 9 (#79) 완전 종결 가능:
- #80 (9a) ✅ default_config output_language + get_language_instruction
- #81 (9b) ✅ rating.py / schemas.py 한국어 라벨 패턴
- #82 (9c) ✅ reporting.py / report_html.py 라벨 한국어화
- #83 (9d) ✅ 12개 에이전트 인라인 프롬프트 한국어화
- #84 (9e) ✅ KRX 특유 리스크 지침 추가
- #85 (9f) 🟡 이 PR — CLI UI 한국어화

### 이후 Task
- Task 11: 테스트 opt-in 통합 테스트
- Task 12: Docker Claude Code 통합

