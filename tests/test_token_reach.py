"""The token's reach: `rce` sends the RCE token only to https on rce.roku.com and its
subdomains at the default port, or to the Core API's own origin (RCE_API_URL)."""

import pytest

from conftest import TOKEN

CONSOLE = 8085
API = "/api/v1"

# Run addresses the Core API might give that must never receive the token,
# with the host the refusal names.
UNTRUSTED = [
    pytest.param("https://evil.example", "evil.example", id="foreign-host"),
    pytest.param("http://run.rce.roku.com", "run.rce.roku.com", id="http"),
    pytest.param("https://run.rce.roku.com:8443", "run.rce.roku.com:8443", id="non-default-port"),
    pytest.param("https://rce.roku.com.evil.example", "rce.roku.com.evil.example", id="suffix-trick"),
    pytest.param("https://evilrce.roku.com", "evilrce.roku.com", id="no-dot-boundary"),
    pytest.param("http://127.0.0.1:9", "127.0.0.1:9", id="core-api-host-other-port"),
]


def running_player(rce, fake_rce, origin: str | None) -> None:
    fake_rce.address_origin = origin
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.name_device("351", "player")
    rce.proxy_through(fake_rce)


def sent_to_the_run(fake_rce) -> list:
    """Every request that reached the Run's address: proxied elsewhere, or on the fake's
    own Instance API."""
    return fake_rce.proxied + [r for r in fake_rce.requests if not r.path.startswith(API)]


def assert_refused(result, fake_rce, host: str) -> None:
    assert result.returncode == 1, result.stderr
    assert f"refusing to send the RCE token to {host}" in result.stderr
    assert TOKEN not in result.stdout + result.stderr
    assert sent_to_the_run(fake_rce) == []


@pytest.mark.parametrize(("origin", "host"), UNTRUSTED)
def test_an_http_command_refuses_an_untrusted_run_address(rce, fake_rce, origin, host):
    running_player(rce, fake_rce, origin)

    result = rce.run("ecp", "player", "query/device-info")

    assert_refused(result, fake_rce, host)


@pytest.mark.parametrize(("origin", "host"), UNTRUSTED)
def test_a_websocket_command_refuses_an_untrusted_run_address(rce, fake_rce, origin, host):
    running_player(rce, fake_rce, origin)
    fake_rce.bridge(CONSOLE).frames = [b"hello\n"]

    result = rce.run("console", "player", "--timeout", "5")

    assert_refused(result, fake_rce, host)


def test_a_run_address_without_a_scheme_is_read_as_https_and_accepted(rce, fake_rce):
    running_player(rce, fake_rce, "run.rce.roku.com")  # as RCE's spec documents instance_api_url

    result = rce.run("ecp", "player", "query/device-info")

    assert "refusing" not in result.stderr
    [connect] = fake_rce.proxied  # through the proxy, so nothing left the machine
    assert (connect.method, connect.path) == ("CONNECT", "run.rce.roku.com:443")
    assert TOKEN not in str(connect.headers)  # the token travels only inside TLS


def test_the_core_apis_own_origin_receives_the_token(rce, fake_rce):
    running_player(rce, fake_rce, None)  # the fake's own address, http on 127.0.0.1

    result = rce.run("ecp", "player", "query/device-info")

    assert result.returncode == 0, result.stderr
    assert fake_rce.proxied == []
