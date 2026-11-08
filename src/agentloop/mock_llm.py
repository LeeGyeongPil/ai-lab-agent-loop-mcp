"""모의 모드의 가짜 LLM — 대본(scenarios/*.json)대로 생각·도구 호출·답을 낸다.

모델은 가짜지만 도구 호출은 **진짜 MCP 서버**로 간다. 그래서 관찰 값은 실제 서버의 응답이다.
네트워크·모델 없이 항상 같은 결과가 나오므로 테스트·CI·화면 녹화에 쓴다.

대본 파일 모양:
    {
      "order": 1,                         # 예시 질문 버튼 순서
      "question": "가장 재고가 많은 ...",   # 예시 질문(화면 버튼)
      "match": ["재고", "가격"],           # 질문에 이 낱말이 모두 들어 있으면 이 대본을 쓴다
      "turns": [                           # 회차별 응답
        {"thinking": "...", "tool_calls": [{"name": "list_items", "arguments": {}}]},
        {"thinking": "...", "answer": "..."}
      ]
    }
"""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

from agentloop.llm import Chunk, ToolCall

NO_SCRIPT_ANSWER = (
    "모의 모드는 예시 질문 3개만 대본이 있습니다. "
    "실제 모드(Ollama)로 실행하면 아무 질문이나 할 수 있습니다."
)

PIECE_SIZE = 3  # 글자를 몇 자씩 흘려 보낼지


def load_scenarios(scenarios_dir: Path) -> list[dict]:
    """대본 파일들을 order 순서로 읽는다."""
    scenarios = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(scenarios_dir.glob("*.json"))]
    return sorted(scenarios, key=lambda s: s.get("order", 99))


def _pieces(text: str) -> list[str]:
    return [text[i : i + PIECE_SIZE] for i in range(0, len(text), PIECE_SIZE)]


class ScriptedLLM:
    name = "모의 LLM (대본)"

    def __init__(self, scenarios_dir: Path, delay_ms: int = 25):
        self.scenarios = load_scenarios(scenarios_dir)
        self.delay = delay_ms / 1000

    def pick_scenario(self, question: str) -> dict | None:
        for scenario in self.scenarios:
            if all(word in question for word in scenario["match"]):
                return scenario
        return None

    async def stream_turn(self, messages: list[dict], tools: list[dict]) -> AsyncIterator[Chunk]:
        # 지금이 몇 번째 회차인지는 대화 기록의 assistant 메시지 수로 안다(상태를 따로 두지 않는다).
        question = next(m["content"] for m in messages if m["role"] == "user")
        turn_index = sum(1 for m in messages if m["role"] == "assistant")

        scenario = self.pick_scenario(question)
        if scenario is None:
            turn = {"thinking": "이 질문에 맞는 대본이 없다. 안내 문구로 답하자.", "answer": NO_SCRIPT_ANSWER}
        else:
            turns = scenario["turns"]
            # 대본이 끝났는데 또 불리면 마지막 회차를 되풀이한다(최대 회차 가드 시험용)
            turn = turns[min(turn_index, len(turns) - 1)]

        # 1) 생각을 몇 글자씩 흘려 보낸다 (실제 모델의 스트리밍 흉내)
        for piece in _pieces(turn.get("thinking", "")):
            await asyncio.sleep(self.delay)  # 0이어도 다른 작업(취소 등)에 차례를 넘긴다
            yield Chunk(thinking=piece)

        # 2) 답 본문
        for piece in _pieces(turn.get("answer", "")):
            await asyncio.sleep(self.delay)
            yield Chunk(content=piece)

        # 3) 도구 호출 요청
        calls = [ToolCall(c["name"], c.get("arguments", {})) for c in turn.get("tool_calls", [])]
        if calls:
            yield Chunk(tool_calls=calls)
