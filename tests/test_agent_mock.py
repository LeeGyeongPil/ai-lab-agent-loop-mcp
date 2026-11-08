"""AC-3 · AC-4 · AC-5: 모의 LLM(대본) + 진짜 MCP 서버로 에이전트 루프의 이벤트를 검증한다."""

import json
import os
from pathlib import Path

import pytest
from conftest import TESTS_DIR, child_pids

from agentloop.agent import run_agent
from agentloop.mcp_hub import load_server_params
from agentloop.mock_llm import NO_SCRIPT_ANSWER, ScriptedLLM
from agentloop.prompts import SYSTEM_PROMPT

pytestmark = pytest.mark.anyio

CHAIN_Q = "가장 재고가 많은 과일의 가격은 얼마야?"


async def collect(settings, question: str, scenarios_dir: Path | None = None, max_steps: int = 6) -> list[dict]:
    """에이전트를 끝까지 돌리고 이벤트를 dict 목록으로 모은다."""
    events = []

    async def emit(event):
        events.append(event.to_dict())

    llm = ScriptedLLM(scenarios_dir or settings.scenarios_dir, delay_ms=0)
    await run_agent(question, llm, load_server_params(settings.servers_file), max_steps=max_steps, mode="mock", emit=emit)
    return events


def types_without_deltas(events: list[dict]) -> list[str]:
    return [e["type"] for e in events if e["type"] != "thinking_delta"]


async def test_chain_event_sequence(settings):
    events = await collect(settings, CHAIN_Q)

    step = ["step_start", "thinking_done"]
    pair = ["tool_call", "tool_result"]
    expected = (
        ["run_start", "tools_listed"]
        + step + pair  # 회차 1: list_items
        + step + pair * 3  # 회차 2: check_stock ×3
        + step + pair  # 회차 3: get_price
        + step + ["answer", "run_end"]  # 회차 4: 답
    )
    assert types_without_deltas(events) == expected

    end = events[-1]
    assert (end["stop_reason"], end["steps"], end["tool_calls"], end["errors"]) == ("answer", 4, 5, 0)

    # 생각은 조각(thinking_delta)으로 흘러나오고, 합치면 thinking_done의 전체 텍스트가 된다
    step1_deltas = "".join(e["text"] for e in events if e["type"] == "thinking_delta" and e["step"] == 1)
    step1_done = next(e for e in events if e["type"] == "thinking_done" and e["step"] == 1)
    assert step1_deltas == step1_done["text"] and len(step1_deltas) > 0

    # 관찰 값은 대본이 아니라 진짜 MCP 서버의 응답이다
    results = [e for e in events if e["type"] == "tool_result"]
    assert json.loads(results[1]["observation"]) == {"item": "사과", "count": 12}
    price = results[-1]
    assert json.loads(price["observation"])["price_won"] == 1500
    assert price["wire_response"]["structuredContent"] == {"item": "사과", "price_won": 1500}
    assert price["wire_response"]["isError"] is False

    calls = [e for e in events if e["type"] == "tool_call"]
    assert [c["name"] for c in calls] == ["list_items", "check_stock", "check_stock", "check_stock", "get_price"]
    assert all(c["server"] == "shop" for c in calls)
    assert calls[-1]["wire_request"]["method"] == "tools/call"
    assert "1,500원" in next(e for e in events if e["type"] == "answer")["text"]


async def test_conversation_history_grows(settings):
    """에이전트 = 대화 기록을 늘려 가며 모델을 다시 부르는 반복문. 이전 생각은 기록에 넣지 않는다."""
    events = await collect(settings, CHAIN_Q)
    starts = [e for e in events if e["type"] == "step_start"]
    # system+user=2 → +assistant+tool 1개=4 → +assistant+tool 3개=8 → +assistant+tool 1개=10
    assert [s["messages_count"] for s in starts] == [2, 4, 8, 10]
    last = starts[-1]["messages_preview"]
    assert [m["role"] for m in last[:4]] == ["system", "user", "assistant", "tool"]
    assert last[0]["text"] == SYSTEM_PROMPT
    assert "tool_calls: list_items({})" in last[2]["text"]
    assert last[3]["tool_name"] == "list_items"
    thinking_1 = next(e for e in events if e["type"] == "thinking_done")["text"]
    assert all(thinking_1 not in m["text"] for m in last)


async def test_error_observed_then_answer(settings):
    events = await collect(settings, "수박 재고 있어?")  # 예외 없이 끝나야 한다
    types = types_without_deltas(events)
    error_at = next(i for i, e in enumerate(events) if e["type"] == "tool_result" and e["is_error"])
    after = [e["type"] for e in events[error_at + 1 :] if e["type"] != "thinking_delta"]
    assert after[:2] == ["step_start", "thinking_done"]
    assert "answer" in after
    assert "error" not in types
    assert "known:" in events[error_at]["observation"]
    end = events[-1]
    assert (end["stop_reason"], end["errors"]) == ("answer", 1)


async def test_max_steps_guard(settings):
    events = await collect(settings, "끝나지 않는 질문", scenarios_dir=TESTS_DIR / "scenarios_loop", max_steps=3)
    end = events[-1]
    assert (end["stop_reason"], end["steps"], end["tool_calls"]) == ("max_steps", 3, 3)
    assert "answer" not in types_without_deltas(events)
    # 같은 호출을 되풀이하면 두 번째부터 "중복 호출" 표시가 붙는다
    assert [e["duplicate"] for e in events if e["type"] == "tool_call"] == [False, True, True]


async def test_unknown_tool_becomes_error_observation(settings):
    events = await collect(settings, "없는 도구 질문", scenarios_dir=TESTS_DIR / "scenarios_loop")
    call = next(e for e in events if e["type"] == "tool_call")
    result = next(e for e in events if e["type"] == "tool_result")
    assert call["server"] is None
    assert result["is_error"] and "unknown tool" in result["observation"]
    assert events[-1]["stop_reason"] == "answer"


async def test_unscripted_question_answers_with_notice(settings):
    events = await collect(settings, "오늘 날씨 어때?")
    answer = next(e for e in events if e["type"] == "answer")
    assert answer["text"] == NO_SCRIPT_ANSWER
    assert events[-1]["stop_reason"] == "answer"


async def test_config_error_becomes_error_event(settings, tmp_path):
    bad = tmp_path / "dup.json"
    shop = str(Path(settings.servers_file).parent / "servers" / "shop_server.py")
    bad.write_text(json.dumps({"mcpServers": {"a": {"command": "python", "args": [shop]}, "b": {"command": "python", "args": [shop]}}}))
    events = []

    async def emit(event):
        events.append(event.to_dict())

    llm = ScriptedLLM(settings.scenarios_dir, delay_ms=0)
    await run_agent(CHAIN_Q, llm, load_server_params(bad), max_steps=3, mode="mock", emit=emit)
    assert [e["type"] for e in events] == ["run_start", "error", "run_end"]
    assert events[-1]["stop_reason"] == "error"
    assert child_pids(os.getpid()) == []
