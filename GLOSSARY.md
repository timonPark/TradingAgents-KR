# GLOSSARY

TradingAgents-KR 포크 전용 도메인 용어집. 코드 식별자나 구현 세부가 아니라, 설계 대화에서 **의미가 서로 다른 개념**을 가리키는 용어들을 모읍니다.

---

## 티커 (Ticker) / 종목코드

한국거래소(KRX) 가 상장 종목에 부여하는 **6자리 숫자 식별자**. 보통주/우선주/ETF/ETN 모두 동일한 6자리 패턴 (`^\d{6}$`).

- 예: `005930` (삼성전자), `000660` (SK하이닉스), `005935` (삼성전자우)
- 상위 포크의 미국식 영문 티커(`AAPL`), 홍콩식(`0700.HK`), 상해식(`600519.SH`) 패턴은 이 포크에서 지원하지 않습니다.
- 심볼 정규화(`dataflows/symbols.py`) 의 Yahoo/HK/상해 변환 테이블은 삭제됩니다.

## 에이전트 분류 (Agent taxonomy)

TradingAgents 그래프의 노드는 다섯 종류로 나뉘고, 각 종류는 LLM 호출 비용/깊이가 다릅니다.

- **분석가 (Analyst)**: 재무·시세·뉴스·감성 네 종류. 데이터 수집과 1차 분석. 이 포크에서는 [[사전조회 패턴]] 으로 Python 이 데이터를 미리 조회해 프롬프트에 주입합니다 — LLM 이 툴을 호출하지 않습니다.
- **리서처 (Researcher)**: Bull / Bear 두 종류. 분석가 산출물을 모아 매수/매도 논거를 토론합니다.
- **디베이터 (Debator / Risk)**: Aggressive / Conservative / Neutral 세 종류. 리서처 산출물을 기반으로 리스크 관점에서 재토론.
- **매니저 (Manager)**: Research Manager (토론 종결), Portfolio Manager (포지션 결정).
- **트레이더 (Trader)**: 최종 거래 제안 생성.

## 추론 티어 (Thinking tier)

LLM 호출 깊이를 두 단계로 나눈 구분. 어댑터가 티어별로 다른 모델/effort 를 사용합니다.

- **깊은 추론 (Deep think)**: 리서처·디베이터·매니저·트레이더. 디폴트는 `sonnet` + `--effort high`.
- **빠른 추론 (Quick think)**: 분석가 (사전조회 데이터로 보고서 작성). 디폴트는 `haiku` + `--effort medium`.

## 사전조회 패턴 (Pre-fetch pattern)

이 포크의 핵심 설계 패턴. LLM 이 툴 콜로 데이터를 가져오는 전통적 흐름 대신, **분석가 노드 진입 전에 Python 이 필요한 모든 데이터를 미리 조회해 프롬프트에 주입**합니다.

- 대안이었던 "MCP 서버 브리지" 는 Claude Code 헤드리스의 subprocess 비용 때문에 포기했습니다 ([[ADR-0002]] 참조).
- 분석가당 LLM 호출이 **3~5회 → 1회** 로 감소합니다.
- 반대 급부: LLM 이 "어떤 지표를 뽑을지" 동적으로 선택하지 못합니다 — 고정 메뉴만 주어집니다.

## 헤드리스 LLM 어댑터 (Headless LLM adapter)

Claude Code CLI 를 subprocess 로 호출해 LangChain `BaseChatModel` 인터페이스로 포장한 어댑터. 외부 API SDK 를 통한 provider 추상화는 이 포크에서 전부 제거됩니다 ([[ADR-0001]] 참조).

- 입력: LangChain messages → `claude -p "..." --output-format json`
- 출력: JSON 파싱 → LangChain `AIMessage`
- 구조화 출력(`with_structured_output`): `--json-schema` 로 매핑
- 툴 바인딩(`bind_tools`): 지원하지 않음 (`NotImplementedError`). [[사전조회 패턴]] 으로 우회.

## 표준 출력 vs 내부 코드값 (Standard output vs internal code value)

i18n 경계를 정의하는 이원 구분.

- **표준 출력**: 사용자가 보는 모든 텍스트 — 에이전트 리포트 본문, CLI UI 메시지, 진행 메시지, 에러 메시지. **한국어** 로 생성/표기.
- **내부 코드값**: 코드가 파싱하거나 enum 으로 처리하는 상수 — 거래 결정(`BUY`/`SELL`/`HOLD`), CLI 플래그 이름, 환경변수 이름, 코드 식별자. **영어** 유지.
- 혼합 케이스: [[최종 결정 라벨]] (라벨·화면 값은 한국어, 내부 값은 영어 — ADR-0004).

## 최종 결정 라벨 (Final decision label)

리포트의 **기계 판독용 결정 라인**. 라벨과 화면 값은 한국어, 내부 값은 영어 (ADR-0004).

- `**등급**: BUY/SELL/HOLD` — `tradingagents/agents/rating.py` 가 파싱.
- `**최종 거래 제안**: BUY/SELL/HOLD` — `tradingagents/agents/schemas.py` 가 렌더링.
- 화면 표기: 매수/비중 확대/보유/비중 축소/매도 (`rating.py::display_rating`). 파서가 한국어 표기를 내부 값(`Buy`/`Overweight`/`Hold`/`Underweight`/`Sell`)으로 되돌리므로 백테스트·메모리 로그 등 다운스트림은 영어 값을 그대로 쓴다.

## Max 플랜 쿼터 (Max plan quota)

이 포크의 LLM 결제 모델. Anthropic Max/Pro 구독에 포함된 Claude Code 사용 쿼터로 추론을 수행합니다. 토큰 종량제 API 결제는 사용하지 않습니다.

- [[헤드리스 LLM 어댑터]] 의 세마포어(`TRADINGAGENTS_CLAUDE_CONCURRENCY`, 디폴트 2) 가 쿼터 소진 속도를 제어합니다.
- 429 응답 시 60초 대기 후 1회 재시도, 그 뒤 명확히 실패 전파.

## 하드 포크 (Hard fork)

`TauricResearch/TradingAgents` 상류 추적을 포기하는 포크 전략. provider 추상화·미사용 vendor 코드·관련 pyproject 의존성을 전면 삭제합니다. 상류의 신규 기능/버그 수정은 자동으로 받지 않습니다.

## 회사 개요 (Company overview)

보고서 맨 앞 섹션. 회사명·시장·대표이사·설립일과 DART 사업보고서 "사업의 개요" **원문 발췌**를 출처와 함께 보여줍니다. 모델이 쓴 글이 아니라 조회한 공시를 그대로 옮긴 것이라 지어낸 내용이 들어갈 수 없습니다 (`dart.get_business_overview` → `fundamentals_data["business"]` → `report_html.company_overview_html`).

- 재무 분석가에게도 같은 발췌를 근거 자료로 주입하고, 발췌에 없는 사업 내용은 학습 지식으로 채우지 못하게 지시합니다.
- 공시를 못 구하면 "회사 개요 없음 — 사유"로 표시합니다 (추정하지 않음).

## 소속 테마 (Company theme)

회사 개요 섹션의 "소속 테마" 블록 (#165). 투자자가 종목을 묶어 부르는 이름(예: 바이오 플랫폼)이며, 모델이 사업 개요 발췌에서 고르되 **각 테마마다 발췌에서 그대로 옮긴 근거 문장**을 함께 내야 합니다. 코드가 그 문장이 발췌에 실제로 있는지 검사해 확인되지 않는 테마는 버립니다 (최대 3개). 근거가 없으면 "확인되지 않음 — 사유"로 표시합니다 (`company_themes.extract_themes` → `fundamentals_data["themes"]`). 테마 이름은 모델이 붙인 것이고, 인용문만 원문임이 보증됩니다.

## 현재 핵심 이슈 (Key issues)

회사 개요 섹션의 "현재 핵심 이슈" 블록 (#166). 뉴스 분석가가 사전조회한 종목 뉴스 헤드라인(N1..)과 DART 최근 30일 공시 제목(D1..)에 번호를 붙여 모델에 주고, 이슈마다 **근거 번호와 그 제목에서 그대로 옮긴 인용구**를 내게 합니다. 코드가 번호의 실재와 인용구의 일치를 검사해 통과한 이슈(최대 3개)만 싣고, 출처의 제목·링크는 모델이 아니라 **조회한 데이터**에서 붙입니다. 이슈 제목·요약 문장은 모델이 쓰므로 기계 검증되지 않고, 출처와 대조해 읽는 용도입니다 (`company_issues.extract_issues` → `company_issues` 상태 키). 근거가 없으면 "확인되지 않음 — 사유".
