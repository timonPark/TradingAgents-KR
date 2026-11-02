# ADR-0003: 표준 출력 한국어 / 내부 코드값 영어 i18n 경계

- 상태: Accepted
- 날짜: 2026-11-02
- 관련 이슈/문서: `code_artifact.md` Task 9, [[CLAUDE.md]] §4.1 i18n 경계, [[GLOSSARY.md]] "표준 출력 vs 내부 코드값"

## 문제 상황 (Context)

이 포크의 산출물은 한국 증시 투자자가 읽는 것이므로 리포트가 한국어로 생성되는 것이 자연스럽다. 그러나 TradingAgents 는 리포트 끝 결정 라인을 **기계가 파싱** 한다:

- `tradingagents/agents/rating.py:34` — 정규식 `"Rating: X" / "rating - X" / "Rating — **X**"` 로 등급 추출.
- `tradingagents/agents/schemas.py:211` — `FINAL TRANSACTION PROPOSAL: **{action.value.upper()}**` 로 결정 라인 렌더링.
- `tradingagents/reporting.py:26` — `f"- Rating: {run_rating(final_state)}"` 로 요약에 재사용.
- `tradingagents/backtest.py` 등 다운스트림은 파싱된 영어 enum (`BUY`/`SELL`/`HOLD`) 에 의존 — 백테스트 평가, 리스크 라우팅, 메모리 로그 모두.

리포트 끝 결정 라벨과 값을 전부 한국어로 번역(`**등급**: 매수`) 하려면 파서, 렌더러, 모든 다운스트림의 enum 상수 처리를 재작성해야 한다. 반대로 전부 영어로 유지하면 (`**Rating**: BUY`) 리포트 끝에 영어 문단이 남아 "모든 사용자 노출 텍스트를 한국어로" 요구에 어긋난다.

중간 경계가 필요하다.

## 결정 (Decision)

**사용자가 보는 모든 텍스트는 한국어, 코드가 파싱하거나 enum 으로 처리하는 상수는 영어 유지.** 두 범주로 명확히 분리한다.

**표준 출력 (한국어):**
- 에이전트 생성 콘텐츠: 분석가 리포트, 리서처 토론, 디베이터 토론, 매니저/트레이더 결정 본문.
- CLI UI: 진행 메시지, 선택 프롬프트, Rich 콘솔 표/제목.
- 에러 메시지, 로그에서 사용자에게 노출되는 텍스트.
- `work_history/` 내용, 커밋 메시지, PR 설명.

**내부 코드값 (영어):**
- 거래 결정 enum: `BUY`, `SELL`, `HOLD`.
- CLI 플래그 이름: `--output-format`, `--permission-mode` 등.
- 환경변수 이름: `TRADINGAGENTS_LLM_PROVIDER`, `ANTHROPIC_API_KEY` 등.
- 코드 식별자: 함수명, 변수명, 파일명, 클래스명.
- 파서가 읽는 정규식 토큰 (BUY/SELL/HOLD 값 자체).

**혼합 케이스 — 리포트 결정 라인:**
- 포맷: `**등급**: BUY` 와 `**최종 거래 제안**: BUY` — 라벨은 한국어, 값은 영어.
- `tradingagents/agents/rating.py` 파서는 한국어 라벨 (`등급`, `최종 거래 제안`) 과 기존 영어 라벨 (`Rating`, `FINAL TRANSACTION PROPOSAL`) 모두 인식한다. BUY/SELL/HOLD 값 추출 로직은 변경하지 않는다.
- `tradingagents/agents/schemas.py` 와 `tradingagents/reporting.py` 의 렌더링 템플릿은 한국어 라벨을 사용한다.
- `tradingagents/agents/context.py` 의 `get_language_instruction()` 는 LLM 에 "라벨은 한국어, 값은 영어 그대로 유지" 를 명시 지시한다.

## 결과 (Consequences)

**긍정:**
- 사용자 산출물이 한국어로 통일되어 가독성 확보.
- 파서/백테스트/다운스트림 코드 변경 최소화 — 영어 enum 유지로 호환성 보존.
- i18n 경계가 명확해 미래 메인테이너가 "이 문자열을 번역해야 하나?" 판단이 쉽다 ("사용자가 보나? → 한국어" / "코드가 읽나? → 영어").
- 상류의 결정 라인 파서를 거의 그대로 재사용 — 유지보수 비용 감소.

**부정:**
- 리포트 끝 결정 라인이 혼합 언어 (`**등급**: BUY`) 로 보여 처음 보는 사용자에게는 어색할 수 있음.
- `rating.py` 파서가 영어/한국어 두 포맷을 모두 인식해야 하므로 정규식이 소폭 복잡해짐.
- LLM 이 지시를 어기고 값까지 번역 (`**등급**: 매수`) 하면 파싱 실패 → 재시도 필요.

**완화책:**
- 혼합 라인은 리포트 전체의 1~2줄만 차지. 본문은 완전 한국어라 체감 영향 미미.
- 파서의 두 포맷 인식 테스트를 Task 11 (`tests/test_rating*.py`) 에 추가해 회귀 방지.
- LLM 지시 어김은 `get_language_instruction()` 의 명시적 경고 문구와 `structured.py` 폴백으로 회복.

## 고려된 대안 (Alternatives Considered)

**(1) 결정 라벨/값 전부 영어 유지 (`**Rating**: BUY`)**
- 기각 사유: 리포트 끝에 영어 문단이 남아 "모든 표준 출력 한국어" 요구에 어긋남. 사용자가 원한 "다 한글로" 톤과 배치됨.

**(2) 결정 라벨/값 전부 한국어 번역 (`**등급**: 매수`)**
- 기각 사유: `rating.py` 파서, `schemas.py` 렌더러, `backtest.py` 평가 로직, 리스크 라우팅, 메모리 로그 등 다운스트림의 enum 처리를 전부 재작성해야 함. 변경 범위가 넓고 리스크 과다. 영어 상수 (`BUY`/`SELL`/`HOLD`) 는 TradingAgents 내부적으로 안정적인 contract 이므로 유지하는 것이 합리적.

**(3) `output_language` 가 Korean 일 때 자동 번역 레이어 삽입 (렌더링 시점에 enum → 한국어)**
- 기각 사유: 파싱/렌더링을 양방향 매핑으로 만들어야 함. 결정 라인에만 적용되는 특수 로직이 전역에 산재 → 복잡도 증가 대비 이점 적음.
