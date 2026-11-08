"""예제 MCP 서버 'shop' — 작은 과일 가게의 재고와 가격을 알려 주는 도구 3개.

모델은 우리 가게 재고를 알 수 없으므로, 답하려면 이 도구들을 불러야 한다.
데이터는 고정 값이라 몇 번을 실행해도 결과가 같다(테스트·모의 모드에 유리).

직접 실행해 볼 일은 거의 없다. 에이전트 호스트가 `mcp_servers.json`을 읽고
이 파일을 하위 프로세스로 띄운 뒤 표준입출력(stdio)으로 JSON-RPC 메시지를 주고받는다.

주의: stdio MCP 서버에서는 print()를 쓰면 안 된다. 표준출력은 MCP 메시지 전용 통로다.
"""

from typing import Annotated, TypedDict

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

# 서버 이름. 화면의 "연결된 MCP 서버" 패널에는 mcp_servers.json에 적은 이름이 쓰인다.
mcp = MCPServer("shop")

# 가게 데이터 (모델이 학습으로는 알 수 없는 "사적인" 정보)
STOCK = {"사과": 12, "바나나": 0, "포도": 5}
PRICE_WON = {"사과": 1500, "바나나": 2000, "포도": 4000}


# 반환형을 TypedDict로 적으면 SDK가 outputSchema와 structuredContent(JSON 결과)를 만들어 준다.
# 그냥 dict로 적으면 구조화 결과가 생기지 않는다.
class ItemList(TypedDict):
    items: list[str]


class StockInfo(TypedDict):
    item: str
    count: int


class PriceInfo(TypedDict):
    item: str
    price_won: int


# 인자 설명은 입력 스키마(inputSchema)의 description이 되어 모델에게 그대로 전달된다.
ItemName = Annotated[str, Field(description="One Korean fruit name exactly as returned by list_items, e.g. 사과")]


def _ensure_known(item: str) -> None:
    """모르는 품목이면 ToolError를 던진다.

    ToolError의 문구는 isError: true 결과로 모델에게 그대로 전달되어,
    모델이 "어떤 값이 가능한지" 읽고 스스로 고칠 수 있다.
    (일반 예외를 던지면 보안상 원인 문구가 숨겨지고 'Error executing tool'만 전달된다.)
    """
    if item not in STOCK:
        raise ToolError(f"unknown item: {item}. known: {list(STOCK)}")


# @mcp.tool() 이 붙은 함수 = 도구 하나. 함수 이름이 도구 이름, docstring이 도구 설명이 된다.
# 도구 설명은 모델이 읽는 "사용 설명서"이므로 무엇을 돌려주는지 구체적으로 쓴다.
@mcp.tool()
def list_items() -> ItemList:
    """List every fruit the shop sells. Returns Korean fruit names (e.g. 사과, 바나나, 포도). Call this first if you do not know the item names."""
    return {"items": list(STOCK)}


@mcp.tool()
def check_stock(item: ItemName) -> StockInfo:
    """Return how many units of one fruit are in the shop's stock right now."""
    _ensure_known(item)
    return {"item": item, "count": STOCK[item]}


@mcp.tool()
def get_price(item: ItemName) -> PriceInfo:
    """Return the price of one unit of a fruit, in Korean won (KRW)."""
    _ensure_known(item)
    return {"item": item, "price_won": PRICE_WON[item]}


if __name__ == "__main__":
    mcp.run()  # 기본 전송 방식은 stdio
