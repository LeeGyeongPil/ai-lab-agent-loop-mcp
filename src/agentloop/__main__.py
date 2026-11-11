"""진입점 — `uv run agent-loop` (웹) 또는 `uv run agent-loop --cli "질문"` (터미널).

    uv run agent-loop                    # 웹 화면 (http://127.0.0.1:8765), 브라우저가 열린다
    uv run agent-loop --mock             # 모의 모드로 강제
    uv run agent-loop --lang ko ...      # 화면 언어: en | ko (AGENT_LOOP_LANG, LANG 으로도 정한다)
    uv run agent-loop --cli --mock "가장 재고가 많은 과일의 가격은 얼마야?"
    uv run agent-loop --mock --host 0.0.0.0 --no-browser   # 컨테이너·다른 기기에서 접속할 때
"""

import argparse
import asyncio
import ipaddress
import logging
import os
import socket
import sys

from agentloop.config import load_settings, resolve_mode_notices
from agentloop.i18n import LANGS, resolve_lang, t


DEFAULT_HOST = "127.0.0.1"
# 모든 네트워크 주소에서 받겠다는 뜻의 특수 주소. 브라우저 주소창에는 그대로 쓸 수 없다.
ANY_ADDRESS = {"0.0.0.0": "127.0.0.1", "::": "[::1]", "": "127.0.0.1"}


def describe_host(host: str, port: int, lang: str = "en") -> tuple[str, str | None]:
    """웹 서버를 열 주소 → (브라우저에 넣을 주소, 경고 문구 또는 None).

    127.0.0.1·localhost 처럼 내 PC 안에서만 닿는 주소면 경고가 없다.
    그 밖의 주소(특히 0.0.0.0)는 같은 네트워크의 다른 기기도 접속할 수 있으므로 경고한다.
    """
    if host in ANY_ADDRESS:
        url = f"http://{ANY_ADDRESS[host]}:{port}"
        where = t(lang, "main.where_any")
    else:
        shown = f"[{host}]" if ":" in host else host  # IPv6 주소는 대괄호로 감싼다
        url = f"http://{shown}:{port}"
        where = host
        if host == "localhost":
            return url, None
        try:
            if ipaddress.ip_address(host).is_loopback:
                return url, None
        except ValueError:
            pass  # 호스트 이름이면 루프백인지 알 수 없으니 경고한다
    warning = t(lang, "main.warning", where=where, host=host or t(lang, "main.all_addresses"))
    return url, warning


def port_is_free(host: str, port: int) -> bool:
    """host:port 를 잠깐 바인드해 보고 닫는다. 이미 쓰이고 있으면 False."""
    try:
        infos = socket.getaddrinfo(host or None, port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE)
    except socket.gaierror:
        return True  # 이름을 못 풀면 여기서 판단하지 않고 uvicorn 에 맡긴다
    family, socktype, proto, _, addr = infos[0]
    with socket.socket(family, socktype, proto) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # uvicorn 과 같은 옵션
        try:
            sock.bind(addr)
        except OSError:
            return False
    return True


def _lang_from_argv(argv: list[str] | None) -> str | None:
    """--lang 값만 먼저 읽는다(--help 문구도 그 언어로 보이게). 잘못된 값은 진짜 파서가 오류로 알린다."""
    pre = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    pre.add_argument("--lang")
    return pre.parse_known_args(argv)[0].lang


def parse_args(argv: list[str] | None = None, environ: dict | None = None) -> argparse.Namespace:
    lang = resolve_lang(_lang_from_argv(argv), os.environ if environ is None else environ)
    class Formatter(argparse.HelpFormatter):
        def add_usage(self, usage, actions, groups, prefix=None):
            # 기본 "usage: " 접두어를 언어 표의 문구로 바꾼다
            return super().add_usage(usage, actions, groups, t(lang, "main.usage_prefix"))

    parser = argparse.ArgumentParser(
        prog="agent-loop", description=t(lang, "main.description"), formatter_class=Formatter, add_help=False
    )
    # argparse 기본 그룹 제목·-h 문구도 언어 표에서 가져온다
    parser._positionals.title = t(lang, "main.positionals")
    parser._optionals.title = t(lang, "main.options")
    parser.add_argument("-h", "--help", action="help", help=t(lang, "main.help.help"))
    parser.add_argument("question", nargs="?", help=t(lang, "main.help.question"))
    parser.add_argument("--cli", action="store_true", help=t(lang, "main.help.cli"))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mock", action="store_true", help=t(lang, "main.help.mock"))
    group.add_argument("--real", action="store_true", help=t(lang, "main.help.real"))
    parser.add_argument("--port", type=int, help=t(lang, "main.help.port"))
    parser.add_argument("--host", default=DEFAULT_HOST, help=t(lang, "main.help.host", default=DEFAULT_HOST))
    parser.add_argument("--no-browser", action="store_true", help=t(lang, "main.help.no_browser"))
    parser.add_argument("--lang", choices=LANGS, help=t(lang, "main.help.lang"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    lang = resolve_lang(args.lang, os.environ)  # --lang > AGENT_LOOP_LANG > LC_ALL > LC_MESSAGES > LANG
    settings = load_settings()
    if args.mock:
        settings.mode = "mock"
    elif args.real:
        settings.mode = "real"
    if args.port:
        settings.port = args.port

    mode, notices = resolve_mode_notices(settings)  # auto면 여기서 Ollama를 확인해 real/mock 을 정한다
    print(notices[lang], flush=True)

    if args.cli:
        from agentloop.cli import run_cli
        from agentloop.mock_llm import load_scenarios

        question = args.question or load_scenarios(settings.scenarios_dir)[0]["question"]
        try:
            return asyncio.run(run_cli(question, settings, mode, lang))
        except KeyboardInterrupt:
            print("\n" + t(lang, "main.cancelled"))
            return 130

    import uvicorn

    from agentloop.web import create_app

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # Ollama 요청마다 찍히는 줄은 숨긴다
    # 포트가 이미 쓰이고 있으면 브라우저를 열기 전에 멈춘다(uvicorn 은 바인드보다 앱 시작을 먼저 실행한다).
    if not port_is_free(args.host, settings.port):
        print(t(lang, "main.port_busy", port=settings.port), file=sys.stderr, flush=True)
        return 2
    # 기본 host는 127.0.0.1: 내 PC에서만 접속된다(이 앱은 MCP 서버 = 내 PC의 프로그램을 실행한다).
    url, warning = describe_host(args.host, settings.port, lang)
    if warning:
        print(warning, flush=True)
    print(t(lang, "main.address", url=url), flush=True)
    if warning and args.host in ANY_ADDRESS:
        print(t(lang, "main.other_device", port=settings.port), flush=True)
    app = create_app(settings, mode, notices, open_browser=not args.no_browser, url=url, lang=lang)
    uvicorn.run(app, host=args.host, port=settings.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
