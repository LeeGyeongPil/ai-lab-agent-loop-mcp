"""LLM 인터페이스와 실제 모델(Ollama) 구현.

에이전트 루프는 모델을 "한 회차"씩 부른다. 한 회차의 응답은 세 가지 조각으로 흘러나온다.
  - thinking   : 모델의 생각(계획). 화면의 회색 "생각" 카드
  - content    : 모델의 답 본문
  - tool_calls : "이 도구를 이 인자로 불러 줘"라는 요청. 모델은 도구를 직접 실행하지 않는다!
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol

import ollama


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class Chunk:
    """스트리밍 응답의 조각 하나."""

    thinking: str = ""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLM(Protocol):
    name: str  # 화면에 보일 모델 이름

    def stream_turn(self, messages: list[dict], tools: list[dict]) -> AsyncIterator[Chunk]:
        """대화 기록(messages)과 도구 목록(tools)을 주고 한 회차의 응답을 조각으로 받는다."""
        ...


def strip_think_residue(text: str) -> str:
    """답 본문에 섞여 나온 생각 찌꺼기(`...</think>`)를 잘라 낸다.

    qwen3:4b는 생각 전용 모델이라, 가끔 생각 끝 표시가 본문에 남는다.
    """
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return text.strip()


def _parse_arguments(raw) -> dict:
    """도구 인자는 보통 dict로 오지만, 모델에 따라 JSON 문자열로 올 때도 있다."""
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"raw": raw}
    return {}


class OllamaLLM:
    """내 PC의 Ollama(/api/chat)로 모델을 부른다."""

    def __init__(self, host: str, model: str, num_ctx: int):
        self.host = host
        self.model = model
        self.name = f"Ollama {model}"
        self.num_ctx = num_ctx

    async def stream_turn(self, messages: list[dict], tools: list[dict]) -> AsyncIterator[Chunk]:
        client = ollama.AsyncClient(host=self.host)
        try:
            stream = await client.chat(
                model=self.model,
                messages=messages,
                tools=tools,
                stream=True,
                # qwen3:4b는 생각을 끌 수 없는 모델이다. think=False면 생각이 본문으로 샌다.
                # 그래서 생각을 켜 두고 따로 받아 "계획" 카드로 보여 준다.
                think=True,
                # num_ctx는 항상 같은 값으로! 값이 바뀌면 Ollama가 모델을 다시 적재한다(10~20초).
                options={"num_ctx": self.num_ctx, "temperature": 0},
                keep_alive="15m",  # 회차 사이에 모델이 메모리에서 내려가지 않게
            )
            async for part in stream:
                message = part.message
                yield Chunk(
                    thinking=message.thinking or "",
                    content=message.content or "",
                    tool_calls=[
                        ToolCall(call.function.name, _parse_arguments(call.function.arguments))
                        for call in (message.tool_calls or [])
                    ],
                )
        finally:
            await client.close()  # HTTP 연결 정리(정상 종료·취소 모두)


def make_llm(mode: str, settings) -> LLM:
    """모드에 맞는 LLM을 만든다. mock → 대본대로 움직이는 가짜 LLM, real → Ollama."""
    if mode == "mock":
        from agentloop.mock_llm import ScriptedLLM

        return ScriptedLLM(settings.scenarios_dir, settings.mock_delay_ms)
    return OllamaLLM(settings.ollama_host, settings.ollama_model, settings.num_ctx)
