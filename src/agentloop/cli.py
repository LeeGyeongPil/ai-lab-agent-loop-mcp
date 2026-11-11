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
from agentloop.i18n import t
from agentloop.mcp_hub import ConfigError, load_server_params

# MCP 서버들의 stderr(로그)를 모아 두는 파일. 실행할 때마다 새로 써서(덮어쓰기) 크기가 계속 커지지 않는다.
# 터미널로 그대로 보내면 서버 로그 줄이 "[생각] ..." 줄 한가운데에 끼어들어 출력이 깨진다.
SERVER_LOG_FILE = PROJECT_ROOT / "runs" / "mcp-server-stderr.log"

STOP_REASONS = ("answer", "max_steps", "error", "cancelled")


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


async def print_event(event: Event, lang: str = "en") -> None:
    d = event.data
    head = t(lang, "cli.head", step=event.step)

    def secs(value) -> str:
        return t(lang, "cli.seconds", seconds=value)

    if event.type == "run_start":
        print(t(lang, "cli.question", question=d["question"], model=d["model"]))
    elif event.type == "tools_listed":
        names = " / ".join(f"{s['name']}: {', '.join(t_['name'] for t_ in s['tools'])}" for s in d["servers"])
        count = sum(len(s["tools"]) for s in d["servers"])
        print(t(lang, "cli.prepared", servers=len(d["servers"]), tools=count, names=names, seconds=secs(d["seconds"])))
    elif event.type == "step_start":
        print(f"{head}{t(lang, 'cli.thinking')}", end="", flush=True)
    elif event.type == "thinking_delta":
        print(d["text"], end="", flush=True)  # 생각이 흘러나오는 대로 바로 찍는다
    elif event.type == "thinking_done":
        print(f"  ({secs(d['seconds'])})")
    elif event.type == "tool_call":
        mark = t(lang, "cli.duplicate") if d["duplicate"] else ""
        print(head + t(lang, "cli.tool_call", name=d["name"], arguments=_json(d["arguments"]), server=d["server"], mark=mark))
    elif event.type == "tool_result":
        label = t(lang, "cli.observe_error" if d["is_error"] else "cli.observe")
        print(f"{head}{label} {d['observation']}")
    elif event.type == "answer":
        print(f"{head}{t(lang, 'cli.answer')} {d['text']}")
    elif event.type == "error":
        print(t(lang, "cli.error", message=d["message"]))
        if d["hint"]:
            print(t(lang, "cli.hint", hint=d["hint"]))
    elif event.type == "run_end":
        reason = d["stop_reason"]
        label = t(lang, f"cli.stop.{reason}") if reason in STOP_REASONS else reason
        print(
            t(lang, "cli.end", reason=label, steps=d["steps"], tool_calls=d["tool_calls"], errors=d["errors"],
              seconds=secs(d["seconds"]))
        )


async def run_cli(question: str, settings: Settings, mode: str, lang: str = "en") -> int:
    """질문 하나를 끝까지 돌린다. 종료 코드: 0 정상, 1 오류."""
    try:
        server_params = load_server_params(settings.servers_file, lang=lang)
    except ConfigError as exc:
        print(t(lang, "cli.error", message=exc))
        return 1

    stop = {}

    async def emit(event: Event) -> None:
        if event.type == "run_end":
            stop["reason"] = event.data["stop_reason"]
        await print_event(event, lang)

    SERVER_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    # with 블록: 실행이 정상 종료·오류·Ctrl+C 어느 쪽으로 끝나도 파일을 닫는다.
    # (서버 프로세스는 run_agent 안의 async with 가 먼저 정리하므로, 닫힌 파일에 쓰는 일은 없다)
    with SERVER_LOG_FILE.open("w", encoding="utf-8") as server_log:
        await run_agent(
            question,
            make_llm(mode, settings, lang),
            server_params,
            max_steps=settings.max_steps,
            mode=mode,
            emit=emit,
            server_errlog=server_log,
            lang=lang,
        )

    log_lines = SERVER_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    if log_lines:
        relative = SERVER_LOG_FILE.relative_to(PROJECT_ROOT).as_posix()
        print(t(lang, "cli.server_log", count=len(log_lines), path=relative))
    return 1 if stop.get("reason") == "error" else 0
