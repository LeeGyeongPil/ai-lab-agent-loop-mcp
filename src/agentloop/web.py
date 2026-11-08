"""웹 서버 — 에이전트 루프의 이벤트를 SSE(Server-Sent Events)로 브라우저에 실시간 중계한다.

    GET /               화면(static/index.html)
    GET /api/config     모드·예시 질문·시스템 프롬프트
    GET /api/tools      연결된 MCP 서버와 도구 목록(tools/list) — 부를 때마다 서버를 새로 띄워 확인
    GET /api/run?q=&mode=   질문 하나를 실행하고 이벤트를 SSE로 흘려보낸다(동시에 1개만)

브라우저 연결이 끊기면(탭 닫기·중지 버튼) 실행 중인 에이전트를 취소하고 MCP 서버 프로세스를 정리한다.
"""

import asyncio
import contextlib
import webbrowser
from pathlib import Path

import anyio
from sse_starlette.sse import EventSourceResponse
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from agentloop.agent import run_agent
from agentloop.config import Settings
from agentloop.events import Event
from agentloop.llm import make_llm
from agentloop.mcp_hub import ConfigError, McpHub, load_server_params
from agentloop.mock_llm import load_scenarios
from agentloop.prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_KO

STATIC_DIR = Path(__file__).parent / "static"
QUEUE_SIZE = 256  # 실행 하나의 이벤트 대기열 크기(브라우저가 느리면 에이전트가 잠시 기다린다)
MAX_QUESTION_CHARS = 500


class RunSlot:
    """동시에 실행 1개만 허용하는 자리표. (Ollama 하나로 여러 실행을 돌리면 모두 느려진다)"""

    def __init__(self):
        self.busy = False

    def try_take(self) -> bool:
        if self.busy:
            return False
        self.busy = True
        return True

    def release(self) -> None:
        self.busy = False


class RunStreamResponse(EventSourceResponse):
    """SSE 응답이 어떻게 끝나든(정상·끊김·오류) 마지막에 자리를 반납하는 응답."""

    def __init__(self, content, *, slot: RunSlot, **kwargs):
        super().__init__(content, **kwargs)
        self.slot = slot

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.slot.release()


def create_app(settings: Settings, mode: str, notice: str, open_browser: bool = False) -> Starlette:
    slot = RunSlot()  # 앱 하나에 자리 하나 (전역 변수 대신 앱에 묶어 둔다)

    async def index(request: Request):
        return FileResponse(STATIC_DIR / "index.html")

    async def api_config(request: Request):
        return JSONResponse(
            {
                "mode": mode,
                "notice": notice,
                "model": settings.ollama_model,
                "max_steps": settings.max_steps,
                "examples": [s["question"] for s in load_scenarios(settings.scenarios_dir)],
                "system_prompt": SYSTEM_PROMPT,
                "system_prompt_ko": SYSTEM_PROMPT_KO,
            }
        )

    async def api_tools(request: Request):
        try:
            async with McpHub(load_server_params(settings.servers_file)) as hub:
                return JSONResponse({"servers": hub.summary(), "wire": hub.list_wire})
        except ConfigError as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    async def api_run(request: Request):
        question = request.query_params.get("q", "").strip()
        run_mode = request.query_params.get("mode", mode)
        if not question or len(question) > MAX_QUESTION_CHARS:
            return JSONResponse({"error": f"질문은 1~{MAX_QUESTION_CHARS}자로 입력하세요."}, status_code=400)
        if run_mode not in ("mock", "real"):
            return JSONResponse({"error": "mode는 mock 또는 real 입니다."}, status_code=400)
        try:
            server_params = load_server_params(settings.servers_file)
        except ConfigError as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
        if not slot.try_take():
            return JSONResponse({"error": "다른 실행이 진행 중입니다. 끝난 뒤 다시 시도하세요."}, status_code=409)

        llm = make_llm(run_mode, settings)

        async def event_stream():
            # 에이전트는 별도 작업(task)으로 돌고, 이벤트를 대기열에 넣는다. 여기서는 꺼내서 보내기만 한다.
            queue: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=QUEUE_SIZE)

            async def produce():
                try:
                    await run_agent(
                        question, llm, server_params, max_steps=settings.max_steps, mode=run_mode, emit=queue.put
                    )
                finally:
                    with contextlib.suppress(asyncio.QueueFull):
                        queue.put_nowait(None)  # "끝" 표시

            task = asyncio.create_task(produce())
            try:
                # 대기열이 가득 찬 채 실행이 끝나면 "끝" 표시가 들어가지 못할 수 있다.
                # 그래서 표시만 기다리지 않고, 작업이 끝났고 대기열이 비었는지도 0.5초마다 확인한다.
                while not (task.done() and queue.empty()):
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=0.5)
                    except TimeoutError:
                        continue
                    if event is None:
                        break
                    yield {"event": event.type, "data": event.to_json()}
            finally:
                # 정상 종료든 연결 끊김이든: 에이전트 작업을 멈추고 MCP 서버 정리가 끝날 때까지 기다린다.
                # shield: 이 정리 자체가 취소되지 않게 보호(최대 10초).
                task.cancel()
                with anyio.move_on_after(10, shield=True):
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

        return RunStreamResponse(event_stream(), slot=slot)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        if open_browser:
            webbrowser.open(f"http://127.0.0.1:{settings.port}")
        yield

    return Starlette(
        routes=[
            Route("/", index),
            Route("/api/config", api_config),
            Route("/api/tools", api_tools),
            Route("/api/run", api_run),
            Mount("/static", StaticFiles(directory=STATIC_DIR), name="static"),
        ],
        lifespan=lifespan,
    )
