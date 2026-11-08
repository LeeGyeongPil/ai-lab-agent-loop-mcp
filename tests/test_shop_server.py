"""AC-2: 예제 MCP 서버가 표준 도구 계약(tools/list · tools/call · isError)을 지킨다.

메모리 내 연결(Client(server))을 써서 프로세스 없이 빠르게 확인한다.
"""

import pytest
import shop_server
from mcp import Client

pytestmark = pytest.mark.anyio


async def test_tools_list_order_and_schema():
    async with Client(shop_server.mcp) as client:
        tools = (await client.list_tools()).tools
    assert [t.name for t in tools] == ["list_items", "check_stock", "get_price"]
    for t in tools:
        assert t.description, t.name
        assert t.input_schema["type"] == "object"
        assert t.output_schema is not None, f"{t.name}: 반환형이 TypedDict라 outputSchema가 있어야 한다"
    check_stock = tools[1]
    assert check_stock.input_schema["required"] == ["item"]
    assert "description" in check_stock.input_schema["properties"]["item"]


async def test_check_stock_ok():
    async with Client(shop_server.mcp) as client:
        result = await client.call_tool("check_stock", {"item": "사과"})
    assert result.is_error is False
    assert result.structured_content == {"item": "사과", "count": 12}


async def test_get_price_ok():
    async with Client(shop_server.mcp) as client:
        result = await client.call_tool("get_price", {"item": "포도"})
    assert result.structured_content == {"item": "포도", "price_won": 4000}


async def test_unknown_item_is_tool_error():
    async with Client(shop_server.mcp) as client:
        result = await client.call_tool("check_stock", {"item": "수박"})  # 예외가 아니라 결과로 온다
    assert result.is_error is True
    text = result.content[0].text
    assert "known:" in text and "수박" in text
