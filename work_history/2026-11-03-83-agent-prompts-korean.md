# [#83] Task 9d: 12개 에이전트 인라인 프롬프트 한국어화

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/83
- PR: (작업 완료 후 추가)
- 상위 에픽: #79
- 브랜치: `feat/83-agent-prompts-korean`
- 작업 기간: 2026-11-03 ~

## 범위

Task 9 에픽의 가장 큰 단일 작업 — 12개 에이전트의 **인라인 시스템 프롬프트**
한국어화. 사용자 승인: 단일 PR, 커밋은 에이전트 그룹별 분할.

### 대상 (12개)
- **분석가 4**: fundamentals / market / news / sentiment analyst
- **리서처 2**: bull / bear researcher
- **매니저 2**: research_manager / portfolio_manager
- **트레이더 1**: trader
- **리스크 디베이터 3**: aggressive / conservative / neutral debator

### 유지 (i18n 경계)
- 함수/변수/파일명 영어
- `NO_EXTERNAL_TOOLS` 상수 (영어) — 그래프 구조 참조 식별자
- state 키 (`market_report`, `fundamentals_report` 등) 영어
- 템플릿 변수 (`{current_date}`, `{instrument_context}` 등) 영어
- 다운스트림 라벨 (`**등급**: BUY`, `**최종 거래 제안**: BUY`) — Task 9b 에서 처리됨
- Task 3 사전조회 리팩터링에 맞춰 "툴을 호출해..." 문구를 "주어진 데이터를
  기반으로..." 로 전환 (code_artifact.md Task 9 작업 내용)

### scope 밖
- KRX 특유 리스크 지침 추가: Task 9e (#84)
- CLI UI 한국어화: Task 9f (#85)

## 수행한 변경

### 분석가 4개 (`tradingagents/agents/analysts/`)

- **fundamentals_analyst.py**:
  - system_message 전면 한국어화 (재무 분석가 역할 / 사전조회 데이터 설명 /
    출력 가이드).
  - `_render_prefetched` 섹션 헤더 (기업 개황 / 재무상태표 / 현금흐름표 /
    손익계산서 / 임원·주요주주 지분변동 / 전환사채 공시) 한국어.
  - ChatPromptTemplate system 메시지 전면 한국어화.
- **market_analyst.py**:
  - system_message 전면 한국어화. 12개 기술지표 설명 (이동평균 / MACD /
    모멘텀 / 변동성 / 거래량) 한국어 재작성.
  - KRX 투자자 수급 지침 한국어 (외국인/기관 매수 흐름 해석).
  - 검증 스냅샷 가이드 한국어.
  - `_render_prefetched` 섹션 헤더 한국어.
- **news_analyst.py**:
  - system_message 전면 한국어화 (한국은행 ECOS 거시 지표 설명).
  - `asset_label` 한국어 ("기업" / "자산").
  - `_render_prefetched` 섹션 헤더 (사전 조회된 뉴스·거시 데이터 / 종목 뉴스 /
    글로벌 거시 뉴스 / 한국 거시경제 지표) 한국어.
- **sentiment_analyst.py**:
  - system / user 프롬프트 전면 한국어화 (분석 방법 베스트 프랙티스 유지).
  - `## Output fields` → `## 출력 필드`, 값 (band / score / confidence) 영어
    유지 (파서 호환).

### 리서처 2개 (`tradingagents/agents/researchers/`)

- **bull_researcher.py**:
  - 강세 리서처 프롬프트 전면 한국어화 (성장 잠재력 / 경쟁 우위 / 긍정 지표 /
    약세 반박 / 대화형 참여).
  - `target_label` / `fundamentals_label` 한국어 ("종목" / "기업 재무 보고서").
  - 자원 라벨 (시장 분석 보고서 / 센티먼트 보고서 / 최신 뉴스) 한국어.
  - **발화자 라벨 `"Bull Analyst:"` 영어 유지** — 다운스트림 코드 식별자.
- **bear_researcher.py**: 대칭 구조로 한국어화.

### 매니저 2개 (`tradingagents/agents/managers/`)

- **research_manager.py**:
  - 리서치 매니저 프롬프트 전면 한국어화.
  - 등급 체계 (`**Buy**` / `**Overweight**` / `**Hold**` / `**Underweight**` /
    `**Sell**`) 설명 한국어, 값 영어 유지.
  - "상충 자체는 Hold 사유가 아닙니다" 지침 한국어화.
  - 출력 섹션 헤더 "## 출력", 라벨 (`**추천**` / `**근거**` / `**전략적 조치**`)
    한국어.
- **portfolio_manager.py**:
  - 포트폴리오 매니저 프롬프트 전면 한국어화.
  - 등급 체계 한국어, 값 영어 유지.
  - "상충 자체는 Hold 사유가 아닙니다" 지침 한국어화.
  - 출력 라벨 (`**등급**` / `**요약 전략**` / `**투자 논리**`) 한국어 — schemas
    render_pm_decision 과 일관.

### 트레이더 (`tradingagents/agents/trader/trader.py`)

- 트레이더 프롬프트 전면 한국어화.
- `grounding` 지침 (가격 수준의 기술적 뿌리내리기) 한국어.
- `report_section` 라벨 ("기술적 시장 보고서") 한국어.
- 출력 라벨 (`**액션**` / `**근거**` / `**진입가**` / `**손절가**` /
  `**포지션 사이징**`) 한국어 — schemas render_trader_proposal 과 일관.
- 액션 값 (Buy / Hold / Sell) 영어 유지.

### 리스크 디베이터 3개 (`tradingagents/agents/risk_mgmt/`)

- **aggressive_debator.py**: 공격적 리스크 분석가 프롬프트 전면 한국어화.
- **conservative_debator.py**: 보수적 리스크 분석가 프롬프트 전면 한국어화.
- **neutral_debator.py**: 중립적 리스크 분석가 프롬프트 전면 한국어화.
- 모두 자원 라벨 (시장 분석 보고서 / 센티먼트 보고서 / 최신 뉴스 / 기업 재무
  보고서) 한국어화.
- 모두 발화자 라벨 (`"Aggressive Analyst:"` / `"Conservative Analyst:"` /
  `"Neutral Analyst:"`) 영어 유지.

### `tradingagents/agents/schemas.py`

- `render_research_plan` 를 Korean 디폴트에서 한국어 라벨 (추천/근거/전략적 조치)
  로 전환. 영어 fallback 유지.

### 테스트 조정

- `tests/test_structured_agents.py`:
  - `TestRenderResearchPlan` — 한국어 라벨 (**추천**/**근거**/**전략적 조치**).
  - `TestResearchManagerAgent::test_structured_path_produces_rendered_markdown`
    — 한국어 라벨.
  - `TestTraderAgent::test_prompt_includes_investment_plan` — "제안된 투자 계획".
  - `TestTraderAgent::test_prompt_includes_market_report_for_price_levels` —
    "기술적 시장 보고서:" / "구체적 가격 수준".
  - `TestTraderAgent::test_empty_market_report_omits_the_section_and_grounding` —
    한국어 헤더 비포함 체크.
  - `test_conflict_alone_is_not_a_hold_trigger` — 한국어 등가 문구 "상충 자체는
    Hold 사유가 아닙니다" 수용.
- `tests/test_rating_integrity.py::test_a_decision_prompt_states_the_shape_of_its_answer`:
  - `must_name` parametrize 한국어 라벨 (`등급` / `추천` / `액션`) 로 전환.
  - 섹션 헤더 `"## 출력"` 또는 `"## Output"` 양쪽 수용.
- `tests/test_memory_log.py::test_pm_prompt_includes_past_context` /
  `test_pm_no_past_context_no_section`:
  - "과거 결정과 결과로부터의 교훈" 한국어 섹션 라벨 체크.

## 설계 결정 변경 사항

### 토론 로그 발화자 라벨 영어 유지

code_artifact.md Task 9 는 "에이전트 인라인 프롬프트" 전수 한국어화 명시. 그러나
리서처/리스크 노드가 `history` 에 추가하는 `f"Bull Analyst: {response.content}"`
형식의 라벨은 **다운스트림 로직이 Bull/Bear/Aggressive/Conservative/Neutral 분기
에 사용** — 프롬프트에서 중요한 식별자 역할. 발화자 라벨만 영어 유지 (i18n 경계,
ADR-0003).

### schemas 필드 설명 영어 유지

ResearchPlan.recommendation / PortfolioDecision.rating 등 Pydantic Field
description 은 구조화 출력 schema 로 LLM 에게 전달. 이들을 한국어로 번역해도
구조화 지원 provider 는 영어 설명을 그대로 수용하지만, "conflict alone is not
a reason to Hold" 같은 명시적 지침은 다른 영어 기반 리서치 참조 (#1321 등) 와
어휘적으로 일치시켜 두는 게 유지보수에 도움. 테스트도 Korean 등가 "상충 자체는
Hold 사유가 아닙니다" 를 양쪽 수용하도록 열어둠.

### render_research_plan Korean 라벨 추가 (9b 범위 확장)

code_artifact.md Task 9b 는 `**Rating**:` 과 `FINAL TRANSACTION PROPOSAL:` 만
명시, Research Plan 렌더는 불포함. 그러나 research_manager 프롬프트가 Korean 으로
가면서 render 함수가 영어 라벨을 출력하면 트레이더가 보는 investment_plan 의
라벨 언어가 어긋남. render_research_plan 도 Korean/English 양쪽 지원하도록 확장.

### Task 9b 디자인 재확인

Portfolio Manager / Research Manager 프롬프트의 `**Rating**:` / `**Recommendation**:`
라벨도 한국어 (`**등급**:` / `**추천**:`) 로 교체. rating.py 파서는 이미 Task 9b
에서 "등급" + "Rating" 양쪽 수용하도록 작성됨 (단, "추천" 은 schema 전용이고
rating.py 파서 대상 아님 — portfolio_manager 의 `**등급**` 만 파서가 매칭).

## 검증 결과

- `pytest -q` 전체 → **851 passed**
- `ruff check tradingagents cli tests` → **All checks passed**

## 완료 criteria 확인

### Task 9d (#83)
- ✓ **분석가 4** (fundamentals / market / news / sentiment) 전면 한국어화
- ✓ **리서처 2** (bull / bear) 전면 한국어화
- ✓ **매니저 2** (research_manager / portfolio_manager) 전면 한국어화
- ✓ **트레이더 1** (trader) 전면 한국어화
- ✓ **리스크 디베이터 3** (aggressive / conservative / neutral) 전면 한국어화
- ✓ Task 3 사전조회 패턴 지원 ("툴을 호출해..." → "주어진 데이터를 기반으로...")
- ✓ 라벨 (등급/추천/액션 등) 한국어, 값 (BUY/SELL/HOLD/Overweight 등) 영어 유지
- ✓ 발화자 라벨 (Bull Analyst 등) 영어 유지 — i18n 경계

## 다음 작업 핸드오프

### Task 9e (#84): KRX 특유 리스크 지침 추가
각 에이전트 (주로 market / news / sentiment / 트레이더 / 리스크) 프롬프트에
KRX 특유 리스크 지침 추가:
- 상·하한가 ±30% 제한
- 관리종목 / 환기종목
- 공매도 금지 종목
- 외국인/기관 수급 공백 영향
- 오버행 이슈 (대주주 매도 가능성)

### Task 9f (#85): CLI UI 한국어화
`cli/display.py`, `cli/prompts.py`, `cli/selections.py`, `cli/run.py`,
`cli/prefs.py` 등의 사용자 노출 문자열 전면 한국어 치환.

