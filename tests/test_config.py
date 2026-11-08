"""AC-9: Ollama가 없어도 첫 실행이 막히지 않는다(auto → mock 폴백)."""

from agentloop.config import FALLBACK_NOTICE, load_settings, resolve_mode


def test_auto_falls_back_to_mock():
    # 9번 포트(discard)에는 Ollama가 없다 → 연결 실패
    settings = load_settings({"AGENT_MODE": "auto", "OLLAMA_HOST": "http://127.0.0.1:9"})
    mode, notice = resolve_mode(settings)
    assert mode == "mock"
    assert "Ollama에 연결할 수 없어 모의 모드로 실행합니다" in notice
    assert FALLBACK_NOTICE in notice


def test_explicit_mock_skips_ollama_check():
    settings = load_settings({"AGENT_MODE": "mock", "OLLAMA_HOST": "http://127.0.0.1:9"})
    assert resolve_mode(settings)[0] == "mock"


def test_defaults():
    s = load_settings({})
    assert (s.mode, s.ollama_model, s.num_ctx, s.max_steps, s.port) == ("auto", "qwen3:4b", 8192, 8, 8765)
    assert s.servers_file.name == "mcp_servers.json" and s.servers_file.exists()
