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
    """pid의 자식 프로세스 목록. 없으면 빈 목록.

    pgrep에 기대지 않는다(작은 Linux 이미지에는 procps가 없다).
      - Linux: /proc/<번호>/stat 의 부모 번호(ppid)를 직접 읽는다
      - macOS 등: 기본으로 깔려 있는 `ps` 로 (pid, ppid) 표를 받는다
    """
    proc = Path("/proc")
    if (proc / "self" / "stat").exists():
        children = []
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                stat = (entry / "stat").read_text()
            except OSError:  # 읽는 사이에 끝난 프로세스
                continue
            # 형식: "번호 (이름) 상태 부모번호 ..." — 이름에 공백·괄호가 있을 수 있어 마지막 ')' 뒤부터 자른다
            fields = stat[stat.rfind(")") + 2 :].split()
            if int(fields[1]) == pid:
                children.append(entry.name)
        return sorted(children, key=int)

    with subprocess.Popen(["ps", "-A", "-o", "pid=,ppid="], stdout=subprocess.PIPE, text=True) as ps:
        output, _ = ps.communicate()
    rows = (line.split() for line in output.splitlines() if line.strip())
    # ps 자신도 이 순간에는 우리의 자식이므로 뺀다
    return [child for child, parent in rows if int(parent) == pid and int(child) != ps.pid]
