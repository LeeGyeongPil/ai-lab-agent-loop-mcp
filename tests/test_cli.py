"""AC-1: 설치 후 명령 하나로 모의 모드 루프가 끝까지 돈다 (`uv run agent-loop --cli --mock "..."`)."""

import os
import subprocess
import sys
import time
from pathlib import Path

# uv가 가상환경에 만들어 둔 진입점 스크립트(= uv run agent-loop 가 실행하는 것)
AGENT_LOOP = Path(sys.executable).parent / "agent-loop"


def run_cli(*args: str, extra_env: dict | None = None) -> tuple[subprocess.CompletedProcess, float]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for name in ("AGENT_MODE", "AGENT_LOOP_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        env.pop(name, None)  # 바깥 환경의 언어·모드에 흔들리지 않게 비운다
    env.update(extra_env or {})
    started = time.perf_counter()
    proc = subprocess.run([str(AGENT_LOOP), *args], capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
    return proc, time.perf_counter() - started


def test_cli_mock_chain():
    # 벽시계 시간 단언은 부하에 따라 흔들려(간헐 실패) 뺐다. 끝까지 도는지는 종료코드와 출력으로 본다.
    proc, _ = run_cli("--lang", "ko", "--cli", "--mock", "가장 재고가 많은 과일의 가격은 얼마야?")
    out = proc.stdout
    assert proc.returncode == 0, proc.stderr
    for expected in ["[도구 호출] list_items", "[도구 호출] get_price", "[관찰]", "[최종 답]", "1,500원"]:
        assert expected in out, expected


def test_cli_auto_falls_back_without_ollama():
    # 모드를 정하지 않으면 auto: Ollama가 없으니 모의 모드로 내려가서 끝까지 돈다
    proc, _ = run_cli("--lang", "ko", "--cli", "수박 재고 있어?", extra_env={"OLLAMA_HOST": "http://127.0.0.1:9", "MOCK_DELAY_MS": "0"})
    assert proc.returncode == 0, proc.stderr
    assert "Ollama에 연결할 수 없어 모의 모드로 실행합니다" in proc.stdout
    assert "[관찰·오류]" in proc.stdout and "[최종 답]" in proc.stdout


def test_cli_server_stderr_kept_out_of_terminal():
    # 예시 2: 서버가 stderr에 "Tool 'check_stock' failed ..." 로그를 남긴다.
    # 이 줄이 "[생각] ..." 줄 사이에 끼어들지 않고 로그 파일로만 가야 한다.
    from agentloop.cli import SERVER_LOG_FILE

    proc, _ = run_cli("--lang", "ko", "--cli", "--mock", "수박 재고 있어?", extra_env={"MOCK_DELAY_MS": "0"})
    assert proc.returncode == 0, proc.stderr
    assert "failed" not in proc.stdout and "failed" not in proc.stderr
    timeline = [line for line in proc.stdout.splitlines() if line.startswith("[회차")]
    assert len(timeline) == 5  # 생각·도구 호출·관찰·생각·최종 답
    assert all(line.endswith("초)") for line in timeline if "[생각]" in line)  # 생각 줄이 중간에 끊기지 않았다
    assert "[서버 로그]" in proc.stdout and "runs/mcp-server-stderr.log" in proc.stdout
    assert "Tool 'check_stock' failed" in SERVER_LOG_FILE.read_text(encoding="utf-8")
