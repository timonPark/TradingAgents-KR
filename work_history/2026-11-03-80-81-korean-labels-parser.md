# [#80 #81] Task 9a + 9b: 한국어 라벨 지침 + 파서 / 렌더 Korean 패턴 지원

- 이슈: #80 (9a), #81 (9b)
- PR: (작업 완료 후 추가)
- 상위 에픽: #79
- 브랜치: `feat/80-81-korean-labels-parser`
- 작업 기간: 2026-11-03 ~

## 범위

Task 9a 와 9b 는 **tightly coupled** — LLM 이 한국어 라벨 (`**등급**: BUY`,
`**최종 거래 제안**: BUY`) 을 생성하도록 지시하는 변경과, 파서/렌더가 그 라벨을
수용하는 변경이 **동시에** 일어나야 파싱 블랙아웃이 발생하지 않음. 사용자 승인
받고 단일 PR 로 통합.

### 9a scope (#80)
- `default_config.py::output_language` 기본값 — 이미 Task 2 (#21) 에서 `"Korean"`
  으로 변경됨. 변경 없음.
- `context.py::get_language_instruction()` 재작성:
  - 한국어 전용 분기 신규 추가 — 라벨은 한국어 (`등급`, `최종 거래 제안`), 값은
    영어 (BUY/SELL/HOLD) 사용 지시.
  - 영어 분기 유지 (하위 호환).
  - 그 외 언어 분기 유지 (영어 라벨 fallback).

### 9b scope (#81)
- `rating.py` 정규식에 한국어 라벨 (`등급`, `최종 거래 제안`) 패턴 추가.
- `schemas.py` `FINAL TRANSACTION PROPOSAL: **{action}**` 렌더링 템플릿에 한국어
  라벨 옵션 — `output_language == "Korean"` 이면 `최종 거래 제안: **{action}**`.
- 파서가 영어/한국어 라벨 양쪽 수용 (하위 호환).

### scope 밖 (다음 단계)
- `reporting.py` 라벨 한국어화: Task 9c (#82)
- 11개 에이전트 인라인 프롬프트: Task 9d (#83)
- KRX 리스크 지침: Task 9e (#84)
- CLI UI: Task 9f (#85)

## 사전 확인 (사용자가 승인한 결정)

**결정 1**: 9a + 9b 통합 PR. 사유 — 파싱 블랙아웃 방지 필요.

## 수행한 변경

### `tradingagents/agents/rating.py` — 파서 regex 확장

- `_LABEL_TOKEN` 신규 상수 추가 — 영어 `rating\b` + 한국어 `등급` /
  `최종[\s·]*거래[\s·]*제안` 알터네이션.
- `_RATING_LABEL_RE` 를 `_LABEL_TOKEN` 사용으로 재조립.
- `_OWN_QUALIFIER` 에 한국어 수식어 추가 (`최종` / `우리` / `전체` / `권장` /
  `수정` / `갱신` / `신규` / `현재`). 공백 매칭도 `\s+` → `\s*` 로 완화 (한국어
  수식어 뒤 공백 없이 "최종등급" 인접 케이스 수용).
- `_RATING_SCALE_RE` 에 한국어 범례 패턴 (`등급\s*(?:척도|옵션|범례)`) 추가.
- 모듈 docstring: Task 9b (#81) 노트 추가, i18n 전략 명시.
- **값 추출 로직 불변** — BUY/SELL/HOLD 등 영어 값만 매칭.

### `tradingagents/agents/schemas.py` — 렌더 템플릿 i18n

- `_output_language()` 신규 — `get_config().get("output_language")` 안전 조회.
- `render_trader_proposal`:
  - Korean 분기 시 라벨 (액션/근거/진입가/손절가/포지션 사이징/최종 거래 제안)
    한국어 치환.
  - `"not provided"` → `"제공되지 않음"`.
  - 영어 분기 (fallback) 유지.
- `render_pm_decision`:
  - Korean 분기 시 라벨 (등급/요약 전략/투자 논리/목표가/투자 기간) 한국어
    치환.
  - 영어 분기 유지.

### `tradingagents/agents/context.py` — `get_language_instruction` 재작성

- Korean 전용 분기 신규 — 한국어 라벨 + 영어 값 지침, 번역/부정형 금지 경고.
- 영어 분기 유지 (empty 반환).
- 그 외 언어 fallback 유지 (영어 라벨 지시).
- 디폴트 fallback `"English"` → `"Korean"` (하드 포크 디폴트 일치).

### 테스트 수정

- `tests/test_structured_agents.py::TestRenderTraderProposal`:
  - 3개 테스트: 영어 라벨 → 한국어 라벨.
  - 신규 테스트 `test_english_output_language_uses_english_labels` 추가 — 영어
    fallback 검증.
- `tests/test_structured_agents.py::test_a_field_the_model_did_not_give_says_so`
  — Korean 라벨 (목표가/제공되지 않음) 로.
- `tests/test_structured_agents.py::test_the_trader_names_the_levels_it_did_not_give`
  — Korean 필드 (진입가/손절가/포지션 사이징) + 안내.
- `tests/test_structured_agents.py::TestTraderAgent::test_structured_path_produces_rendered_markdown`
  — Korean 라벨.
- `tests/test_memory_log.py::test_pm_returns_rendered_markdown_with_rating` — Korean 라벨.

## 설계 결정 변경 사항

### 9a + 9b 통합 PR (사용자 승인 받음)

사유 — LLM 이 한국어 라벨을 생성하도록 지시하는 변경 (9a) 과 파서가 그 라벨을
수용하는 변경 (9b) 이 **동시에** 일어나야 파싱 블랙아웃 없음. 분리 머지는 라벨
생성/파싱이 어긋나는 위험 시간대 발생.

### 라벨 번역 범위 확장 (Executive Summary / Investment Thesis 등)

code_artifact.md Task 9b 는 `**Rating**:` 과 `FINAL TRANSACTION PROPOSAL:` 만
명시. 그러나 render 함수는 Executive Summary / Investment Thesis / Price Target
/ Time Horizon 라벨도 함께 포함 — 섹션별로 혼재된 언어는 가독성 저하. 전체 렌더
라벨을 Korean 모드에서 한국어로 통일. 파서는 "등급" / "최종 거래 제안" 만 매칭
하므로 영향 없음.

### `_OWN_QUALIFIER` 한국어 수식어

영어 수식어 (`final`, `our`, `overall`, ...) 는 공백 `\s+` 로 분리됐으나 한국어
"최종등급" 같은 공백 없는 조합도 자연스러워 `\s*` 로 완화. 영어 경우 `\s*` 는
수식어 없는 경우 (예: `rating:`) 와 수식어 + 공백 (`final rating:`) 둘 다 매칭
해 영향 없음.

### `_output_language()` fail-safe

`get_config()` 가 테스트 셋업 등에서 호출 불가할 수 있어 try/except 로 "Korean"
fallback. 하드 포크 디폴트와 일치하므로 설정 접근 실패해도 올바른 기본값.

## 검증 결과

- `pytest -q` 전체 → **851 passed**
- `ruff check tradingagents cli tests` → **All checks passed**
- 파서 smoke (13 케이스 — 영어 + 한국어 라벨 + Negative) 전부 통과

## 완료 criteria 확인

### Task 9a (#80)
- ✓ `default_config.output_language` 디폴트가 `"Korean"` — 이미 Task 2 에서 설정됨
- ✓ `context.get_language_instruction` 가 Korean 전용 분기로 한국어 라벨 지침 반환
- ✓ 예시 (`**등급**: BUY`, `**최종 거래 제안**: BUY`) 포함

### Task 9b (#81)
- ✓ `rating.py` 정규식에 한국어 라벨 (`등급`, `최종 거래 제안`) 패턴 추가
- ✓ BUY/SELL/HOLD 값 추출 로직 불변 (영어만 매칭)
- ✓ `schemas.py` `FINAL TRANSACTION PROPOSAL: **{action}**` 템플릿 Korean 분기
- ✓ 영어 라벨 하위 호환 테스트 추가 + 통과

## 다음 작업 핸드오프

### Task 9c (#82): `reporting.py` 라벨 한국어화
- `f"- Rating: {run_rating(...)}"` (라인 26) → `f"- 등급: ..."`
- 기타 사용자 노출 라벨 전수 확인

### Task 9d (#83): 11개 에이전트 인라인 프롬프트 한국어화
### Task 9e (#84): KRX 특유 리스크 지침 추가
### Task 9f (#85): CLI UI 한국어화

