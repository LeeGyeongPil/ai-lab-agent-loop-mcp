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
