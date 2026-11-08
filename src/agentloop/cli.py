"""CLI — 웹 화면과 같은 이벤트를 텍스트 타임라인으로 찍는다.

    [회차 1][생각] 가게에서 파는 과일 이름을 모른다 ...
    [회차 1][도구 호출] list_items {}
    [회차 1][관찰] {"items": ["사과", "바나나", "포도"]}
    ...
    [회차 4][최종 답] 재고가 가장 많은 과일은 사과(12개)이고, 1개에 1,500원입니다.
"""

import json

from agentloop.agent import run_agent
from agentloop.config import PROJECT_ROOT, Settings
from agentloop.events import Event
from agentloop.llm import make_llm
from agentloop.mcp_hub import ConfigError, load_server_params

# MCP 서버들의 stderr(로그)를 모아 두는 파일. 실행할 때마다 새로 써서(덮어쓰기) 크기가 계속 커지지 않는다.
# 터미널로 그대로 보내면 서버 로그 줄이 "[생각] ..." 줄 한가운데에 끼어들어 출력이 깨진다.
SERVER_LOG_FILE = PROJECT_ROOT / "runs" / "mcp-server-stderr.log"

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

    SERVER_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    # with 블록: 실행이 정상 종료·오류·Ctrl+C 어느 쪽으로 끝나도 파일을 닫는다.
    # (서버 프로세스는 run_agent 안의 async with 가 먼저 정리하므로, 닫힌 파일에 쓰는 일은 없다)
    with SERVER_LOG_FILE.open("w", encoding="utf-8") as server_log:
        await run_agent(
            question,
            make_llm(mode, settings),
            server_params,
            max_steps=settings.max_steps,
            mode=mode,
            emit=emit,
            server_errlog=server_log,
        )

    log_lines = SERVER_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    if log_lines:
        relative = SERVER_LOG_FILE.relative_to(PROJECT_ROOT).as_posix()
        print(f"[서버 로그] MCP 서버가 남긴 로그 {len(log_lines)}줄은 {relative} 에 있습니다.")
    return 1 if stop.get("reason") == "error" else 0
