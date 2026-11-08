"""에이전트 루프 — 이 데모의 핵심. 위에서 아래로 읽으면 된다.

에이전트의 정체는 "대화 기록(messages)을 늘려 가며 모델을 다시 부르는 반복문" 하나다.

    대화 기록 = [시스템 지시, 사용자 질문]
    반복 (최대 N회차):
        1) 계획: 모델에게 대화 기록 + 도구 목록을 주고 응답을 받는다(생각 + 도구 요청 또는 답)
        2) 도구 요청이 없으면 → 그게 최종 답. 끝.
        3) 행동: 요청받은 도구를 MCP 서버로 실행한다(모델이 아니라 이 호스트가 실행한다!)
        4) 관찰: 실행 결과(오류 포함)를 대화 기록에 붙이고 1)로 돌아간다

각 단계마다 이벤트(events.py)를 emit() 으로 내보낸다. 웹 화면과 CLI는 이 이벤트를 받아 그린다.
"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable

from mcp import StdioServerParameters

from agentloop.events import Event
from agentloop.llm import LLM, strip_think_residue
from agentloop.mcp_hub import ConfigError, McpHub
from agentloop.prompts import SYSTEM_PROMPT

log = logging.getLogger("agentloop")

Emit = Callable[[Event], Awaitable[None]]


async def run_agent(
    question: str,
    llm: LLM,
    server_params: dict[str, StdioServerParameters],
    *,
    max_steps: int,
    mode: str,
    emit: Emit,
) -> None:
    started = time.perf_counter()
    stats = {"steps": 0, "tool_calls": 0, "errors": 0}
    stop_reason = "max_steps"  # 답이 나오면 "answer"로 바뀐다

    async def send(type_: str, step: int = 0, **data) -> None:
        await emit(Event(type_, step, time.perf_counter() - started, data))

    try:
        await send("run_start", mode=mode, model=llm.name, question=question)

        # ── 준비: MCP 서버들에 연결하고 도구 목록(tools/list)을 받는다 ──
        async with McpHub(server_params) as hub:
            await send("tools_listed", servers=hub.summary(), wire=hub.list_wire, seconds=_since(started))

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ]
            tools = hub.ollama_tools()
            seen_calls = set()  # 같은 도구를 같은 인자로 또 부르는지 표시하려고

            for step in range(1, max_steps + 1):
                stats["steps"] = step
                await send("step_start", step, messages_count=len(messages), messages_preview=_preview(messages))

                # ── 1) 계획: 모델 호출 (생각은 조각조각 흘러나온다) ──
                turn_started = time.perf_counter()
                thinking, content, calls = "", "", []
                async for chunk in llm.stream_turn(messages, tools):
                    if chunk.thinking:
                        thinking += chunk.thinking
                        await send("thinking_delta", step, text=chunk.thinking)
                    content += chunk.content
                    calls += chunk.tool_calls
                await send("thinking_done", step, text=thinking, chars=len(thinking), seconds=_since(turn_started))

                # ── 2) 도구 요청이 없으면 = 최종 답 ──
                if not calls:
                    await send("answer", step, text=strip_think_residue(content) or "(모델이 빈 답을 냈습니다)")
                    stop_reason = "answer"
                    break

                # 모델의 요청을 대화 기록에 남긴다. 생각(thinking)은 넣지 않는다 → 기록이 짧아져 다음 회차가 빨라진다.
                messages.append(
                    {
                        "role": "assistant",
                        "content": strip_think_residue(content),
                        "tool_calls": [{"function": {"name": c.name, "arguments": c.arguments}} for c in calls],
                    }
                )

                # ── 3) 행동 + 4) 관찰: 요청 순서대로 실행하고 결과를 기록에 붙인다 ──
                for call in calls:
                    stats["tool_calls"] += 1
                    call_id = f"call-{stats['tool_calls']}"
                    key = (call.name, json.dumps(call.arguments, sort_keys=True, ensure_ascii=False))
                    await send(
                        "tool_call",
                        step,
                        call_id=call_id,
                        server=hub.server_of(call.name),
                        name=call.name,
                        arguments=call.arguments,
                        duplicate=key in seen_calls,
                        wire_request=_wire_request(stats["tool_calls"], call.name, call.arguments),
                    )
                    seen_calls.add(key)

                    result = await hub.call(call.name, call.arguments)  # ← 실제 MCP tools/call
                    if result.is_error:
                        stats["errors"] += 1  # 오류도 예외가 아니라 "관찰"이다
                    await send(
                        "tool_result",
                        step,
                        call_id=call_id,
                        name=call.name,
                        is_error=result.is_error,
                        observation=result.observation,
                        wire_response=result.wire_response,
                        seconds=result.seconds,
                    )
                    messages.append({"role": "tool", "tool_name": call.name, "content": result.observation})

    except asyncio.CancelledError:
        # 사용자가 중지했거나 브라우저 연결이 끊김 → async with 가 MCP 서버를 정리한 뒤 여기로 온다
        stop_reason = "cancelled"
        _log_run_end(stop_reason, stats, started)
        raise
    except Exception as exc:  # Ollama 꺼짐, 설정 오류 등
        stop_reason = "error"
        message, hint = _explain_error(exc)
        await send("error", message=message, hint=hint)

    _log_run_end(stop_reason, stats, started)
    await send("run_end", stop_reason=stop_reason, **stats, seconds=_since(started))


# ── 아래는 화면 표시를 돕는 작은 함수들 ─────────────────────────


def _since(started: float) -> float:
    return round(time.perf_counter() - started, 2)


def _log_run_end(stop_reason: str, stats: dict, started: float) -> None:
    log.info("run_end stop_reason=%s steps=%s tool_calls=%s errors=%s seconds=%s",
             stop_reason, stats["steps"], stats["tool_calls"], stats["errors"], _since(started))


def _wire_request(request_id: int, name: str, arguments: dict) -> dict:
    """화면 표시용 tools/call 요청 모양(실제 전송 바이트가 아니라 _meta를 뺀 재구성)."""
    return {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


def _preview(messages: list[dict], limit: int = 400) -> list[dict]:
    """"모델에게 보낸 대화 기록" 패널용 요약."""
    preview = []
    for m in messages:
        text = m.get("content") or ""
        if m.get("tool_calls"):
            calls = ", ".join(
                f"{c['function']['name']}({json.dumps(c['function']['arguments'], ensure_ascii=False)})" for c in m["tool_calls"]
            )
            text = (text + "\n" if text else "") + f"tool_calls: {calls}"
        item = {"role": m["role"], "text": text[:limit] + ("…" if len(text) > limit else "")}
        if m.get("tool_name"):
            item["tool_name"] = m["tool_name"]
        preview.append(item)
    return preview


def _explain_error(exc: Exception) -> tuple[str, str]:
    """예외를 사람이 읽을 문구와 해결 방법(hint)으로 바꾼다."""
    message = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, ConfigError):
        return str(exc), "mcp_servers.json 과 servers/ 폴더의 서버 코드를 확인하세요."
    if isinstance(exc, ConnectionError) or type(exc).__name__ in ("ConnectError", "ConnectTimeout"):
        return message, "Ollama가 꺼져 있습니다. 터미널에서 `ollama serve`를 실행하거나, 모드를 모의로 바꾸세요."
    if "not found" in str(exc).lower():
        return message, "모델이 없습니다. `ollama pull qwen3:4b`로 받은 뒤 다시 실행하세요."
    return message, ""
