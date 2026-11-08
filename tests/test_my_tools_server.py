"""AC-6(일부): '내 도구' 템플릿 서버의 count_chars."""

import my_tools_server
import pytest
from mcp import Client

pytestmark = pytest.mark.anyio


async def test_count_chars():
    async with Client(my_tools_server.mcp) as client:
        names = [t.name for t in (await client.list_tools()).tools]
        result = await client.call_tool("count_chars", {"text": "에이전트 루프"})
    assert names == ["count_chars"]
    assert result.structured_content == {"chars": 7, "chars_no_space": 6}
