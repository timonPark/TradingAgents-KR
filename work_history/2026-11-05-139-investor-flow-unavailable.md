# [#139] 투자자별 수급 조회 실패 원인 표시 (1단계: 조회 불가를 명시)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/139 (이 PR 로 닫지 않음 — 2단계 남음)
- PR: https://github.com/timonPark/TradingAgents-KR/pull/142
- 브랜치: fix/139-investor-flow-unavailable
- 작업 기간: 2026-11-05 ~ 2026-11-05

## 문제

투자자별 수급 조회가 실패하는데 보고서에는 `[KRX 수급 조회 실패: '거래대금']` 같은 파서 내부 예외만 나와 원인을 알 수 없었음. 또 `KRX_ID`/`KRX_PW` 사전 검사는 pykrx 1.0.51(로그인 코드 없음)에서는 효과가 없는데도 "자격증명이 없습니다" 안내를 내보내 오해를 줌.

조사 결과 (이슈 #139 본문에 기록):
- 이 프로젝트의 pykrx 는 1.0.51 — KRX 로그인 미지원. 1.2.x 는 로그인을 지원하지만 `pandas<3.0` 을 요구해 설치 불가.
- 읽기 전용 호출: OHLCV 정상, `get_market_trading_value_by_investor` → `KeyError: '거래대금'`.

## 수행한 변경

- `tradingagents/dataflows/vendors/pykrx.py` — `_pykrx_supports_login()`·`_pykrx_version()`·`_diagnose_investor_failure()` 추가. 실패 시 원인(설치된 pykrx 버전이 로그인을 지원하지 않음)을 설명하고 "수급 데이터 없음. 수급을 추정하거나 언급하지 마세요" 를 덧붙임. 로그인 미지원 pykrx 에서는 `KRX_ID`/`KRX_PW` 사전 검사를 하지 않음
- `tradingagents/agents/analysts/market_analyst.py` — 프롬프트: 수급 섹션이 조회 실패면 수급을 추정하지 말고 보고서에 명시, 수급 의존 결론의 신뢰도 하향
- `tradingagents/agents/tools.py` — 도구 설명 갱신
- `tests/test_pykrx_vendor.py` — 진단 메시지, 로그인 미지원 시 사전 검사 생략, 로그인 지원 시 원본 메시지 유지, 지원 여부 감지 테스트 추가

## 설계 결정 변경 사항

없음. (Task 6c 수급 선조회는 유지, 실패 표시만 개선)

## 검증 결과

- `pytest` 전체 — 970 passed
- `ruff check tradingagents cli tests` — 통과
- 실제 호출(이 환경, pykrx 1.0.51): `[KRX 수급 조회 실패: KeyError: '거래대금'. 설치된 pykrx 1.0.51 는 KRX 로그인을 지원하지 않는데 KRX 가 투자자별 수급 조회에 로그인을 요구해, 응답 형식이 달라진 것으로 보입니다 (#139) — 수급 데이터 없음. 수급을 추정하거나 언급하지 마세요]`

## 다음 작업 핸드오프

- #139 2단계: `KRX_API_KEY`(KRX Open API)로 투자자별 수급을 받을 수 있는지 읽기 전용으로 확인. 가능하면 별도 PR 로 수급 구현, 불가하면 이 상태 유지.
- 에이피위성 보고서의 `IncompleteRead` 는 이번에 재현한 `KeyError` 와 오류 형태가 달라 같은 원인인지 미확인.
- pykrx 1.2.x 업그레이드는 pandas 2.x 다운그레이드가 필요해 보류. 올릴 경우 자동 로그인/재시도로 인한 계정 잠금 방지 대책 필요.
