"""Multi-language support (English / Korean): message tables, language choice, CLI output, web API.

The default language is English; Korean is chosen with `--lang ko`, `AGENT_LOOP_LANG=ko` or a `ko*` locale.
Machine-readable output (event JSON, exit codes, MCP tool names/schemas) must not depend on the language.
"""

import json
import re
from urllib.parse import quote

import pytest
from starlette.testclient import TestClient
from test_cli import run_cli

from agentloop.agent import run_agent
from agentloop.config import PROJECT_ROOT
from agentloop.i18n import MESSAGES, resolve_lang, t
from agentloop.mcp_hub import load_server_params
from agentloop.mock_llm import ScriptedLLM
from agentloop.web import create_app

STATIC = PROJECT_ROOT / "src" / "agentloop" / "static"
SHOP_Q = "수박 재고 있어?"
CHAIN_Q = "가장 재고가 많은 과일의 가격은 얼마야?"
PLACEHOLDER = re.compile(r"\{(\w+)\}")
HANGUL = re.compile("[가-힣]")


# ── message tables ─────────────────────────────────────────────


def js_tables() -> dict[str, dict[str, str]]:
    """Read the en/ko tables out of app.js (no JS runtime needed)."""
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    start = source.index("const MESSAGES = {")
    body = source[start : source.index("\n};", start)]
    en_at, ko_at = body.index("\n  en: {"), body.index("\n  ko: {")
    entry = re.compile(r'^\s+"([^"]+)":\s*"((?:[^"\\]|\\.)*)"', re.MULTILINE)
    return {
        "en": dict(entry.findall(body[en_at:ko_at])),
        "ko": dict(entry.findall(body[ko_at:])),
    }


def test_python_tables_have_same_keys_and_placeholders():
    en, ko = MESSAGES["en"], MESSAGES["ko"]
    assert set(en) == set(ko), set(en) ^ set(ko)
    for key in en:
        assert set(PLACEHOLDER.findall(en[key])) == set(PLACEHOLDER.findall(ko[key])), key
        assert en[key].strip() and ko[key].strip(), key


def test_js_tables_have_same_keys_and_placeholders():
    tables = js_tables()
    en, ko = tables["en"], tables["ko"]
    assert len(en) > 50
    assert set(en) == set(ko), set(en) ^ set(ko)
    for key in en:
        assert set(PLACEHOLDER.findall(en[key])) == set(PLACEHOLDER.findall(ko[key])), key


def test_english_tables_have_no_hangul():
    # The English UI must not leak Korean text (example questions are demo data and come from the server).
    assert [k for k, v in js_tables()["en"].items() if HANGUL.search(v)] == []
    assert [k for k, v in MESSAGES["en"].items() if HANGUL.search(v)] == []


def test_html_and_js_only_use_known_keys():
    keys = set(js_tables()["en"])
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    used = set(re.findall(r'data-i18n(?:-title|-placeholder|-aria)?="([^"]+)"', html))
    assert used and used <= keys, used - keys
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    called = set(re.findall(r'\btr\("([^"]+)"', js))
    assert called <= keys, called - keys
    # The HTML itself ships English text (no flash of untranslated UI); only the language menu says 한국어.
    visible = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL).replace(">한국어<", "><")
    assert not HANGUL.search(visible)


def test_web_has_language_switch_and_storage():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="lang-select"' in html and ">English<" in html and ">한국어<" in html
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert '"agentloop.lang"' in js and "localStorage.setItem" in js and "localStorage.getItem" in js
    assert "navigator.language" in js  # first visit only; a saved choice wins


# ── language choice ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cli", "env", "expected"),
    [
        ("ko", {"AGENT_LOOP_LANG": "en", "LANG": "en_US.UTF-8"}, "ko"),  # --lang beats everything
        ("en", {"AGENT_LOOP_LANG": "ko", "LC_ALL": "ko_KR.UTF-8"}, "en"),
        (None, {"AGENT_LOOP_LANG": "ko", "LC_ALL": "en_US.UTF-8"}, "ko"),  # tool variable beats locale
        (None, {"AGENT_LOOP_LANG": "en", "LC_ALL": "ko_KR.UTF-8"}, "en"),
        (None, {"LC_ALL": "ko_KR.UTF-8", "LC_MESSAGES": "en_US", "LANG": "en_US"}, "ko"),  # LC_ALL first
        (None, {"LC_MESSAGES": "ko_KR", "LANG": "en_US.UTF-8"}, "ko"),  # then LC_MESSAGES
        (None, {"LANG": "ko_KR.UTF-8"}, "ko"),
        (None, {"LANG": "en_US.UTF-8"}, "en"),
        (None, {"LANG": "C"}, "en"),
        (None, {"LANG": "POSIX"}, "en"),
        (None, {"LANG": "fr_FR.UTF-8"}, "en"),  # not Korean -> English
        (None, {"LANG": ""}, "en"),
        (None, {}, "en"),
        (None, {"AGENT_LOOP_LANG": "fr", "LANG": "ko_KR.UTF-8"}, "ko"),  # invalid tool value is ignored
        (None, {"AGENT_LOOP_LANG": "", "LANG": "ko_KR.UTF-8"}, "ko"),
        ("xx", {"LANG": "ko_KR.UTF-8"}, "ko"),  # invalid --lang falls through (argparse rejects it earlier)
    ],
)
def test_resolve_lang_priority(cli, env, expected):
    assert resolve_lang(cli, env) == expected


def test_t_fills_placeholders_and_falls_back_to_english():
    assert t("en", "web.bad_question", max=500) == "Enter a question of 1 to 500 characters."
    assert t("ko", "web.bad_question", max=500) == "질문은 1~500자로 입력하세요."
    assert t("fr", "web.busy") == t("en", "web.busy")  # unknown language -> English
    with pytest.raises(KeyError):
        t("en", "no.such.key")


# ── CLI ────────────────────────────────────────────────────────


def test_cli_lang_en_prints_english_labels():
    proc, _ = run_cli("--lang", "en", "--cli", "--mock", SHOP_Q, extra_env={"MOCK_DELAY_MS": "0"})
    out = proc.stdout
    assert proc.returncode == 0, proc.stderr
    for expected in ["Mode: mock", "[Step 1][Tool call] check_stock", "[Observation-error]", "[Final answer]", "[End] answered", "[Server log]"]:
        assert expected in out, expected
    for korean_label in ["[회차", "[최종 답]", "[도구 호출]", "[끝]", "모드:", "[서버 로그]"]:
        assert korean_label not in out, korean_label


def test_cli_default_is_english_without_korean_locale():
    proc, _ = run_cli("--cli", "--mock", SHOP_Q, extra_env={"MOCK_DELAY_MS": "0", "LANG": "C"})
    assert proc.returncode == 0, proc.stderr
    assert "[Final answer]" in proc.stdout and "[최종 답]" not in proc.stdout


def test_cli_korean_locale_and_env_selection():
    env = {"MOCK_DELAY_MS": "0"}
    proc, _ = run_cli("--cli", "--mock", SHOP_Q, extra_env={**env, "LANG": "ko_KR.UTF-8"})
    assert proc.returncode == 0 and "[최종 답]" in proc.stdout and "[Final answer]" not in proc.stdout

    proc, _ = run_cli("--cli", "--mock", SHOP_Q, extra_env={**env, "LANG": "ko_KR.UTF-8", "AGENT_LOOP_LANG": "en"})
    assert "[Final answer]" in proc.stdout  # the tool's variable beats the locale

    proc, _ = run_cli("--lang", "ko", "--cli", "--mock", SHOP_Q, extra_env={**env, "AGENT_LOOP_LANG": "en"})
    assert "[최종 답]" in proc.stdout  # --lang beats the variable


def test_cli_invalid_lang_is_rejected_with_exit_code_2():
    proc, _ = run_cli("--lang", "xx", "--cli", "--mock", "hi")
    assert proc.returncode == 2
    assert "invalid choice" in proc.stderr


def test_cli_help_follows_language():
    en, _ = run_cli("--help", extra_env={"LANG": "C"})
    ko, _ = run_cli("--lang", "ko", "--help", extra_env={"LANG": "C"})
    assert en.returncode == ko.returncode == 0
    assert "--lang" in en.stdout and "Display language" in en.stdout and not HANGUL.search(en.stdout)
    assert "화면 언어" in ko.stdout and "--lang" in ko.stdout
    from_env, _ = run_cli("--help", extra_env={"AGENT_LOOP_LANG": "ko"})
    assert "화면 언어" in from_env.stdout


def test_cli_config_error_message_follows_language(tmp_path):
    missing = {"AGENT_MODE": "mock", "MCP_SERVERS_FILE": str(tmp_path / "nope.json")}
    en, _ = run_cli("--lang", "en", "--cli", extra_env=missing)
    ko, _ = run_cli("--lang", "ko", "--cli", extra_env=missing)
    assert en.returncode == ko.returncode == 1  # exit code does not depend on the language
    assert "[Error] MCP server config file not found: nope.json" in en.stdout
    assert "[오류] MCP 서버 설정 파일이 없습니다: nope.json" in ko.stdout


# ── machine-readable output stays the same ─────────────────────


async def run_events(settings, question: str, lang: str, servers_file=None) -> list[dict]:
    events = []

    async def emit(event):
        events.append(event.to_dict())

    llm = ScriptedLLM(settings.scenarios_dir, delay_ms=0, lang=lang)
    params = load_server_params(servers_file or settings.servers_file, lang=lang)
    await run_agent(question, llm, params, max_steps=6, mode="mock", emit=emit, lang=lang)
    return events


@pytest.mark.anyio
@pytest.mark.parametrize("question", [CHAIN_Q, SHOP_Q])
async def test_event_stream_does_not_depend_on_language(settings, question):
    en, ko = await run_events(settings, question, "en"), await run_events(settings, question, "ko")
    assert [(e["type"], e["step"]) for e in en] == [(e["type"], e["step"]) for e in ko]
    assert [sorted(e) for e in en] == [sorted(e) for e in ko]  # same field names
    assert en[-1]["stop_reason"] == ko[-1]["stop_reason"] == "answer"
    # only the display name of the mock model differs
    assert en[0]["model"] == "Mock LLM (scripted)" and ko[0]["model"] == "모의 LLM (대본)"
    # MCP observations and the scripted demo data are untouched
    observations = [[e["observation"] for e in events if e["type"] == "tool_result"] for events in (en, ko)]
    assert observations[0] == observations[1]


@pytest.mark.anyio
async def test_error_event_follows_language(settings, tmp_path):
    shop = str(PROJECT_ROOT / "servers" / "shop_server.py")
    clash = tmp_path / "dup.json"
    servers = {"a": {"command": "python", "args": [shop]}, "b": {"command": "python", "args": [shop]}}
    clash.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    errors = {}
    for lang in ("en", "ko"):
        events = await run_events(settings, CHAIN_Q, lang, servers_file=clash)
        errors[lang] = next(e for e in events if e["type"] == "error")
    assert "exists on both server" in errors["en"]["message"] and errors["en"]["hint"].startswith("Check mcp_servers.json")
    assert "모두 있습니다" in errors["ko"]["message"] and errors["ko"]["hint"].startswith("mcp_servers.json")
    assert set(errors["en"]) == set(errors["ko"])


# ── web API ────────────────────────────────────────────────────


@pytest.fixture
def web(settings):
    notices = {"en": "Mode: mock (test)", "ko": "모드: 모의 (테스트)"}
    with TestClient(create_app(settings, "mock", notices)) as c:
        yield c


def test_api_config_notice_follows_lang_query_and_keys_are_stable(web):
    default = web.get("/api/config").json()
    en = web.get("/api/config?lang=en").json()
    ko = web.get("/api/config?lang=ko").json()
    bogus = web.get("/api/config?lang=xx").json()
    assert default["notice"] == en["notice"] == bogus["notice"] == "Mode: mock (test)"
    assert ko["notice"] == "모드: 모의 (테스트)"
    assert set(default) == set(ko) == {"mode", "notice", "model", "max_steps", "examples", "system_prompt", "system_prompt_ko"}
    assert default["examples"] == ko["examples"]  # Korean demo data stays Korean in the English UI


def test_server_start_language_is_the_default_for_requests(settings):
    with TestClient(create_app(settings, "mock", {"en": "e", "ko": "k"}, lang="ko")) as c:
        assert c.get("/api/config").json()["notice"] == "k"
        assert c.get("/api/config?lang=en").json()["notice"] == "e"
        assert c.get("/api/run?q=").json()["error"] == "질문은 1~500자로 입력하세요."


def test_run_errors_follow_lang_with_same_status_codes_and_keys(web):
    cases = [
        ("/api/run?q=", 400, "Enter a question of 1 to 500 characters.", "질문은 1~500자로 입력하세요."),
        ("/api/run?q=hi&mode=cloud", 400, "mode must be mock or real.", "mode는 mock 또는 real 입니다."),
    ]
    for url, status, en_text, ko_text in cases:
        en = web.get(url)
        ko = web.get(url + ("&" if "?" in url else "?") + "lang=ko")
        assert en.status_code == ko.status_code == status
        assert list(en.json()) == list(ko.json()) == ["error"]
        assert (en.json()["error"], ko.json()["error"]) == (en_text, ko_text)


def test_api_tools_error_follows_lang(settings, tmp_path):
    settings.servers_file = tmp_path / "missing.json"
    with TestClient(create_app(settings, "mock", "n")) as c:
        en = c.get("/api/tools")
        ko = c.get("/api/tools?lang=ko")
    assert en.status_code == ko.status_code == 500
    assert en.json()["error"] == "MCP server config file not found: missing.json"
    assert ko.json()["error"] == "MCP 서버 설정 파일이 없습니다: missing.json"


def test_run_stream_has_same_events_in_both_languages(web):
    url = f"/api/run?q={quote(SHOP_Q)}&mode=mock"
    bodies = {}
    for lang in ("en", "ko"):
        with web.stream("GET", f"{url}&lang={lang}") as response:
            assert response.status_code == 200
            bodies[lang] = "".join(response.iter_text())
    names = {lang: re.findall(r"^event: (\w+)\r?$", body, re.MULTILINE) for lang, body in bodies.items()}
    assert names["en"] == names["ko"] and "run_end" in names["en"]
    assert "Mock LLM (scripted)" in bodies["en"] and "모의 LLM (대본)" in bodies["ko"]


# ── hygiene ────────────────────────────────────────────────────


def test_no_local_user_paths_in_repo_text_files():
    needles = ["/" + "Users/", "/" + "home/"]
    roots = [PROJECT_ROOT / "tests", PROJECT_ROOT / "src", PROJECT_ROOT / "README.md", PROJECT_ROOT / "README.ko.md"]
    files = []
    for root in roots:
        if root.is_file():
            files.append(root)
        else:
            files += [p for p in root.rglob("*") if p.suffix in {".py", ".js", ".html", ".md", ".json"}]
    offenders = [str(p.relative_to(PROJECT_ROOT)) for p in files if any(n in p.read_text(encoding="utf-8") for n in needles)]
    assert offenders == [], offenders


def test_help_default_phrases_follow_language(capsys):
    """argparse's own phrases (usage:, group titles, -h text) are translated too."""
    import pytest

    from agentloop.__main__ import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--lang", "ko", "--help"], {})
    ko = capsys.readouterr().out
    for english in ("usage:", "positional arguments:", "options:", "show this help message and exit"):
        assert english not in ko
    assert "사용법: " in ko and "옵션:" in ko and "위치 인자:" in ko
    with pytest.raises(SystemExit):
        parse_args(["--help"], {"AGENT_LOOP_LANG": "ko"})  # env is applied before --help
    assert "사용법: " in capsys.readouterr().out


def test_help_english_is_identical_to_argparse_defaults(capsys):
    import argparse

    import pytest

    from agentloop.__main__ import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--help"], {})
    out = capsys.readouterr().out
    assert out.startswith("usage: agent-loop")
    assert "positional arguments:" in out and "options:" in out
    assert "  -h, --help      show this help message and exit" in out
    # byte-identical to a parser built with argparse's own defaults
    from agentloop import __main__ as m

    reference = argparse.ArgumentParser(prog="agent-loop", description=m.t("en", "main.description"))
    reference.add_argument("question", nargs="?", help=m.t("en", "main.help.question"))
    reference.add_argument("--cli", action="store_true", help=m.t("en", "main.help.cli"))
    group = reference.add_mutually_exclusive_group()
    group.add_argument("--mock", action="store_true", help=m.t("en", "main.help.mock"))
    group.add_argument("--real", action="store_true", help=m.t("en", "main.help.real"))
    reference.add_argument("--port", type=int, help=m.t("en", "main.help.port"))
    reference.add_argument("--host", default=m.DEFAULT_HOST, help=m.t("en", "main.help.host", default=m.DEFAULT_HOST))
    reference.add_argument("--no-browser", action="store_true", help=m.t("en", "main.help.no_browser"))
    reference.add_argument("--lang", choices=m.LANGS, help=m.t("en", "main.help.lang"))
    assert out == reference.format_help()
