"""AC-1: 설치 후 명령 하나로 모의 모드 루프가 끝까지 돈다 (`uv run agent-loop --cli --mock "..."`)."""

import os
import subprocess
import sys
import time
from pathlib import Path

# uv가 가상환경에 만들어 둔 진입점 스크립트(= uv run agent-loop 가 실행하는 것)
AGENT_LOOP = Path(sys.executable).parent / "agent-loop"


def run_cli(*args: str, extra_env: dict | None = None) -> tuple[subprocess.CompletedProcess, float]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", **(extra_env or {})}
    env.pop("AGENT_MODE", None)
    started = time.perf_counter()
    proc = subprocess.run([str(AGENT_LOOP), *args], capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)
    return proc, time.perf_counter() - started


def test_cli_mock_chain():
    proc, seconds = run_cli("--cli", "--mock", "가장 재고가 많은 과일의 가격은 얼마야?")
    out = proc.stdout
    assert proc.returncode == 0, proc.stderr
    assert seconds < 10, f"{seconds:.1f}초 걸림"
    for expected in ["[도구 호출] list_items", "[도구 호출] get_price", "[관찰]", "[최종 답]", "1,500원"]:
        assert expected in out, expected


def test_cli_auto_falls_back_without_ollama():
    # 모드를 정하지 않으면 auto: Ollama가 없으니 모의 모드로 내려가서 끝까지 돈다
    proc, _ = run_cli("--cli", "수박 재고 있어?", extra_env={"OLLAMA_HOST": "http://127.0.0.1:9", "MOCK_DELAY_MS": "0"})
    assert proc.returncode == 0, proc.stderr
    assert "Ollama에 연결할 수 없어 모의 모드로 실행합니다" in proc.stdout
    assert "[관찰·오류]" in proc.stdout and "[최종 답]" in proc.stdout
