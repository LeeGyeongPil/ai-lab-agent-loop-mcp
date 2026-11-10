"""진입점 옵션: --host 기본값과, 다른 기기에 열릴 때의 경고·접속 주소."""

from agentloop.__main__ import DEFAULT_HOST, describe_host, parse_args


def test_host_default_is_local_only():
    assert parse_args([]).host == DEFAULT_HOST == "127.0.0.1"
    assert parse_args(["--host", "0.0.0.0"]).host == "0.0.0.0"


def test_loopback_hosts_have_no_warning():
    assert describe_host("127.0.0.1", 8765) == ("http://127.0.0.1:8765", None)
    assert describe_host("localhost", 8765) == ("http://localhost:8765", None)
    assert describe_host("::1", 9000) == ("http://[::1]:9000", None)


def test_any_address_warns_and_gives_usable_url():
    # 0.0.0.0 / :: 는 브라우저 주소창에 못 쓰므로 이 PC에서 여는 주소로 바꿔 보여 준다
    url, warning = describe_host("0.0.0.0", 8765)
    assert url == "http://127.0.0.1:8765"
    assert warning and "다른 기기" in warning

    url, warning = describe_host("::", 8765)
    assert url == "http://[::1]:8765" and warning


def test_lan_address_warns():
    url, warning = describe_host("192.168.0.10", 8765)
    assert url == "http://192.168.0.10:8765" and warning


def test_busy_port_does_not_open_browser(monkeypatch, capsys):
    # 포트가 이미 쓰이면 브라우저를 열지 않고, 서버도 시작하지 않고, 한국어 안내와 함께 0이 아닌 코드로 끝난다
    import socket
    import webbrowser

    import uvicorn

    from agentloop.__main__ import main, port_is_free

    opened, started = [], []
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: opened.append(a))
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: started.append(a))
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        assert not port_is_free("127.0.0.1", port)  # 특수 주소는 아래 별도 확인
        code = main(["--mock", "--port", str(port)])
    captured = capsys.readouterr()
    assert code != 0
    assert opened == [] and started == []
    assert f"포트 {port}" in captured.err and "--port 9000" in captured.err
    assert "주소:" not in captured.out


def test_busy_port_detected_for_any_address():
    # 0.0.0.0 으로 점유된 포트는 0.0.0.0 으로 다시 열 수 없다
    import socket

    from agentloop.__main__ import port_is_free

    with socket.socket() as busy:
        busy.bind(("0.0.0.0", 0))
        busy.listen()
        port = busy.getsockname()[1]
        assert not port_is_free("0.0.0.0", port)
    assert port_is_free("127.0.0.1", port)  # 닫히면 다시 비어 있다
