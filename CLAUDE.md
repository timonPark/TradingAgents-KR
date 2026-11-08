# CLAUDE.md

TradingAgents-KR 포크를 위한 Claude Code 작업 지침서. 이 디렉터리에서 Claude Code 세션 시작 시 자동 로드됩니다.

## 프로젝트 요지

- TauricResearch/TradingAgents 의 한국 증시(KOSPI/KOSDAQ) 전용 **하드 포크**. upstream 추적 안 함.
- LLM 백엔드: Claude Code 헤드리스 **단일**. Anthropic/OpenAI/Gemini 등 외부 LLM API SDK 는 전부 제거 대상.
- 분석가 노드는 **"사전조회 + 프롬프트 주입"** 패턴 (LangGraph ToolNode/MCP 미사용).
- 설계 문서:
  - `code_artifact.md` — 12개 Task 실행 계획
  - `GLOSSARY.md` — 도메인 용어집
  - `docs/adr/` — 중대 결정 기록 (ADR)

## 작업 흐름

### 1. 이슈 등록 (상위 에픽 + 하위 이슈)

모든 작업은 GitHub 이슈로 등록합니다.

- **상위 에픽**: `code_artifact.md` 의 하나의 Task 와 1:1 대응. 예: "Task 1: Claude Code 헤드리스 LLM 어댑터 구현".
- **하위 이슈**: 에픽을 실행 가능한 단위로 쪼갠 서브태스크. 예:
  - `1a. ChatClaudeCodeHeadless BaseChatModel subprocess 래퍼`
  - `1b. 세마포어 + 타임아웃 + 재시도 정책`
  - `1c. with_structured_output / --json-schema 매핑`
  - `1d. 어댑터 유닛 테스트 (tests/test_claude_code_client.py)`
- 에픽 본문에 하위 이슈를 `- [ ] #NN` 체크리스트로 연결합니다.
- 라벨: `epic`, `task-N`, 영역 라벨(`llm`, `data`, `cli`, `docker`, `test`) 사용.

### 2. 브랜치 → 커밋 → 푸시 → PR → 승인

- **이슈 1개당 브랜치 1개.** 브랜치 이름 규칙: `{type}/{issue-number}-{slug}`
  - type: `feat` (기능), `fix` (버그), `refactor` (리팩터), `test` (테스트만), `docs` (문서), `chore` (설정)
  - 예: `feat/42-claude-code-adapter`, `refactor/51-remove-provider-registry`
- 작업 완료 후 `commit → push → PR` 순서로 진행하고 **머지는 사용자 승인을 기다립니다.**
- PR 설명 템플릿:
  - `Closes #N` (상위 이슈 번호)
  - 변경 요약
  - 테스트 수행 결과 (`pytest`, `ruff` 통과 여부)
  - `code_artifact.md` 계획과 **달라진 지점이 있다면 이유**
- 사용자가 리뷰/머지하기 전까지 **같은 브랜치를 계속 다듬지 않고, 다음 이슈로 넘어갑니다** (리뷰 피드백 수신 전까지 다른 에픽/서브태스크 진행).

### 3. 작업 이력 기록 (`work_history/`)

각 브랜치에서 작업 시작 시 `work_history/yyyy-mm-dd-{이슈식별제목}.md` 파일을 생성해 **작업과 함께 커밋**합니다.

- 파일명 규칙:
  - `yyyy-mm-dd`: 작업 시작일 (ISO 8601, 로컬 KST 기준)
  - `{이슈식별제목}`: `{이슈번호}-{브랜치slug}`
  - 예: `work_history/2026-11-02-42-claude-code-adapter.md`
- 파일 내용 구조:
  ```markdown
  # [#42] Claude Code 헤드리스 LLM 어댑터 구현

  - 이슈: https://github.com/<repo>/issues/42
  - PR: https://github.com/<repo>/pull/<n>
  - 브랜치: feat/42-claude-code-adapter
  - 작업 기간: 2026-11-02 ~ 2026-11-03

  ## 수행한 변경

  - `tradingagents/llm_clients/claude_code_client.py` 신규 (XXX줄)
  - `tradingagents/llm_clients/factory.py` 수정 (claude-code 분기 추가)
  - ...

  ## 설계 결정 변경 사항

  (code_artifact.md 와 달라진 지점이 있다면 이유 기술. 없으면 "없음".)

  ## 검증 결과

  - `pytest tests/test_claude_code_client.py` — 전부 통과
  - 수동 smoke: `claude -p "..."` 응답 정상
  - `ruff check tradingagents` — 통과

  ## 다음 작업 핸드오프

  (연결된 다음 서브태스크나 발견한 후속 이슈)
  ```
- `work_history/` 는 `.gitignore` 대상이 **아님**. PR 과 함께 머지합니다.

### 4. 그 외 작업 규칙

#### 4.1 i18n 경계 (설계 결정)

- **표준 출력 = 한국어** — 사용자에게 노출되는 모든 텍스트 (리포트, CLI UI, 진행 메시지, 에러 메시지, work_history 내용, 커밋 메시지, PR 설명).
- **내부 코드값 = 영어** — enum, 파싱 상수 (`BUY`/`SELL`/`HOLD`), CLI 플래그 이름, 환경변수 이름, 함수/변수/파일명 등 코드 식별자.
- 혼합 케이스: 등급 값은 내부에서 영어(`Buy`/`Underweight` …), 화면에는 한국어(`매수`/`비중 축소` …)로 표기. 파서가 두 표기를 모두 읽는다 (ADR-0004).
- 코드 주석은 영어 또는 한국어 모두 허용. 한국어가 더 명확하면 한국어 우선.

#### 4.2 커밋 규칙

- **한 커밋 = 한 논리적 변경**. 리뷰 가능한 단위로 쪼갭니다.
- 커밋 메시지는 한국어. 첫 줄 요약(50자 이내), 본문에 "왜" 기술.
- `--no-verify`, `--no-gpg-sign`, `--amend` **금지** (사용자가 명시 요청한 경우 제외).
- pre-commit 훅 실패 시 **원인을 수정하고 새 커밋**을 추가 — 훅 우회 시도 금지.
- `.env`, 자격증명 파일, 대용량 바이너리 커밋 금지. `git add .` / `git add -A` 피하고 파일을 명시적으로 지정.

#### 4.3 코드 품질 체크

- 커밋 전: `ruff check tradingagents cli tests` 통과.
- 변경한 영역 관련 테스트 통과: `pytest tests/test_<관련>.py`.
- 어댑터/vendor 신규 작성 시: 해당 유닛 테스트도 **같은 PR 에 포함** (Task 11 의 DoD 규칙).

#### 4.4 설계 문서 유지

- 도메인 용어가 새로 등장하거나 재정의되면 **즉시** `GLOSSARY.md` 업데이트 (해당 PR 에 포함).
- 되돌리기 어려운 결정이 추가로 발생하면 `docs/adr/NNNN-<slug>.md` 신규 작성.
- `code_artifact.md` 는 "계획" 문서입니다. 실행 중 바뀐 결정은:
  1. `work_history/` 에 기록 (즉시)
  2. 해당 PR 머지 시점에 `code_artifact.md` 본문에도 반영 (**계획과 실제의 간극 방지**)

#### 4.5 Claude Code 어댑터 운영 (자기참조 주의)

이 프로젝트의 LLM 어댑터는 다음 플래그로 Claude Code 를 호출합니다:
```
claude -p "<프롬프트>" \
  --output-format json \
  --no-session-persistence \
  --permission-mode plan \
  --disable-slash-commands \
  --exclude-dynamic-system-prompt-sections
```
로컬 수동 디버깅 시 같은 플래그를 쓰면 **이 CLAUDE.md 가 결과를 오염시키지 않습니다** (자동 발견 차단). 어댑터 동작을 재현/디버깅 할 때 활용하세요.

#### 4.6 금지 사항

- `main` 브랜치 직접 커밋/푸시 **금지**. 모든 변경은 PR 경유.
- 강제 푸시(`git push --force`), `git reset --hard origin/*`, 사용자 승인 없는 PR 머지 **금지**.
- 상류 추적 재개(`git remote add upstream TauricResearch/TradingAgents`) **금지** (하드 포크 결정).
- Anthropic/OpenAI/Gemini 등 **외부 LLM API 키 `.env` 추가 금지** (Max 플랜 쿼터 사용).
- `tradingagents/llm_clients/` 아래에 **새 LLM provider 추가 금지** (하드 포크 결정, ADR-0001).
- `tradingagents/agents/analysts/turn.py` 의 LangGraph ToolNode 바인딩 **복원 금지** (ADR-0002, 사전조회 패턴 유지).
- Claude Code `--bare` 모드로 어댑터 운영 변경 **금지** — OAuth 접근이 끊어져 Max 플랜 쿼터 활용이 불가능해집니다. 디버깅용 escape hatch (`TRADINGAGENTS_CLAUDE_BARE=1`) 는 API 키가 명시 설정된 경우에만 사용.

#### 4.7 작업 태도 원칙 (Karpathy 지침 기반)

LLM 코딩의 흔한 실수(조용한 가정, 과설계, 무관한 수정, 모호한 완료 기준)를 줄이기 위한 원칙입니다. 속도보다 신중함 쪽으로 치우친 지침이므로, 오타 수정 같은 사소한 작업은 판단해서 가볍게 적용하세요.

**① 코딩 전에 생각하기**

- 가정을 명시하고, 불확실하면 추측하지 말고 묻습니다.
- 해석이 여러 개면 조용히 하나를 고르지 말고 제시합니다.
- 이슈 범위나 `code_artifact.md` 계획이 모호하거나 서로 어긋나 보이면 구현 전에 멈추고 확인합니다 (구현 후 수정보다 싸다).
- 더 단순한 방법이 있으면 말하고, 필요하면 반박합니다.

**② 단순함 우선**

- 이슈가 요구한 것만 구현합니다. 요청하지 않은 기능·설정·"유연성"을 넣지 않습니다.
- 한 곳에서만 쓰는 코드에 추상화를 만들지 않습니다.
- 일어날 수 없는 상황의 에러 처리를 넣지 않습니다. (외부 경계 — `claude` subprocess, 데이터 vendor 응답 — 는 실제로 실패하므로 예외)
- 200줄이 50줄로 줄면 다시 씁니다.

**③ 외과적 변경**

- 인접 코드·주석·포맷을 "개선"하지 않고, 기존 스타일을 따릅니다.
- 내 변경으로 안 쓰이게 된 import/변수/함수만 지웁니다. 원래부터 있던 dead code 는 지우지 말고 PR 설명이나 `work_history/` 핸드오프에 언급만 합니다.
- 변경된 모든 줄은 해당 이슈에서 직접 추적 가능해야 합니다. 범위 밖 발견은 **새 이슈 후보**로 기록합니다 (§1, §2 의 "이슈 1개 = 브랜치 1개" 와 같은 맥락).
- 단, 외부 LLM SDK 제거처럼 이슈가 **명시적으로 삭제를 요구한 경우**는 이 원칙의 대상이 아닙니다.

**④ 목표 기반 실행**

- 작업을 검증 가능한 목표로 바꿉니다: "버그 수정" → "재현 테스트 작성 후 통과", "리팩터" → "전후 테스트 통과 확인".
- 여러 단계 작업은 `1. [단계] → 검증: [확인 방법]` 형태로 짧게 계획을 세우고 진행합니다.
- 검증 수단은 §4.3 (`ruff`, `pytest`) 을 따르고, 결과를 PR 설명과 `work_history/` "검증 결과" 에 그대로 기록합니다.

## 참조 문서

- `code_artifact.md` — 12개 Task 실행 계획 (요구사항·범위·대상 파일)
- `GLOSSARY.md` — 도메인 용어집 (종목코드, 사전조회 패턴, i18n 경계 등)
- `docs/adr/` — 중대 결정 기록 (ADR)
- `README.md` — 사용자 대상 소개 (Task 완료 후 한국어화 예정)
- `work_history/` — 브랜치별 작업 이력 (per-issue 기록)
