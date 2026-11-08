"""'내 도구' 템플릿 MCP 서버 — 이 파일을 고쳐서 나만의 도구를 에이전트에 붙여 보세요.

지금 들어 있는 도구는 count_chars 하나다. 언어 모델은 토큰 단위로 글을 보기 때문에
"글자 수 세기"를 자주 틀린다. 이런 약점을 함수 몇 줄짜리 도구가 메워 준다.

내 도구를 추가하는 순서
  1) 아래 count_chars를 복사해 새 함수를 만든다.
  2) 함수 위에 @mcp.tool() 을 붙인다.
  3) docstring에 "무엇을 하고 무엇을 돌려주는지"를 영어나 한국어로 구체적으로 쓴다(모델이 읽는다).
  4) 인자와 반환 타입을 적는다(반환은 TypedDict 권장 → 구조화된 JSON 결과가 생긴다).
  5) 에이전트를 다시 실행하면(웹이면 페이지 새로고침) 왼쪽 패널에 새 도구가 보인다.
  새 파일로 서버를 따로 만들었다면 mcp_servers.json 에 한 줄을 추가한다.

주의: 여기서는 print()를 쓰지 말 것. 표준출력은 MCP 메시지 전용이다(로그는 stderr로).
"""

from typing import Annotated, TypedDict

from mcp.server import MCPServer
from pydantic import Field

mcp = MCPServer("my_tools")


class CharCount(TypedDict):
    chars: int  # 공백 포함 글자 수
    chars_no_space: int  # 공백(띄어쓰기·줄바꿈) 제외 글자 수


@mcp.tool()
def count_chars(
    text: Annotated[str, Field(description="The exact text to count, without surrounding quotes")],
) -> CharCount:
    """Count the characters in a text exactly. Language models are bad at counting characters, so use this tool instead of guessing."""
    no_space = "".join(text.split())  # 모든 공백 문자를 지운 문자열
    return {"chars": len(text), "chars_no_space": len(no_space)}


# ▼ 여기에 내 도구를 추가해 보세요. 예)
#
# class Reversed(TypedDict):
#     text: str
#
# @mcp.tool()
# def reverse_text(text: str) -> Reversed:
#     """Return the text with its characters in reverse order."""
#     return {"text": text[::-1]}


if __name__ == "__main__":
    mcp.run()  # 기본 전송 방식은 stdio
