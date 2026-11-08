"""에이전트 루프가 내보내는 이벤트 — 웹·CLI·테스트가 함께 쓰는 약속(계약).

모든 이벤트는 {"type", "step", "t", ...추가 필드} 모양의 JSON이 된다.
  - type: 무슨 일이 일어났나 (아래 표)
  - step: 몇 번째 회차인가 (회차 밖의 이벤트는 0)
  - t:    실행 시작 후 몇 초가 지났나

| type            | 추가 필드                                                         |
|-----------------|-------------------------------------------------------------------|
| run_start       | mode, model, question                                             |
| tools_listed    | servers[{name, tools[...]}], wire, seconds                        |
| step_start      | messages_count, messages_preview                                  |
| thinking_delta  | text (생각 조각, 스트리밍)                                        |
| thinking_done   | text, chars, seconds                                              |
| tool_call       | call_id, server, name, arguments, duplicate, wire_request         |
| tool_result     | call_id, name, is_error, observation, wire_response, seconds      |
| answer          | text                                                              |
| error           | message, hint                                                     |
| run_end         | stop_reason(answer/max_steps/error/cancelled), steps, tool_calls, errors, seconds |
"""

import json
from dataclasses import dataclass, field


@dataclass
class Event:
    type: str
    step: int = 0
    t: float = 0.0
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"type": self.type, "step": self.step, "t": round(self.t, 2), **self.data}

    def to_json(self) -> str:
        # ensure_ascii=False: 한국어를 \uXXXX 가 아닌 그대로 보낸다
        return json.dumps(self.to_dict(), ensure_ascii=False)
