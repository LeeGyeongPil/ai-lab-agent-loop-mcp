"""설정 읽기와 실행 모드(auto/mock/real) 판정."""

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# 이 파일 위치(src/agentloop/config.py)에서 두 단계 위 = 저장소 루트.
# mcp_servers.json, servers/, scenarios/ 가 여기에 있다.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

FALLBACK_NOTICE = "Ollama에 연결할 수 없어 모의 모드로 실행합니다"


@dataclass
class Settings:
    mode: str  # auto / mock / real
    ollama_host: str
    ollama_model: str
    num_ctx: int
    max_steps: int
    port: int
    mock_delay_ms: int
    servers_file: Path
    scenarios_dir: Path


def _project_path(value: str) -> Path:
    """상대 경로는 현재 폴더에 있으면 그걸, 없으면 저장소 루트 기준으로 찾는다."""
    path = Path(value)
    if path.is_absolute() or path.exists():
        return path.resolve()
    return PROJECT_ROOT / path


def load_settings(environ: dict | None = None) -> Settings:
    """환경 변수에서 설정을 읽는다. 값이 없으면 기본값(.env.example 참고)."""
    env = os.environ if environ is None else environ
    return Settings(
        mode=env.get("AGENT_MODE", "auto").strip().lower(),
        ollama_host=env.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/"),
        ollama_model=env.get("OLLAMA_MODEL", "qwen3:4b"),
        num_ctx=int(env.get("OLLAMA_NUM_CTX", "8192")),
        max_steps=int(env.get("AGENT_MAX_STEPS", "8")),
        port=int(env.get("AGENT_PORT", "8765")),
        mock_delay_ms=int(env.get("MOCK_DELAY_MS", "25")),
        servers_file=_project_path(env.get("MCP_SERVERS_FILE", "mcp_servers.json")),
        scenarios_dir=PROJECT_ROOT / "scenarios",
    )


def _get_json(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_ollama(host: str, model: str, timeout: float = 3.0) -> str:
    """Ollama 상태를 확인한다. 결과: "ok" / "unreachable"(꺼져 있음) / "no_model"(모델 없음)."""
    try:
        _get_json(f"{host}/api/version", timeout)  # 1) 서버가 켜져 있나?
        tags = _get_json(f"{host}/api/tags", timeout)  # 2) 모델을 받아 두었나?
    except (OSError, ValueError):
        return "unreachable"
    names = {m.get("name") for m in tags.get("models", [])}
    wanted = model if ":" in model else f"{model}:latest"
    return "ok" if wanted in names else "no_model"


def resolve_mode(settings: Settings) -> tuple[str, str]:
    """실제로 쓸 모드("mock"/"real")와 터미널에 보여 줄 안내 문구를 정한다."""
    model = settings.ollama_model
    if settings.mode == "mock":
        return "mock", "모드: 모의 (AGENT_MODE=mock — 대본대로 움직이는 가짜 LLM + 진짜 MCP 서버)"

    status = check_ollama(settings.ollama_host, model)
    if settings.mode == "real":
        if status == "ok":
            return "real", f"모드: 실제 (Ollama {model})"
        return "real", f"모드: 실제 (Ollama {model}) — 경고: Ollama 또는 모델을 찾지 못했습니다. 실행하면 오류 안내가 나옵니다."

    # auto: 쓸 수 있으면 실제, 아니면 모의로 내려간다(첫 실행이 막히지 않게).
    if status == "ok":
        return "real", f"모드: 실제 (Ollama {model})"
    if status == "no_model":
        return "mock", f"모드: 모의 (Ollama에 {model} 모델이 없어 모의 모드로 실행합니다. 받으려면: ollama pull {model})"
    return "mock", f"모드: 모의 ({FALLBACK_NOTICE})"
