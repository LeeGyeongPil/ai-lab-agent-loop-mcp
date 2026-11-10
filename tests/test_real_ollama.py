"""AC-10: 실제 로컬 모델(qwen3:4b)이 MCP 도구를 써서 답한다. (로컬 전용, CI 제외)

    uv run pytest -m ollama tests/test_real_ollama.py::test_real_chain

Ollama가 꺼져 있거나 모델이 없으면 건너뛴다. 4B 모델이라 1~5분 걸릴 수 있다.
"""

import asyncio
import os
import time

import pytest
from conftest import no_children

from agentloop.agent import run_agent
from agentloop.config import check_ollama, load_settings
from agentloop.llm import OllamaLLM
from agentloop.mcp_hub import load_server_params

pytestmark = [pytest.mark.ollama, pytest.mark.anyio]

TIMEOUT_SECONDS = 300


async def test_real_chain():
    settings = load_settings()
    status = check_ollama(settings.ollama_host, settings.ollama_model)
    if status != "ok":
        pytest.skip(f"Ollama 사용 불가({status}): {settings.ollama_host} / {settings.ollama_model}")

    events = []

    async def emit(event):
        events.append(event.to_dict())
        if event.type in ("tool_call", "tool_result", "answer", "run_end", "error"):
            print(event.to_json(), flush=True)  # -s 로 실행하면 진행 상황이 보인다

    llm = OllamaLLM(settings.ollama_host, settings.ollama_model, settings.num_ctx)
    started = time.perf_counter()
    await asyncio.wait_for(
        run_agent(
            "가장 재고가 많은 과일의 가격은 얼마야?",
            llm,
            load_server_params(settings.servers_file),
            max_steps=settings.max_steps,
            mode="real",
            emit=emit,
        ),
        timeout=TIMEOUT_SECONDS,
    )
    print(f"real run took {time.perf_counter() - started:.1f}s")

    calls = [e for e in events if e["type"] == "tool_call"]
    assert any(c["server"] == "shop" for c in calls), "shop 서버 도구를 한 번도 부르지 않았다"
    end = events[-1]
    assert end["type"] == "run_end" and end["stop_reason"] == "answer", end
    answer = next(e for e in events if e["type"] == "answer")["text"]
    assert "1500" in answer or "1,500" in answer, answer
    assert no_children(os.getpid())
