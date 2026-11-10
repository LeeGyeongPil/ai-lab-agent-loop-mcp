"""AC-7 · AC-8: 웹 API와 SSE 스트림, 동시 실행 락, 연결 끊김 시 취소·정리."""

import logging
import os
import time
from urllib.parse import quote

import pytest
from conftest import children_alive_as_expected, no_children
from starlette.testclient import TestClient

from agentloop.web import create_app

CHAIN_Q = "가장 재고가 많은 과일의 가격은 얼마야?"
RUN_URL = f"/api/run?q={quote(CHAIN_Q)}&mode=mock"


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, "mock", "모드: 모의 (테스트)")) as c:
        yield c


@pytest.fixture
def slow_client(settings):
    """모의 모드 지연을 줘서 실행이 몇 초 걸리게 한 앱 (락·끊김 시험용)."""
    settings.mock_delay_ms = 40
    with TestClient(create_app(settings, "mock", "모드: 모의 (테스트)")) as c:
        yield c


def wait_until(condition, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.1)
    return condition()


def test_index_and_static(client):
    page = client.get("/")
    assert page.status_code == 200 and "에이전트 루프 + MCP" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_api_config(client):
    data = client.get("/api/config").json()
    assert data["mode"] == "mock"
    assert data["examples"] == ["가장 재고가 많은 과일의 가격은 얼마야?", "수박 재고 있어?", "'에이전트 루프'는 몇 글자야?"]
    assert data["system_prompt"] and data["system_prompt_ko"]


def test_api_tools(client):
    response = client.get("/api/tools")
    assert response.status_code == 200
    servers = response.json()["servers"]
    names = [t["name"] for s in servers for t in s["tools"]]
    assert names == ["list_items", "check_stock", "get_price", "count_chars"]
    assert no_children(os.getpid())  # 목록만 받고 서버는 바로 정리


def test_run_stream_mock(client):
    with client.stream("GET", RUN_URL) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    assert "event: tool_call" in body
    assert "event: tool_result" in body
    assert "event: run_end" in body
    assert '"stop_reason": "answer"' in body
    assert "1,500원" in body


def test_bad_requests(client):
    assert client.get("/api/run?q=").status_code == 400
    assert client.get(f"/api/run?q=hi&mode=cloud").status_code == 400


def test_single_run_lock(slow_client):
    with slow_client.stream("GET", RUN_URL) as first:
        assert first.status_code == 200
        lines = first.iter_lines()  # 변수에 붙잡아 둔다(버리면 스트림이 닫혀 연결이 끊긴다)
        assert next(lines).startswith("event: run_start")
        # 첫 실행이 진행 중일 때 두 번째 요청은 거절된다
        second = slow_client.get(RUN_URL)
        assert second.status_code == 409
        assert "진행 중" in second.json()["error"]
    # 첫 실행이 끝나면(여기서는 연결을 닫으면) 다시 실행할 수 있다
    with slow_client.stream("GET", f"/api/run?q={quote('수박 재고 있어?')}&mode=mock") as again:
        assert again.status_code == 200


def test_disconnect_cancels_run(slow_client, caplog):
    caplog.set_level(logging.INFO, logger="agentloop")
    pid = os.getpid()
    with slow_client.stream("GET", RUN_URL) as response:
        for line in response.iter_lines():
            if line.startswith("event: tool_call"):
                alive_during_run = children_alive_as_expected(pid, 2)  # 이때는 MCP 서버 2개가 떠 있다
                break  # 첫 도구 호출을 본 순간 연결을 끊는다(브라우저 탭 닫기와 같다)
    assert alive_during_run

    # 서버는 끊김을 알아채고 실행을 취소한 뒤 MCP 서버 프로세스를 정리한다
    assert wait_until(lambda: "stop_reason=cancelled" in caplog.text), caplog.text
    assert wait_until(lambda: no_children(pid))
    # 자리도 반납되어 새 실행을 받을 수 있다
    with slow_client.stream("GET", RUN_URL) as again:
        assert again.status_code == 200


def test_stream_ends_even_when_queue_full(settings, monkeypatch):
    """대기열이 가득 찬 채 실행이 끝나 '끝' 표시가 버려져도 스트림은 닫혀야 한다(멈춤 방지)."""
    import threading

    import agentloop.web as web

    monkeypatch.setattr(web, "QUEUE_SIZE", 1)  # 대기열을 1칸으로 줄여 '끝' 표시가 들어갈 자리가 없게 만든다
    result = {}

    def consume():
        with TestClient(create_app(settings, "mock", "모드: 모의 (테스트)")) as c:
            with c.stream("GET", RUN_URL) as response:
                result["body"] = "".join(response.iter_text())

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    t.join(timeout=30)
    assert not t.is_alive(), "스트림이 끝나지 않고 멈췄다"
    assert "event: run_end" in result["body"]
