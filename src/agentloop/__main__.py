"""진입점 — `uv run agent-loop` (웹) 또는 `uv run agent-loop --cli "질문"` (터미널).

    uv run agent-loop                    # 웹 화면 (http://127.0.0.1:8765), 브라우저가 열린다
    uv run agent-loop --mock             # 모의 모드로 강제
    uv run agent-loop --cli --mock "가장 재고가 많은 과일의 가격은 얼마야?"
"""

import argparse
import asyncio
import logging
import sys

from agentloop.config import load_settings, resolve_mode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agent-loop", description="MCP 도구를 쓰는 에이전트 루프를 한 단계씩 보여 줍니다.")
    parser.add_argument("question", nargs="?", help="--cli 모드에서 물어볼 질문")
    parser.add_argument("--cli", action="store_true", help="웹 대신 터미널에 텍스트 타임라인을 찍는다")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mock", action="store_true", help="모의 모드(대본 LLM + 진짜 MCP 서버)")
    group.add_argument("--real", action="store_true", help="실제 모드(로컬 Ollama)")
    parser.add_argument("--port", type=int, help="웹 포트(기본 8765, 127.0.0.1에만 열림)")
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
    url = f"http://127.0.0.1:{settings.port}"
    print(f"주소: {url}  (끝내려면 Ctrl+C)", flush=True)
    app = create_app(settings, mode, notice, open_browser=not args.no_browser)
    # host는 127.0.0.1 고정: 내 PC에서만 접속된다(이 앱은 MCP 서버 = 내 PC의 프로그램을 실행한다).
    uvicorn.run(app, host="127.0.0.1", port=settings.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
