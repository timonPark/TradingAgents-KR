"""Guard the news analyst against tool-signature drift (#1116).

Task 3c (#35) 로 news_analyst 가 사전조회 패턴으로 전환되어 LLM 이 더 이상
get_news 를 직접 호출하지 않습니다. 그래도 Python 선조회 코드가 get_news 의
현재 시그니처 (start_date, end_date) 를 그대로 쓰는지는 검증합니다 — vendor
가 query 파라미터를 재도입하면 선조회 코드도 깨져야 합니다.
"""
import inspect

import pytest

import tradingagents.agents.analysts.news_analyst as na
from tradingagents.agents.tools import get_news


@pytest.mark.unit
def test_get_news_takes_the_window_not_a_query():
    arg_names = set(get_news.tool_call_schema.model_json_schema()["properties"])
    assert arg_names == {"start_date", "end_date"}


@pytest.mark.unit
def test_news_module_uses_window_not_query():
    """선조회 코드가 start_date/end_date 로 호출하는지 확인. query 재도입 방지."""
    src = inspect.getsource(na)
    assert "start_date" in src and "end_date" in src
    assert "get_news(query" not in src
    assert '"query"' not in src
