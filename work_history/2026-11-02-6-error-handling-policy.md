# [#6] Task 1e: 오류 처리 정책 (타임아웃·재시도·429)

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/6
- PR: (작업 완료 후 추가)
- 상위 에픽: #1
- 브랜치: `feat/6-error-handling-policy`
- 작업 기간: 2026-11-02 ~

## 범위

Claude Code subprocess 호출의 실패 모드별 정책을 구현합니다. 그릴링 라운드 6 (Q8) 에서 결정된 "권장 조합" 반영:

| 실패 모드 | 대응 |
|---|---|
| 타임아웃 | effort 레벨 기반 가변 디폴트. 환경변수 `TRADINGAGENTS_CLAUDE_TIMEOUT` 로 오버라이드. 재시도 없음 |
| non-zero exit (CalledProcessError) | 1회 재시도 후 전파. 일시적 네트워크 오류 흡수 |
| 429 / 쿼터 초과 | 60초 대기 후 1회 재시도. 2회째 실패 시 "Max 플랜 쿼터 소진" 메시지와 함께 RuntimeError 전파 |
| JSON 파싱 실패 | 재시도 없이 전파 (JSONDecodeError). `structured.py` 폴백 처리 |

## 수행한 변경

### `tradingagents/llm_clients/claude_code_client.py`

- `_EFFORT_TIMEOUTS` 신규: effort 레벨 (`low/medium/high/xhigh/max`) → 초 단위 타임아웃 매핑 (`180/300/600/900/1200`).
- `_resolve_timeout(effort)` 신규: 환경변수 `TRADINGAGENTS_CLAUDE_TIMEOUT` 가 설정되어 있으면 그 값, 아니면 effort 기반 디폴트. 환경변수가 양의 정수가 아닐 경우 `ValueError` 로 명확히 실패.
- `_is_quota_error(payload)` 신규: 429 쿼터 초과 판정. 두 가지 지표 중 하나로 식별:
  - `api_error_status == 429`
  - `subtype` 에 "rate"/"quota"/"limit" 포함 (예: `rate_limit_exceeded`)
  - `is_error` 플래그가 True 일 때만 쿼터로 간주 (false positive 방지)
- `_run_claude_subprocess(args, timeout)` 재작성:
  - `timeout` 파라미터 신규 추가, `subprocess.run(..., timeout=timeout)` 로 전달.
  - 세마포어 `with` 블록 **안쪽에서** `for attempt in range(2)` 재시도 루프 — 재시도 중 다른 호출이 쿼터를 밀어내지 못하도록 (Task 1d 핸드오프 노트 반영).
  - CalledProcessError: 첫 시도 실패 시 `continue`, 두 번째도 실패하면 전파.
  - 429 응답: 첫 시도에서 `time.sleep(60)` 후 재시도, 두 번째도 429 면 `"Max 플랜 쿼터 소진"` RuntimeError.
  - 일반 `is_error` 응답: 즉시 RuntimeError 전파.
  - 타임아웃/JSON 파싱 실패는 자동 재시도 없이 바로 전파 (각각 `TimeoutExpired`, `JSONDecodeError`).
- `ChatClaudeCodeHeadless.effort: str = "medium"` 필드 추가 (Pydantic 필드). Task 1e 에서는 타임아웃 산정에만 쓰이고 Task 1f (#7) 에서 `--effort` CLI 플래그 연계 + 티어별 매핑이 추가됨.
- `_generate` 와 `_StructuredClaudeCode.invoke`: `_run_claude_subprocess(args, timeout=_resolve_timeout(self.effort))` 로 호출. structured 경로는 `self._llm.effort` 로 접근.

### `tests/test_claude_code_client.py`

- 기존 Task 1d 세마포어 테스트 2개를 timeout 파라미터 추가로 업데이트 (`_run_claude_subprocess(["claude", "-p", "x"], 300)`).
- Task 1e 테스트 20개 추가:
  - `_resolve_timeout`: 디폴트 medium, 5개 effort 레벨, 알 수 없는 effort → medium 폴백, 환경변수 오버라이드, 환경변수 유효성 검증 2개
  - `_is_quota_error`: 429 status, rate_limit subtype, quota subtype, 일반 에러 무시, `is_error=False` 는 쿼터 아님
  - `_run_claude_subprocess` timeout 전달
  - `_generate` effort 기반 타임아웃
  - `_generate` 환경변수가 effort 보다 우선
  - 비정상 종료 재시도 성공 / 재시도 후도 실패 전파
  - 타임아웃 전파 (재시도 없음)
  - JSON 파싱 실패 전파 (재시도 없음)
  - 429 대기 후 재시도 성공 (`time.sleep` 모킹으로 실제 60초 대기 없음)
  - 429 반복 시 한국어 메시지 포함 RuntimeError

## 설계 결정 변경 사항

없음. 그릴링 Q8 의 권장 조합 그대로.

**세마포어 안쪽에서 재시도 루프를 돌리는 이유:** 재시도 중에 세마포어를 놓으면 다른 호출이 쿼터를 밀어내 재시도 성공률이 낮아짐. 재시도가 끝나거나 실패할 때까지 하나의 "작업" 으로 간주하는 것이 쿼터 관리 측면에서 자연스러움.

**`effort` 필드를 Task 1e 에서 미리 도입:** Task 1f (#7) 가 티어별 effort 를 config 에서 주입하지만, Task 1e 는 **타임아웃 계산에 effort 가 필요** 하므로 지금 필드만 선도입. CLI `--effort` 플래그 전달은 Task 1f 에서 추가.

## 검증 결과

- `pytest tests/test_claude_code_client.py -v` → **55 passed in 0.93s**
  - Task 1a 9 + Task 1b 13 + Task 1c 5 + Task 1d 8 + Task 1e 20 = 55
- `ruff check` → **All checks passed**
- `time.sleep` 과 `subprocess.run` 모두 모킹해 테스트가 실제 60초를 기다리지 않도록 함.

## 다음 작업 핸드오프

Task 1f (#7) 모델 티어 매핑 + `--effort` CLI 플래그 전달.
- 현재 `effort` 필드는 Pydantic 필드로 존재하지만 CLI 로 전달되지 않음. Task 1f 에서 `_base_cli_args` 에 `--effort <level>` 추가.
- `TRADINGAGENTS_DEEP_THINK_LLM`, `TRADINGAGENTS_QUICK_THINK_LLM`, `TRADINGAGENTS_EFFORT`, `TRADINGAGENTS_QUICK_EFFORT` config 키 매핑은 `tradingagents/llm_clients/factory.py` 의 `create_tier_client` 와 `build_llm_kwargs` 에서 처리.
