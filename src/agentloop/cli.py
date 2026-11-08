"""CLI — 웹 화면과 같은 이벤트를 텍스트 타임라인으로 찍는다.

    [회차 1][생각] 가게에서 파는 과일 이름을 모른다 ...
    [회차 1][도구 호출] list_items {}
    [회차 1][관찰] {"items": ["사과", "바나나", "포도"]}
    ...
    [회차 4][최종 답] 재고가 가장 많은 과일은 사과(12개)이고, 1개에 1,500원입니다.
"""

import json

from agentloop.agent import run_agent
from agentloop.config import Settings
from agentloop.events import Event
from agentloop.llm import make_llm
from agentloop.mcp_hub import ConfigError, load_server_params

STOP_LABELS = {"answer": "답을 냄", "max_steps": "최대 회차 도달", "error": "오류", "cancelled": "취소됨"}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


async def print_event(event: Event) -> None:
    d = event.data
    head = f"[회차 {event.step}]"

    if event.type == "run_start":
        print(f"질문: {d['question']}  (모델: {d['model']})")
    elif event.type == "tools_listed":
        names = " / ".join(f"{s['name']}: {', '.join(t['name'] for t in s['tools'])}" for s in d["servers"])
        count = sum(len(s["tools"]) for s in d["servers"])
        print(f"[준비] MCP 서버 {len(d['servers'])}개 연결 · 도구 {count}개 ({names}) · {d['seconds']}초")
    elif event.type == "step_start":
        print(f"{head}[생각] ", end="", flush=True)
    elif event.type == "thinking_delta":
        print(d["text"], end="", flush=True)  # 생각이 흘러나오는 대로 바로 찍는다
    elif event.type == "thinking_done":
        print(f"  ({d['seconds']}초)")
    elif event.type == "tool_call":
        mark = " (중복 호출)" if d["duplicate"] else ""
        print(f"{head}[도구 호출] {d['name']} {_json(d['arguments'])} → 서버 {d['server']}{mark}")
    elif event.type == "tool_result":
        label = "[관찰·오류]" if d["is_error"] else "[관찰]"
        print(f"{head}{label} {d['observation']}")
    elif event.type == "answer":
        print(f"{head}[최종 답] {d['text']}")
    elif event.type == "error":
        print(f"[오류] {d['message']}")
        if d["hint"]:
            print(f"[해결] {d['hint']}")
    elif event.type == "run_end":
        print(
            f"[끝] {STOP_LABELS.get(d['stop_reason'], d['stop_reason'])} · 회차 {d['steps']} · "
            f"도구 호출 {d['tool_calls']} · 오류 {d['errors']} · 총 {d['seconds']}초"
        )


async def run_cli(question: str, settings: Settings, mode: str) -> int:
    """질문 하나를 끝까지 돌린다. 종료 코드: 0 정상, 1 오류."""
    try:
        server_params = load_server_params(settings.servers_file)
    except ConfigError as exc:
        print(f"[오류] {exc}")
        return 1

    stop = {}

    async def emit(event: Event) -> None:
        if event.type == "run_end":
            stop["reason"] = event.data["stop_reason"]
        await print_event(event)

    await run_agent(
        question,
        make_llm(mode, settings),
        server_params,
        max_steps=settings.max_steps,
        mode=mode,
        emit=emit,
    )
    return 1 if stop.get("reason") == "error" else 0
