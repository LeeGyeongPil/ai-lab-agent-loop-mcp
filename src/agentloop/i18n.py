"""Display-language support for the CLI and the server-generated texts (English / Korean).

All user-visible Python strings live in ``MESSAGES`` below, one table per language.
The browser UI has its own table at the top of ``static/app.js`` (same idea, one place).

What is *not* translated: event type/field names, MCP tool names and schemas, the scenario
scripts (Korean demo data), log lines and the system prompt sent to the model.

Language choice for the CLI: ``--lang en|ko`` > ``AGENT_LOOP_LANG`` > ``LC_ALL`` >
``LC_MESSAGES`` > ``LANG``. Anything that is not Korean falls back to English.
"""

import os
from collections.abc import Mapping

LANGS = ("en", "ko")
DEFAULT_LANG = "en"
ENV_VAR = "AGENT_LOOP_LANG"

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        # --- __main__.py ---
        "main.description": "Shows an agent loop that uses MCP tools, one step at a time.",
        "main.help.question": "Question to ask in --cli mode",
        "main.help.cli": "Print a text timeline in the terminal instead of opening the web UI",
        "main.help.mock": "Mock mode (scripted LLM + real MCP servers)",
        "main.help.real": "Real mode (local Ollama)",
        "main.help.port": "Web port (default 8765)",
        "main.help.host": "Address to serve the web UI on (default {default} = reachable from this PC only). "
        "0.0.0.0 is reachable from other devices too",
        "main.help.no_browser": "Do not open the browser automatically",
        "main.help.lang": "Display language (default: taken from AGENT_LOOP_LANG, LC_ALL, LC_MESSAGES, "
        "LANG in that order; English unless Korean)",
        "main.usage_prefix": "usage: ",
        "main.positionals": "positional arguments",
        "main.options": "options",
        "main.help.help": "show this help message and exit",
        "main.where_any": "all network addresses of this PC",
        "main.all_addresses": "all addresses",
        "main.warning": "Warning: the web server listens on {where} ({host}). Other devices on the same network "
        "can connect and run questions (= MCP server programs run on this PC). "
        "Use it only on a network you trust.",
        "main.cancelled": "[Stopped] The run was cancelled.",
        "main.port_busy": "Error: port {port} is in use by another program. "
        "Change it with --port 9000 or AGENT_PORT=9000.",
        "main.address": "Address: {url}  (press Ctrl+C to quit)",
        "main.other_device": "      From other devices, open http://<this PC's IP address>:{port}",
        # --- config.py ---
        "config.mode_mock": "Mode: mock (AGENT_MODE=mock - a scripted fake LLM + real MCP servers)",
        "config.mode_real": "Mode: real (Ollama {model})",
        "config.mode_real_warn": "Mode: real (Ollama {model}) - warning: Ollama or the model was not found. "
        "Running will show an error with a hint.",
        "config.mode_no_model": "Mode: mock (Ollama has no {model} model, so running in mock mode. "
        "To get it: ollama pull {model})",
        "config.mode_fallback": "Mode: mock ({fallback})",
        "config.fallback": "Cannot reach Ollama, so running in mock mode",
        # --- cli.py ---
        "cli.question": "Question: {question}  (model: {model})",
        "cli.prepared": "[Ready] MCP servers: {servers} connected - tools: {tools} ({names}) - {seconds}",
        "cli.head": "[Step {step}]",
        "cli.thinking": "[Thinking] ",
        "cli.seconds": "{seconds}s",
        "cli.duplicate": " (duplicate call)",
        "cli.tool_call": "[Tool call] {name} {arguments} -> server {server}{mark}",
        "cli.observe": "[Observation]",
        "cli.observe_error": "[Observation-error]",
        "cli.answer": "[Final answer]",
        "cli.error": "[Error] {message}",
        "cli.hint": "[Fix] {hint}",
        "cli.end": "[End] {reason} - steps {steps} - tool calls {tool_calls} - errors {errors} - total {seconds}",
        "cli.stop.answer": "answered",
        "cli.stop.max_steps": "max steps reached",
        "cli.stop.error": "error",
        "cli.stop.cancelled": "cancelled",
        "cli.server_log": "[Server log] The MCP servers wrote {count} log line(s) to {path}.",
        # --- agent.py ---
        "agent.empty_answer": "(the model returned an empty answer)",
        "agent.hint_config": "Check mcp_servers.json and the server code in the servers/ folder.",
        "agent.hint_ollama_down": "Ollama is not running. Run `ollama serve` in a terminal, or switch to mock mode.",
        "agent.hint_no_model": "The model is missing. Run `ollama pull qwen3:4b`, then try again.",
        # --- mock_llm.py ---
        "mock.name": "Mock LLM (scripted)",
        "mock.no_script_thinking": "No script matches this question. Let me answer with the guidance text.",
        "mock.no_script_answer": "Mock mode only has scripts for the 3 example questions. "
        "Run in real mode (Ollama) to ask anything.",
        # --- mcp_hub.py ---
        "hub.no_config": "MCP server config file not found: {name}",
        "hub.bad_json": "{name} is not valid JSON: {error}",
        "hub.empty_servers": '{name} has an empty "mcpServers" section.',
        "hub.name_clash": "Tool name '{tool}' exists on both server '{first}' and '{second}'. "
        "Rename the tool on one of them.",
        # --- web.py ---
        "web.bad_question": "Enter a question of 1 to {max} characters.",
        "web.bad_mode": "mode must be mock or real.",
        "web.busy": "Another run is in progress. Try again when it finishes.",
    },
    "ko": {
        # --- __main__.py ---
        "main.description": "MCP 도구를 쓰는 에이전트 루프를 한 단계씩 보여 줍니다.",
        "main.help.question": "--cli 모드에서 물어볼 질문",
        "main.help.cli": "웹 대신 터미널에 텍스트 타임라인을 찍는다",
        "main.help.mock": "모의 모드(대본 LLM + 진짜 MCP 서버)",
        "main.help.real": "실제 모드(로컬 Ollama)",
        "main.help.port": "웹 포트(기본 8765)",
        "main.help.host": "웹 서버를 열 주소(기본 {default} = 내 PC에서만 접속). 0.0.0.0 은 다른 기기에서도 접속된다",
        "main.help.no_browser": "브라우저를 자동으로 열지 않는다",
        "main.help.lang": "화면 언어(기본: AGENT_LOOP_LANG, LC_ALL, LC_MESSAGES, LANG 순으로 정하며, 한국어가 아니면 영어)",
        "main.usage_prefix": "사용법: ",
        "main.positionals": "위치 인자",
        "main.options": "옵션",
        "main.help.help": "이 도움말을 보여 주고 종료한다",
        "main.where_any": "이 PC의 모든 네트워크 주소",
        "main.all_addresses": "모든 주소",
        "main.warning": "경고: 웹 서버를 {where}({host})에 엽니다. 같은 네트워크의 다른 기기도 접속해서 "
        "질문을 실행할 수 있습니다(= 이 PC에서 MCP 서버 프로그램이 실행됩니다). 믿을 수 있는 네트워크에서만 쓰세요.",
        "main.cancelled": "[중지] 실행을 취소했습니다.",
        "main.port_busy": "오류: 포트 {port} 을(를) 다른 프로그램이 쓰고 있습니다. "
        "--port 9000 또는 AGENT_PORT=9000 으로 바꾸세요.",
        "main.address": "주소: {url}  (끝내려면 Ctrl+C)",
        "main.other_device": "      다른 기기에서는 http://<이 PC의 IP 주소>:{port} 로 접속합니다.",
        # --- config.py ---
        "config.mode_mock": "모드: 모의 (AGENT_MODE=mock — 대본대로 움직이는 가짜 LLM + 진짜 MCP 서버)",
        "config.mode_real": "모드: 실제 (Ollama {model})",
        "config.mode_real_warn": "모드: 실제 (Ollama {model}) — 경고: Ollama 또는 모델을 찾지 못했습니다. "
        "실행하면 오류 안내가 나옵니다.",
        "config.mode_no_model": "모드: 모의 (Ollama에 {model} 모델이 없어 모의 모드로 실행합니다. "
        "받으려면: ollama pull {model})",
        "config.mode_fallback": "모드: 모의 ({fallback})",
        "config.fallback": "Ollama에 연결할 수 없어 모의 모드로 실행합니다",
        # --- cli.py ---
        "cli.question": "질문: {question}  (모델: {model})",
        "cli.prepared": "[준비] MCP 서버 {servers}개 연결 · 도구 {tools}개 ({names}) · {seconds}",
        "cli.head": "[회차 {step}]",
        "cli.thinking": "[생각] ",
        "cli.seconds": "{seconds}초",
        "cli.duplicate": " (중복 호출)",
        "cli.tool_call": "[도구 호출] {name} {arguments} → 서버 {server}{mark}",
        "cli.observe": "[관찰]",
        "cli.observe_error": "[관찰·오류]",
        "cli.answer": "[최종 답]",
        "cli.error": "[오류] {message}",
        "cli.hint": "[해결] {hint}",
        "cli.end": "[끝] {reason} · 회차 {steps} · 도구 호출 {tool_calls} · 오류 {errors} · 총 {seconds}",
        "cli.stop.answer": "답을 냄",
        "cli.stop.max_steps": "최대 회차 도달",
        "cli.stop.error": "오류",
        "cli.stop.cancelled": "취소됨",
        "cli.server_log": "[서버 로그] MCP 서버가 남긴 로그 {count}줄은 {path} 에 있습니다.",
        # --- agent.py ---
        "agent.empty_answer": "(모델이 빈 답을 냈습니다)",
        "agent.hint_config": "mcp_servers.json 과 servers/ 폴더의 서버 코드를 확인하세요.",
        "agent.hint_ollama_down": "Ollama가 꺼져 있습니다. 터미널에서 `ollama serve`를 실행하거나, 모드를 모의로 바꾸세요.",
        "agent.hint_no_model": "모델이 없습니다. `ollama pull qwen3:4b`로 받은 뒤 다시 실행하세요.",
        # --- mock_llm.py ---
        "mock.name": "모의 LLM (대본)",
        "mock.no_script_thinking": "이 질문에 맞는 대본이 없다. 안내 문구로 답하자.",
        "mock.no_script_answer": "모의 모드는 예시 질문 3개만 대본이 있습니다. "
        "실제 모드(Ollama)로 실행하면 아무 질문이나 할 수 있습니다.",
        # --- mcp_hub.py ---
        "hub.no_config": "MCP 서버 설정 파일이 없습니다: {name}",
        "hub.bad_json": "{name} 의 JSON 형식이 잘못됐습니다: {error}",
        "hub.empty_servers": '{name} 에 "mcpServers" 항목이 비어 있습니다.',
        "hub.name_clash": "도구 이름 '{tool}' 이(가) 서버 '{first}' 와 '{second}' 에 모두 있습니다. "
        "한쪽 도구 이름을 바꾸세요.",
        # --- web.py ---
        "web.bad_question": "질문은 1~{max}자로 입력하세요.",
        "web.bad_mode": "mode는 mock 또는 real 입니다.",
        "web.busy": "다른 실행이 진행 중입니다. 끝난 뒤 다시 시도하세요.",
    },
}


def normalize_lang(value: str | None) -> str | None:
    """Return ``"en"`` / ``"ko"`` for a recognised value, otherwise ``None``."""
    if value is None:
        return None
    value = value.strip().lower()
    return value if value in LANGS else None


def _lang_from_locale(value: str | None) -> str | None:
    """Locale variable (``ko_KR.UTF-8``, ``C``, ``en_US``...) -> ``"ko"`` / ``"en"`` / ``None`` if unset."""
    if value is None or not value.strip():
        return None
    return "ko" if value.strip().lower().startswith("ko") else "en"


def resolve_lang(cli_value: str | None = None, environ: Mapping[str, str] | None = None) -> str:
    """Pick the display language.

    Order: ``--lang`` value > ``AGENT_LOOP_LANG`` (ignored unless ``en``/``ko``) >
    ``LC_ALL`` > ``LC_MESSAGES`` > ``LANG``. A locale starting with ``ko`` means Korean; anything
    else (``C``, ``POSIX``, ``en_US``...) means English. Nothing set -> English.
    """
    env = os.environ if environ is None else environ
    explicit = normalize_lang(cli_value)
    if explicit:
        return explicit
    from_env = normalize_lang(env.get(ENV_VAR))
    if from_env:
        return from_env
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        found = _lang_from_locale(env.get(name))
        if found:
            return found
    return DEFAULT_LANG


def t(lang: str, key: str, **params) -> str:
    """Look up ``key`` in the ``lang`` table (unknown language -> English) and fill ``{placeholders}``."""
    table = MESSAGES.get(lang) or MESSAGES[DEFAULT_LANG]
    template = table.get(key)
    if template is None:
        template = MESSAGES[DEFAULT_LANG][key]  # KeyError here = a typo in the calling code
    return template.format(**params) if params else template
