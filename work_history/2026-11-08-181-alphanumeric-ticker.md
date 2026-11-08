# [#181] 영숫자 종목코드(0126Z0 등)를 분석할 수 있게 하기

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/181
- PR: https://github.com/timonPark/TradingAgents-KR/pull/182
- 브랜치: feat/181-alphanumeric-ticker
- 작업 기간: 2026-11-08

## 수행한 변경

- `tradingagents/dataflows/symbols.py`: 종목코드 규칙을 상수 `KRX_TICKER_PATTERN = ^[0-9A-Z]{6}$` 로 한 곳에 정의. `validate_krx_ticker`(CLI `--ticker`)가 이 상수를 쓰고 안내 문구를 바꿨다.
- `api/routes/runs.py`: `RunCreate.ticker` 검증이 같은 상수를 쓴다 → `/openapi.json` 의 패턴이 `^[0-9A-Z]{6}$` 로 바뀌어 클라이언트가 읽고 판단할 수 있다.
- `api/reports_store.py`: 보고서 번호 패턴을 영숫자 코드로 넓힘. 이전에는 영숫자 코드의 보고서가 목록·열람에서 빠졌다.
- `tradingagents/dataflows/krx_symbol_search.py`: 코드 정확 매칭이 같은 상수를 쓴다. 코드 모양인데 일치하는 코드가 없으면(숫자 코드는 제외) 종목명 검색으로 넘어간다 — `DOOSAN` 같은 6자 대문자 영문 종목명이 이름으로 안 찾아지는 것을 막기 위함.
- `cli/prompts.py`: 대화형 입력에서 영숫자 코드를 코드로 인식(`_is_ticker_code`). 숫자가 하나도 없는 6자 대문자(`DOOSAN`)는 코드가 아니라 종목명 검색으로 보낸다.
- `tradingagents/dataflows/vendors/dart.py`: `_dart_company(ticker)` 추가, DART 호출 8곳이 이것을 거친다. 영숫자 코드는 DART 코드표(`corp_codes`)에서 8자리 `corp_code` 로 바꿔 넘긴다.
- 문구: `api/models.py`, `api/routes/symbols.py`, `cli/selections.py`, README, `web/src/pages/index.astro`, `portfolio.py`·`cli/prompts.py` 주석에서 "6자리 숫자"라고 틀리게 말하던 곳. `GLOSSARY.md` 의 티커 항목.
- 테스트: `tests/test_alphanumeric_ticker.py` 신규(32). 기존 `tests/test_api_reports.py`(2곳)·`tests/test_api_runs.py`(1곳)는 "잘못된 코드" 예시로 `ABCDEF` 를 썼는데 이제 형식상 유효하므로 소문자 `abcdef` 로 바꿨다 (`test_api_runs.py` 쪽은 그대로 두면 실제 분석이 시작될 수 있다).

## 설계 결정 변경 사항

`code_artifact.md` 와 달라진 지점 없음. 이슈가 열어 둔 부분을 아래처럼 정했다.

- **대문자만 받는다** (`^[0-9A-Z]{6}$`, 이슈가 제안한 규칙 그대로). 소문자를 대문자로 바꿔 받지 않는 이유: 보고서 폴더명과 같은 종목·기준일 중복 실행 막기(#172) 키에 대소문자가 섞이는 것을 막고, 이슈가 krx-screener 전종목 목록에서 본 영숫자 코드도 전부 대문자다.
- **"숫자가 하나는 있어야 한다"는 규칙은 공통 규칙에 넣지 않았다.** 상장 2,876종목(영숫자 98개)이 전부 숫자를 포함하지만(2026-11-08 FDR 목록), KRX 가 이를 문서로 보장하는지는 확인하지 못했다. 이 가정은 종목명과 코드를 가려야 하는 CLI 대화형 입력(`_is_ticker_code`)에서만 쓴다. 틀려도 그 코드는 이름 검색으로 가고 `--ticker` 플래그로는 입력된다.
- **DART 는 라이브러리를 고치지 않고 호출 쪽에서 `corp_code` 로 바꾼다.** OpenDartReader `find_corp_code` 는 숫자가 아닌 문자열을 회사명으로 보는데, 이 컴퓨터에 설치된 0.3+ 만 코드를 읽어 확인했다 (`dart.py` 주석대로 py3.13 미만 환경에 깔리는 0.2.x 는 확인하지 못함). 호출 쪽에서 8자리 숫자 `corp_code` 를 넘기면 라이브러리 구현과 무관하게 같은 경로를 탄다. 숫자 코드는 그대로 넘기므로 기존 동작이 바뀌지 않는다.

## 검증 결과

- `pytest` 1282 passed (25 deselected), `ruff check tradingagents cli tests api` 통과. 새 테스트는 구현 전 실패(red) 확인.
- **변이 검사:** DART 변환 제거 / 보고서 번호 숫자만 / 검색 폴백 제거 / CLI 숫자 가드 제거 / API 패턴 숫자만 / 공통 규칙 숫자만 — 6개를 각각 되돌렸을 때 모두 새 테스트가 실패했다.
- **데이터 공급자를 실제로 호출해 확인** (LLM 쿼터를 쓰지 않는 조회만, `0126Z0`·`0088M0`·`00680K`):
  - pykrx 시세·투자자 수급: 세 코드 모두 정상.
  - 네이버 투자자 수급: 세 코드 모두 정상. 네이버 뉴스: `0126Z0`·`0088M0` 정상, `00680K` 는 "해당 기간 뉴스가 없습니다".
  - DART (수정 전): 세 코드 모두 `could not find` — 코드표(`corp_codes`)에 `0126Z0`·`0088M0` 는 있는데 라이브러리가 회사명으로 오인한 것이 원인.
  - DART (수정 후): `0126Z0`(삼성에피스홀딩스, KOSPI)·`0088M0`(메쥬, KOSDAQ) 의 기업 개황·최근 공시·사업 개요가 조회된다. `00680K` 는 DART 코드표에 없어(우선주는 별도 회사가 없다) 공시·재무가 "조회 실패"로 표시된다 — 숫자 우선주 `005935` 도 지금 똑같다 (이번 변경의 회귀가 아님). 지어내지 않는다.
  - 재무제표: `0088M0` 는 연결 재무제표 조회가 전부 "조회된 데이타가 없습니다"여서 재무 섹션이 비는 경우가 있다 (신규 상장 종목의 일반적 모습이고 DART 쪽 데이터 문제).
- `POST /api/runs` 로 영숫자 코드를 실제 분석까지 돌려 보지는 않았다 (LLM 쿼터 사용). 요청 검증과 run 생성은 테스트로, 데이터 조회는 위 호출로 확인했다.

## 다음 작업 핸드오프

- 실행 중인 서버는 재시작해야 새 규칙이 `/openapi.json` 에 나온다. krx-screener 는 재시작 후 `RunCreate.ticker` 패턴이 `^[0-9A-Z]{6}$` 로 바뀐 것을 읽고 영숫자 종목을 보낼 수 있다.
- 실제 분석 1건(예: `0088M0`)으로 끝까지 도는지 확인하는 것은 쿼터가 드는 일이라 사용자 판단에 맡긴다.
- 관찰 (이 PR 과 무관, 고치지 않음): 이전에 기록한 `_ALLOWED_FOLDERS` 폴더명 불일치, 웹 `RunPanel` 의 `cancelled` 처리는 여전히 후속 이슈 후보.
- 관찰: `vendors/pykrx.py`·`naver_news.py` 의 주석 일부("6자리 종목코드")는 길이만 말해 여전히 맞아 그대로 두었다.
