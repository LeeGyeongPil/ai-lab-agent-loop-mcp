"""테스트 공용 준비물. 모든 테스트는 네트워크·모델 없이 모의 모드로 돈다(test_real_ollama 제외)."""

import subprocess
from pathlib import Path

import pytest

from agentloop.config import PROJECT_ROOT, load_settings

TESTS_DIR = Path(__file__).parent


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def settings():
    """기본 설정 + 모의 모드 + 지연 0 (빠르고 결정적)."""
    s = load_settings({"AGENT_MODE": "mock", "MOCK_DELAY_MS": "0"})
    assert s.servers_file == PROJECT_ROOT / "mcp_servers.json"
    return s


def child_pids(pid: int) -> list[str]:
    """pid의 자식 프로세스 목록 (`pgrep -P <pid>`). 없으면 빈 목록."""
    out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True)
    return out.stdout.split()
