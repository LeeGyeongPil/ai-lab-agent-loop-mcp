"""MCP 허브 — 설정 파일의 MCP 서버들에 연결하고, 도구 목록을 합치고, 도구 호출을 알맞은 서버로 보낸다.

MCP에서 우리 에이전트는 "호스트"이고, 서버 하나마다 "클라이언트"(연결) 하나를 둔다.
  - tools/list : 서버가 가진 도구 목록(이름·설명·입력 스키마)을 받는다
  - tools/call : 도구 하나를 인자와 함께 실행해 달라고 요청한다

사용법:
    async with McpHub(load_server_params(path)) as hub:   # 서버 프로세스들이 뜬다
        result = await hub.call("check_stock", {"item": "사과"})
    # async with 블록을 벗어나면(정상 종료·오류·취소 모두) 서버 프로세스가 정리된다
"""

import json
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client

# 도구 하나가 이 시간보다 오래 걸리면 오류 관찰로 돌려준다(멈춘 도구가 실행 전체를 붙잡지 않게).
TOOL_TIMEOUT_SECONDS = 30.0


class ConfigError(Exception):
    """mcp_servers.json 설정이 잘못됐을 때(파일 없음, 형식 오류, 도구 이름 충돌 등)."""


@dataclass
class ToolResult:
    is_error: bool  # MCP 결과의 isError
    observation: str  # 모델에게 돌려줄 관찰 텍스트
    wire_response: dict  # 화면 표시용: MCP 결과를 와이어(JSON) 모양으로 덤프한 것
    seconds: float


def load_server_params(config_path: Path) -> dict[str, StdioServerParameters]:
    """mcp_servers.json 을 읽어 {서버 이름: 실행 방법} 을 만든다.

    형식은 여러 MCP 호스트 앱이 쓰는 {"mcpServers": {이름: {command, args, env}}} 와 같다.
    """
    if not config_path.exists():
        raise ConfigError(f"MCP 서버 설정 파일이 없습니다: {config_path.name}")
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{config_path.name} 의 JSON 형식이 잘못됐습니다: {exc}") from exc

    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        raise ConfigError(f'{config_path.name} 에 "mcpServers" 항목이 비어 있습니다.')

    params = {}
    for name, spec in servers.items():
        command = spec["command"]
        # "python"은 지금 에이전트를 돌리는 가상환경의 파이썬으로 바꾼다(mcp 패키지가 깔린 파이썬).
        if command in ("python", "python3"):
            command = sys.executable
        params[name] = StdioServerParameters(
            command=command,
            args=spec.get("args", []),
            env=spec.get("env"),
            cwd=config_path.parent,  # args의 상대 경로는 설정 파일이 있는 폴더 기준
        )
    return params


def _dump(model) -> dict:
    """SDK 결과 객체 → MCP 와이어(JSON) 모양 dict. 화면의 "MCP 메시지 보기"에 쓴다."""
    return model.model_dump(by_alias=True, exclude_none=True, mode="json")


class McpHub:
    def __init__(self, server_params: dict[str, StdioServerParameters], errlog: TextIO | None = None):
        """errlog: 서버들의 stderr(로그)를 보낼 파일. None이면 지금 터미널(sys.stderr)에 그대로 나온다.

        파일을 열고 닫는 책임은 호출한 쪽에 있다(허브는 빌려 쓰기만 한다).
        """
        self.server_params = server_params
        self.errlog = errlog
        self.clients: dict[str, Client] = {}  # 서버 이름 → 연결
        self.tools: dict[str, list] = {}  # 서버 이름 → 도구 정의 목록(설정 파일 순서 유지)
        self.route: dict[str, str] = {}  # 도구 이름 → 그 도구를 가진 서버 이름
        self.list_wire: dict[str, dict] = {}  # 서버 이름 → tools/list 응답(와이어 모양)
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self) -> "McpHub":
        # AsyncExitStack: 여러 개의 async with 를 한 번에 열고, 나갈 때 역순으로 모두 닫아 준다.
        self._stack = AsyncExitStack()
        try:
            for name, params in self.server_params.items():
                # 1) 서버를 하위 프로세스로 띄우고 stdio로 연결한다
                # errlog가 있으면 stderr를 그 파일로 돌리도록 stdio 연결을 직접 만들어 넘긴다
                transport = stdio_client(params, errlog=self.errlog) if self.errlog else params
                client = Client(transport, read_timeout_seconds=TOOL_TIMEOUT_SECONDS)
                self.clients[name] = await self._stack.enter_async_context(client)

                # 2) tools/list — 이 서버가 가진 도구 목록을 받는다
                listed = await client.list_tools()
                self.tools[name] = listed.tools
                self.list_wire[name] = _dump(listed)

                # 3) 도구 이름 → 서버 이름 길 안내표. 같은 이름이 두 서버에 있으면 어디로 보낼지 모른다.
                for tool in listed.tools:
                    if tool.name in self.route:
                        raise ConfigError(
                            f"도구 이름 '{tool.name}' 이(가) 서버 '{self.route[tool.name]}' 와 '{name}' 에 모두 있습니다. "
                            "한쪽 도구 이름을 바꾸세요."
                        )
                    self.route[tool.name] = name
        except BaseException:
            # 연결 도중 실패·취소되면 이미 띄운 서버들을 정리하고 오류를 그대로 올린다
            await self._stack.aclose()
            raise
        return self

    async def __aexit__(self, *exc_info) -> None:
        # 각 Client가 서버의 stdin을 닫고 프로세스가 끝나기를 기다린다(안 끝나면 강제 종료).
        if self._stack is not None:
            await self._stack.aclose()

    # ── 도구 목록 ──────────────────────────────────────────────

    def tool_names(self) -> list[str]:
        return list(self.route)

    def summary(self) -> list[dict]:
        """화면의 "연결된 MCP 서버" 패널용 요약."""
        return [
            {
                "name": server,
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "input_schema": t.input_schema,
                        "output_schema": t.output_schema,
                    }
                    for t in tools
                ],
            }
            for server, tools in self.tools.items()
        ]

    def ollama_tools(self) -> list[dict]:
        """MCP 도구 정의 → Ollama(OpenAI 함수 호출) 도구 형식. 모델에게는 이 목록이 전달된다."""
        result = []
        for tools in self.tools.values():
            for t in tools:
                result.append(
                    {
                        "type": "function",
                        "function": {"name": t.name, "description": t.description or "", "parameters": t.input_schema},
                    }
                )
        return result

    def server_of(self, tool_name: str) -> str | None:
        return self.route.get(tool_name)

    # ── 도구 호출 ──────────────────────────────────────────────

    async def call(self, name: str, arguments: dict) -> ToolResult:
        """tools/call 을 알맞은 서버로 보내고, 결과를 모델에게 줄 관찰 텍스트로 바꾼다.

        어떤 경우에도 예외를 올리지 않고 ToolResult(is_error=True)로 돌려준다.
        → 오류도 "관찰"이 되어 모델이 읽고 스스로 고칠 기회를 얻는다.
        """
        started = time.perf_counter()

        def elapsed() -> float:
            return round(time.perf_counter() - started, 3)

        server = self.route.get(name)
        if server is None:
            # 모델이 없는 도구 이름을 지어낸 경우: 서버로 보내지 않고 호스트가 오류를 돌려준다
            text = f"unknown tool: {name}. available tools: {self.tool_names()}"
            return ToolResult(True, text, {"host_error": text}, elapsed())

        try:
            result = await self.clients[server].call_tool(name, arguments)
        except Exception as exc:  # 연결 끊김·시간 초과 같은 프로토콜 수준 오류
            text = f"host error while calling {name}: {exc}"
            return ToolResult(True, text, {"host_error": text}, elapsed())

        if result.structured_content is not None and not result.is_error:
            # 구조화 결과(JSON)가 있으면 그걸 관찰로 쓴다
            observation = json.dumps(result.structured_content, ensure_ascii=False)
        else:
            # 없으면 텍스트 content 들을 이어 붙인다 (오류 문구도 여기로 온다)
            observation = "\n".join(getattr(block, "text", "") for block in result.content)
        return ToolResult(result.is_error, observation, _dump(result), elapsed())
