# [#199] claude 헤드리스 어댑터 실패 시 stderr 없이 프롬프트 전체가 오류 메시지에 들어감

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/199
- PR: https://github.com/timonPark/TradingAgents-KR/pull/203
- 브랜치: fix/199-adapter-error-message
- 작업 기간: 2026-11-26

## 수행한 변경

- `tradingagents/llm_clients/claude_code_client.py`
  - `_run_claude_subprocess`: `CalledProcessError`(재시도 후)·`TimeoutExpired` 를
    `RuntimeError` 로 바꿔 전파. 원 예외는 `from None` 으로 체인에서 끊는다
    (원 예외의 `str()` 이 명령줄 전체 = 프롬프트를 담기 때문).
  - `_tail`, `_describe_cli_output` 신규: stderr 끝부분 + stdout JSON 의
    `result`/`api_error_status`/`terminal_reason`/`subtype` (JSON 이 아니면 stdout
    끝부분) 을 각 500자 상한으로 요약.
  - 오류 처리 정책 주석에 macOS 잠자기와 타임아웃 관계, 예외 변환 정책 추가.
- `tests/test_claude_code_client.py`
  - 기존 2건 기대 예외를 `RuntimeError` 로 갱신 (non-zero exit 전파, 타임아웃 전파).
  - 신규 4건: 프롬프트 제외·원인 포함·예외 체인 차단, stderr 끝부분만 유지,
    JSON 이 아닌 stdout, 타임아웃(bytes 부분 출력) 메시지.

## 설계 결정 변경 사항

- **타임아웃은 변경하지 않음.** 이슈는 "가능하면 타임아웃을 두어 13시간 같은 무한
  대기를 막는다" 를 제안했지만, 조사 결과 타임아웃은 정상 동작 중이었다.
  - `pmset -g log`: 분석 시작(11-19 17:54) 3분 뒤 17:57:47 `Clamshell Sleep`,
    실패 시각 11-20 06:40:00 은 `DarkWake ... wifibt` (잠깐 깨어난 순간) 와 일치.
  - 이 환경의 Python 3.15 `time.monotonic` 은 `mach_absolute_time()` 이며, 시스템
    잠자기 중에는 진행하지 않는다. `subprocess.run(timeout=...)` 은 이 시계를 쓰므로
    잠든 시간은 타임아웃에 포함되지 않는다. 13시간 대부분은 잠든 시간이었다.
  - 벽시계 기준 타임아웃으로 바꾸면 깨어난 직후 진행 중이던 호출을 모두 죽이게 되어
    이득이 없다고 판단. 잠든 동안 프로세스도 멈춰 있으므로 현 동작이 타당하다.
- **예외 타입 변경**: `CalledProcessError`/`TimeoutExpired` → `RuntimeError`.
  저장소 안에서 두 예외를 잡는 호출부는 없음 (`grep` 확인). 쿼터·`is_error` 경로도
  이미 `RuntimeError` 를 쓰고 있어 일관된다.

## 검증 결과

- `pytest tests/test_claude_code_client.py` — 81 passed (신규 테스트는 구현 전 6 failed 확인)
- `pytest` 전체 — 1294 passed
- `ruff check tradingagents cli tests` — 통과
- 수동 smoke: 존재하지 않는 모델로 실제 `claude -p` 실패 유도 → 메시지 365자,
  프롬프트 미포함, 원인 표시:
  `claude -p 실패 (종료 코드 1, 1회 재시도 후) — stderr: [claude-code:unrecognized_model] ... / 응답: result="There's an issue with the selected model ...", api_error_status='404', terminal_reason='api_error', ...`
- 웹 UI 검증 (Aside, 2026-11-26):
  - 타임아웃 경로: 백엔드를 `TRADINGAGENTS_CLAUDE_TIMEOUT=1` 로 띄우고 UI 에서 005930 /
    2026-11-25 / 뉴스 분석가 / low 실행 (run `dd135c04e59e`).
    - `GET /api/runs/{id}` 의 `error`: `claude -p 가 1초 안에 끝나지 않아 중단했습니다 — 출력 없음` (39자)
    - SSE `error` 이벤트의 `message`·`traceback` 에 프롬프트 없음, 원 예외 체인 없음
  - 종료 코드 1 경로: API 로 `deep/quick_think_llm=no-such-model-xyz` 실행 (run `2bd17dba0f36`).
    실행 시작 시 메모리 정산(reflection) 단계의 백엔드 로그에 새 메시지 확인
    (`... 종료 코드 1 ... unrecognized_model ... api_error_status='404' ...`). 정산 대기
    299건을 모두 실패 처리해야 메인 노드에 닿아 30분 이상 걸리므로 실행은 취소했다.
    정산 실패 항목은 pending 으로 남아 메모리 로그 손상 없음.
  - **화면 표시는 확인되지 않음 — 기존 UI 버그**: 화면에는 어댑터 메시지 대신
    `에러: SSE 연결 끊김 — uvicorn 이 켜져 있는지 확인하세요.` 가 표시됐다.
    `web/src/components/RunPanel.tsx` 가 서버의 `error` 이벤트를 처리한 직후,
    같은 이벤트에 `source.onerror` 도 호출되어 메시지를 덮어쓴다. 브라우저에서
    확인: 서버 `error` 이벤트(MessageEvent, data 있음) 한 건에 리스너와 `onerror`
    가 모두 호출됨. #199 이전부터 있던 문제로 범위 밖 (새 이슈 후보).

## 위험도 (§4.8): risk:high

- 파급 범위: 모든 LLM 호출이 이 경로를 지난다 — 해당
- 변경 주기: Task 1e 이후 오래 안정적이던 핵심 어댑터 — 해당
- 민감도: LLM 어댑터 호출 경로 — 해당
- 단, 성공 경로와 재시도 정책은 손대지 않았고 실패 시 예외 타입·메시지만 바뀐다.

## 다음 작업 핸드오프

- 새 이슈 후보 (UI): 실행 실패 시 화면이 실제 오류 대신 "SSE 연결 끊김" 을 표시.
  서버 이벤트 이름 `error` 가 `EventSource.onerror` 와 겹친다. `onerror` 에서
  `MessageEvent` 를 무시하거나, 서버 이벤트 이름을 바꾸는 방법이 있다.

- 새 이슈 후보: exit 1 과 함께 stdout JSON 에 `api_error_status=429` 가 오면 현재는
  `CalledProcessError` 경로(즉시 재시도)로 가서 60초 대기 쿼터 재시도 정책이 적용되지
  않는다. 실제 쿼터 소진 시 CLI 의 종료 코드를 확인한 뒤 판단 필요.
- 노트북 덮개를 닫으면 분석이 잠자기와 함께 멈춘다. 장시간 분석은 `caffeinate -i`
  같은 방법으로 잠자기를 막는 안내를 README 트러블슈팅에 둘지 검토 (#185 재실행 시 참고).
