# [#134] Fix: Claude 어댑터 `--permission-mode plan` 제거 → `--tools ""`

- 이슈: https://github.com/timonPark/techTradingAgents-KR/issues/134
- 브랜치: `fix/134-adapter-plan-mode`
- 작업 기간: 2026-11-04

## 치명적 결함

Claude Code 어댑터가 `--permission-mode plan` 로 돌아서 모든 LLM 응답이 **"분석 보고서는 위 본문에 전달했습니다. 플랜 파일도 생성하였으며, 코드 변경은 없는 read-only 분석 작업입니다."** 같은 **plan 메타 요약** 으로 돌아옴.

결과: 모든 분석가/리서처/트레이더/매니저가 **쓸모없는 메타 텍스트** 만 생성. Portfolio Manager 가 이런 요약 기반으로 Underweight 같은 결정을 내리므로 판단 근거 자체가 부실. 지금까지 Task 14 전체가 사실상 unusable.

## 원인

Plan 모드는 "Claude 가 뭘 할지 제안" 하는 용도. 분석 보고서 작성에는 완전히 부적합. JSON 응답 `result` 필드에는 plan 요약만 담기고 실제 본문은 안 나옴.

## 수정

`tradingagents/llm_clients/claude_code_client.py` `_base_cli_args`:
- `"--permission-mode", "plan"` **제거**
- `"--tools", ""` **추가** — 모든 built-in 툴 (Bash/Write/Edit/NotebookEdit/WebFetch/ExitPlanMode 등) 비활성화

이로써:
- 호스트 파일 수정, Bash 실행, 웹 접근 전부 차단 (기존 plan 모드의 안전성과 등가)
- Claude 가 응답 본문에 **분석 보고서를 직접** 씀
- `payload["result"]` 가 실제 분석 본문

## 라이브 검증

```python
from tradingagents.llm_clients.claude_code_client import ChatClaudeCodeHeadless
from langchain_core.messages import HumanMessage

llm = ChatClaudeCodeHeadless(model="haiku", effort="low")
result = llm.invoke([HumanMessage(content="...시장 분석 보고서 작성...")])
print(result.content)
```

응답 (1084자):
```
# 삼성전자(005930) 기술적 분석 보고서

## 1. 추세 판정: 강세(Uptrend)
현재가(85,000원)이 5일 이평(83,200원)과 20일 이평(81,500원)을 모두 상회...

## 2. 지지·저항선
| 레벨 | 유형 | 의의 |
|------|------|------|
| 81,500원 | 지지선 | 20일 이평 |
...

## 3. 리스크 요인
① 과매수 구간 진입 경고 (RSI 62...)
② 이평선 하방 이탈 시 연쇄 하락...
```

**실제 보고서 본문** 수령 확인. 메타 요약 아님.

## 테스트 수정

`tests/test_claude_code_client.py::test_generate_passes_cli_args`:
- 기존 `--permission-mode plan` 체크 → `--tools ""` 체크로 교체
- `--permission-mode` 는 **포함되지 않아야** (명시적 negative assert)

## 검증

- **라이브 smoke**: 실제 Claude 호출로 분석 본문 1084자 수령 ✅
- `pytest -q` 전수 → **917 passed, 11 deselected**
- `ruff check .` → clean

## 후속

- ADR-0001 §4.5 업데이트 (plan 모드 → tools 비활성) — 별도 PR
- Task 14 전체는 이 fix 로 처음으로 실질적 동작
