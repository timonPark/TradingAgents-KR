# [#139] 투자자별 수급 — KRX 로그인 세션 + 네이버 증권 폴백 (2단계)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/139
- PR: (작성 후 기입)
- 브랜치: feat/139-krx-login-investor-flow
- 작업 기간: 2026-11-05 ~ 2026-11-05

## 문제

1단계(PR #142)는 수급 조회 실패를 "조회 불가"로 명시하기만 했다. 수급 데이터 자체는 여전히 못 가져왔다.
KRX 는 투자자별 거래실적에 **로그인**을 요구한다. 로그인을 지원하는 pykrx 1.2.x 는 `pandas<3.0` 을 요구해 이 프로젝트(pandas 3)에 설치할 수 없다.

## 수행한 변경

- `tradingagents/dataflows/vendors/krx_session.py` 신규 — `KRX_ID`/`KRX_PW` 로 data.krx.co.kr 에 로그인(pykrx 1.2.9 `auth.py` 와 동일 흐름)하고, pykrx 1.0.x `webio` 의 모듈 전역 `requests` 를 로그인 세션 shim 으로 바꿔 끼운다(`authenticated_pykrx()` 컨텍스트, 락 직렬화, 종료 시 복원).
  - 계정 잠금 방지: 수급을 실제 조회할 때만 로그인, 자격증명 **거부**는 프로세스 안에서 기억하고 재시도하지 않음, 네트워크 오류는 기억하지 않음, 비밀번호·쿠키는 로그·예외에 넣지 않음. CD011(중복 로그인)은 `skipDup=Y` 로 1회 재전송.
  - shim 은 `http://` → `https://` 로 올려 보낸다. pykrx 1.0.x 가 `http://` 로 요청하면 KRX 가 301 로 넘기면서 POST 가 GET 으로 바뀌어 HTML 이 돌아온다 — 이것이 로그인 후에도 `KeyError: '거래대금'` 이 났던 원인.
- `tradingagents/dataflows/vendors/naver_investor.py` 신규 — 네이버 증권 `m.stock.naver.com/api/stock/{ticker}/trend` (최근 10거래일, 주 단위) 폴백. 기준일 이후 행 제외, 실패는 `VendorUnavailableError`.
- `tradingagents/dataflows/vendors/pykrx.py` — 수급 조회 순서: KRX 로그인 세션 → 네이버 증권 → 두 원인을 담은 "조회 실패(수급 추정 금지)" 메시지.
- **조회 창 버그 수정** — 기존에는 "최근 N 거래일"이라고 표기하면서 약 2N+10 달력일 구간을 합산했다. `_window_start()` 가 `krx_calendar` 로 정확히 N 거래일 전을 시작일로 잡는다(캘린더 실패 시 평일 기준 대체). 과거 보고서의 "최근 5거래일 순매수" 수치도 이 영향을 받았을 수 있다.
- 테스트: `tests/test_krx_session.py`, `tests/test_naver_investor_vendor.py` 신규, `tests/test_pykrx_vendor.py` 수급 테스트 재작성.

## 설계 결정 변경 사항

없음. (pykrx 를 1.2.x 로 올리는 대신 1.0.x 위에 로그인 세션을 얹었다 — pandas 3 호환 유지)

## 검증 결과

- `pytest` 전체 — 998 passed, 13 deselected(integration)
- `ruff check tradingagents cli tests` — 통과
- 실호출(integration): `test_live_login_and_investor_table` — KRX 로그인 + 투자자별 표 조회 통과 (로그인 성공, 거부 없음)
- 실호출(integration): `naver_investor.get_investor_flow("001210", ...)` — 5거래일 표 정상

## 다음 작업 핸드오프

- 한 프로세스에서 같은 KRX 계정으로 다른 곳에 이미 로그인돼 있으면 CD011 로 기존 세션을 끊는다(`skipDup=Y`). 운영 시 참고.
- 수급 외 데이터(공매도 등)도 로그인이 필요해졌다면 `authenticated_pykrx()` 로 같은 방식 적용 가능.
- DART 공시 → 뉴스 분석가(대량보유·임원지분·CB), 주요뉴스(글로벌 뉴스) 복구는 별도 이슈.
