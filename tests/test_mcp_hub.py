"""AC-6 · AC-8: 설정 파일로 서버 여러 개 붙이기, 이름 충돌, 하위 프로세스 정리 (진짜 stdio 연결)."""

import json
import os

import pytest
from conftest import child_pids

from agentloop.config import PROJECT_ROOT
from agentloop.mcp_hub import ConfigError, McpHub, load_server_params

pytestmark = pytest.mark.anyio


async def test_merge_two_servers(settings):
    async with McpHub(load_server_params(settings.servers_file)) as hub:
        assert hub.tool_names() == ["list_items", "check_stock", "get_price", "count_chars"]
        assert hub.server_of("count_chars") == "my_tools"
        assert [t["function"]["name"] for t in hub.ollama_tools()] == hub.tool_names()

        ok = await hub.call("count_chars", {"text": "에이전트 루프"})
        assert not ok.is_error and json.loads(ok.observation) == {"chars": 7, "chars_no_space": 6}
        assert ok.wire_response["structuredContent"] == {"chars": 7, "chars_no_space": 6}

        bad = await hub.call("check_stock", {"item": "수박"})
        assert bad.is_error and "known:" in bad.observation

        unknown = await hub.call("no_such_tool", {})
        assert unknown.is_error and "unknown tool" in unknown.observation


async def test_duplicate_tool_name_error(tmp_path):
    shop = str(PROJECT_ROOT / "servers" / "shop_server.py")
    config = tmp_path / "dup.json"
    config.write_text(
        json.dumps({"mcpServers": {"shop_a": {"command": "python", "args": [shop]}, "shop_b": {"command": "python", "args": [shop]}}}),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as info:
        async with McpHub(load_server_params(config)):
            pass
    assert "shop_a" in str(info.value) and "shop_b" in str(info.value)
    assert child_pids(os.getpid()) == []  # 실패해도 먼저 띄운 서버는 정리된다


async def test_bad_config_file(tmp_path):
    with pytest.raises(ConfigError):
        load_server_params(tmp_path / "missing.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_server_params(broken)


async def test_no_orphan_processes(settings):
    pid = os.getpid()
    async with McpHub(load_server_params(settings.servers_file)):
        assert len(child_pids(pid)) == 2  # 실행 중에는 서버 2개가 자식 프로세스로 떠 있다
    assert child_pids(pid) == []  # async with 를 벗어나면 남지 않는다


async def test_errlog_receives_server_stderr(settings, tmp_path):
    # errlog 파일을 주면 서버 로그가 터미널 대신 그 파일로 가고, 서버는 그대로 정리된다
    log_path = tmp_path / "servers.log"
    with log_path.open("w", encoding="utf-8") as errlog:
        async with McpHub(load_server_params(settings.servers_file), errlog=errlog) as hub:
            bad = await hub.call("check_stock", {"item": "수박"})
            assert bad.is_error
    assert child_pids(os.getpid()) == []
    assert "Tool 'check_stock' failed" in log_path.read_text(encoding="utf-8")
