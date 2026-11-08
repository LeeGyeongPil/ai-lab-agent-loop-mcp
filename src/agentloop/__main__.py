"""진입점 — `uv run agent-loop` (웹) 또는 `uv run agent-loop --cli "질문"` (터미널).

    uv run agent-loop                    # 웹 화면 (http://127.0.0.1:8765), 브라우저가 열린다
    uv run agent-loop --mock             # 모의 모드로 강제
    uv run agent-loop --cli --mock "가장 재고가 많은 과일의 가격은 얼마야?"
    uv run agent-loop --mock --host 0.0.0.0 --no-browser   # 컨테이너·다른 기기에서 접속할 때
"""

import argparse
import asyncio
import ipaddress
import logging
import sys

from agentloop.config import load_settings, resolve_mode


DEFAULT_HOST = "127.0.0.1"
# 모든 네트워크 주소에서 받겠다는 뜻의 특수 주소. 브라우저 주소창에는 그대로 쓸 수 없다.
ANY_ADDRESS = {"0.0.0.0": "127.0.0.1", "::": "[::1]", "": "127.0.0.1"}


def describe_host(host: str, port: int) -> tuple[str, str | None]:
    """웹 서버를 열 주소 → (브라우저에 넣을 주소, 경고 문구 또는 None).

    127.0.0.1·localhost 처럼 내 PC 안에서만 닿는 주소면 경고가 없다.
    그 밖의 주소(특히 0.0.0.0)는 같은 네트워크의 다른 기기도 접속할 수 있으므로 경고한다.
    """
    if host in ANY_ADDRESS:
        url = f"http://{ANY_ADDRESS[host]}:{port}"
        where = "이 PC의 모든 네트워크 주소"
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
    warning = (
        f"경고: 웹 서버를 {where}({host or '모든 주소'})에 엽니다. 같은 네트워크의 다른 기기도 접속해서 "
        "질문을 실행할 수 있습니다(= 이 PC에서 MCP 서버 프로그램이 실행됩니다). 믿을 수 있는 네트워크에서만 쓰세요."
    )
    return url, warning


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agent-loop", description="MCP 도구를 쓰는 에이전트 루프를 한 단계씩 보여 줍니다.")
    parser.add_argument("question", nargs="?", help="--cli 모드에서 물어볼 질문")
    parser.add_argument("--cli", action="store_true", help="웹 대신 터미널에 텍스트 타임라인을 찍는다")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mock", action="store_true", help="모의 모드(대본 LLM + 진짜 MCP 서버)")
    group.add_argument("--real", action="store_true", help="실제 모드(로컬 Ollama)")
    parser.add_argument("--port", type=int, help="웹 포트(기본 8765)")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"웹 서버를 열 주소(기본 {DEFAULT_HOST} = 내 PC에서만 접속). 0.0.0.0 은 다른 기기에서도 접속된다",
    )
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않는다")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = load_settings()
    if args.mock:
        settings.mode = "mock"
    elif args.real:
        settings.mode = "real"
    if args.port:
        settings.port = args.port

    mode, notice = resolve_mode(settings)  # auto면 여기서 Ollama를 확인해 real/mock 을 정한다
    print(notice, flush=True)

    if args.cli:
        from agentloop.cli import run_cli
        from agentloop.mock_llm import load_scenarios

        question = args.question or load_scenarios(settings.scenarios_dir)[0]["question"]
        try:
            return asyncio.run(run_cli(question, settings, mode))
        except KeyboardInterrupt:
            print("\n[중지] 실행을 취소했습니다.")
            return 130

    import uvicorn

    from agentloop.web import create_app

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # Ollama 요청마다 찍히는 줄은 숨긴다
    # 기본 host는 127.0.0.1: 내 PC에서만 접속된다(이 앱은 MCP 서버 = 내 PC의 프로그램을 실행한다).
    url, warning = describe_host(args.host, settings.port)
    if warning:
        print(warning, flush=True)
    print(f"주소: {url}  (끝내려면 Ctrl+C)", flush=True)
    if warning and args.host in ANY_ADDRESS:
        print(f"      다른 기기에서는 http://<이 PC의 IP 주소>:{settings.port} 로 접속합니다.", flush=True)
    app = create_app(settings, mode, notice, open_browser=not args.no_browser, url=url)
    uvicorn.run(app, host=args.host, port=settings.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
