"""사전조회 패턴 분석가의 단일 LLM 호출 (Task 3d #36, ADR-0002).

Task 3 로 모든 분석가 (market/fundamentals/news/sentiment) 가 사전조회 패턴
으로 전환되어 ToolNode / `take_turn` / `WRAP_UP` 가 삭제되었습니다. 남은 패턴은
"Python 이 데이터를 선조회해 프롬프트에 주입 → `invoke_once` 로 단일 호출" 뿐.
"""


def invoke_once(prompt, llm, messages):
    """사전조회 패턴 분석가 전용 — 단일 LLM 호출.

    사전조회 데이터는 호출부가 ``prompt.partial(...)`` 로 이미 주입했다는 전제.
    `messages` 는 LangGraph 가 분석가 노드에 넘겨준 초기 user 메시지. 반환은
    ``(result, result.content)`` — 호출부가 `AIMessage` 와 report 텍스트 양쪽을
    바로 쓸 수 있도록.
    """
    result = (prompt | llm).invoke(messages)
    return result, result.content
