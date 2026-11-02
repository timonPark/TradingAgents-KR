"""한 분석가 턴.

Task 3 (#32) 로 사전조회 패턴 (ADR-0002) 이 도입되었습니다 — Python 이 데이터를
선조회해 프롬프트에 주입하고, LLM 은 단일 호출로 보고서를 작성합니다. `invoke_once`
가 그 경로입니다.

레거시 `take_turn` 과 WRAP_UP 은 아직 전환되지 않은 분석가 (Task 3 하위 이슈
#34, #35, #36 에서 순차 전환) 를 위해 유지됩니다. 모든 분석가가 전환되면 Task 3d
(#36) 에서 함께 삭제됩니다.
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

WRAP_UP = (
    "You have used every tool round this report allows. Write your final report "
    "now from the tool results above, and say which data you could not retrieve."
)


def invoke_once(prompt, llm, messages):
    """사전조회 패턴 분석가용 — 단일 LLM 호출.

    사전조회 데이터는 호출부가 ``prompt.partial(...)`` 로 이미 주입했다는 전제.
    `messages` 는 초기 user 메시지 (`company_of_interest`) 등 LangGraph 가 분석가
    노드에 넘겨준 그대로. 반환은 ``(result, result.content)`` 로 `take_turn` 과
    호환되는 튜플.
    """
    result = (prompt | llm).invoke(messages)
    return result, result.content


def take_turn(prompt, llm, tools, messages):
    """The analyst's reply and its report, which stays empty while it calls tools.

    Told to wrap up, it answers without tools: a model offered tools may call one
    whatever it is told. Its earlier calls and their results reach it as text,
    since a provider may refuse a history holding tool calls when none are bound.
    """
    if messages and isinstance(messages[-1], HumanMessage) and messages[-1].content == WRAP_UP:
        # The prompt lists the tools it offers; a model told of tools it cannot
        # call may still try, and some providers then answer with nothing.
        prompt = prompt.partial(tool_names="none; your tool rounds are spent")
        result = (prompt | llm).invoke(_as_text(messages))
        return result, result.content
    result = (prompt | llm.bind_tools(tools)).invoke(messages)
    return result, "" if result.tool_calls else result.content


def _as_text(messages):
    """The history with its tool calls and tool results written out as plain messages."""
    written = []
    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            said = message.content if isinstance(message.content, str) else ""
            calls = "; ".join(f"{c['name']}({json.dumps(c['args'], default=str)})" for c in message.tool_calls)
            written.append(AIMessage(content=f"{said}\n[Called {calls}]".strip()))
        elif isinstance(message, ToolMessage):
            written.append(HumanMessage(content=f"[{message.name or 'Tool'} returned]\n{message.content}"))
        else:
            written.append(message)
    return written
