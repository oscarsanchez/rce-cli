"""`rce forward`: a local TCP port bridged to a running Cloud Device's port."""

import json
import signal
import socket
import time

import pytest

from conftest import TOKEN

CONSOLE = 8085


def running_player(rce, fake_rce) -> dict:
    device = fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.name_device("351", "player")
    return device


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def start_forward(rce, *args: str):
    """`rce forward` in the background, once it says it is listening."""
    forward = rce.spawn("forward", *args)
    line = forward.stdout.readline()
    assert line, forward.stderr.read()
    return forward, line


def read_until(client: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = client.recv(size - len(data))
        if not chunk:
            break
        data += chunk
    return data


@pytest.fixture
def forwards():
    """Every `rce forward` a test spawns, interrupted at the end if still running."""
    spawned = []
    yield spawned
    for process in spawned:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_json_names_the_cloud_device_like_other_commands(rce, fake_rce, forwards):
    running_player(rce, fake_rce)
    local = free_port()
    forward = rce.spawn("forward", "player", "8085", "--local", str(local), "--json")
    forwards.append(forward)

    printed = ""
    while not printed.rstrip().endswith("}"):
        line = forward.stdout.readline()
        assert line, forward.stderr.read()
        printed += line

    assert json.loads(printed) == {"id": 351, "device_name": "player", "port": 8085, "local": local}


def test_bytes_flow_both_ways_between_the_local_port_and_the_device_port(
    rce, fake_rce, forwards
):
    running_player(rce, fake_rce)
    bridge = fake_rce.bridge(CONSOLE)
    bridge.frames = [b"hello from the device\n"]
    bridge.echo = True
    local = free_port()
    forward, line = start_forward(rce, "player", "8085", "--local", str(local))
    forwards.append(forward)

    sent = b"\x00\xffbinary to the device\n"
    with socket.create_connection(("127.0.0.1", local), timeout=10) as client:
        assert read_until(client, 22) == b"hello from the device\n"
        client.sendall(sent)
        assert read_until(client, len(sent)) == sent

    assert f"127.0.0.1:{local}" in line
    assert bridge.received == sent
    (opened,) = fake_rce.requests_to("GET", "/instance/uuid-351/api/v0/ports/8085")  # glossary-ok
    assert opened.headers["authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize("port, instead", [("80", "sideload"), ("8060", "ecp")])
def test_http_only_ports_are_refused_with_the_command_to_use(rce, fake_rce, port, instead):
    running_player(rce, fake_rce)

    result = rce.run("forward", "player", port)

    assert result.returncode == 2
    assert f"port {port} is HTTP only" in result.stderr
    assert f"rce {instead}" in result.stderr


def test_a_port_rce_does_not_bridge_is_refused_listing_the_ones_it_does(rce, fake_rce):
    running_player(rce, fake_rce)

    result = rce.run("forward", "player", "22")

    assert result.returncode == 2
    assert "8080, 8081, 8082, 8085, 8087, 9999" in result.stderr


@pytest.mark.parametrize("port", ["8080", "8081", "8082", "8087", "9999"])
def test_each_debug_port_is_forwarded_to_its_own_bridge(rce, fake_rce, forwards, port):
    running_player(rce, fake_rce)
    fake_rce.bridge(int(port)).frames = [port.encode()]
    local = free_port()
    forward, _ = start_forward(rce, "player", port, "--local", str(local))
    forwards.append(forward)

    with socket.create_connection(("127.0.0.1", local), timeout=10) as client:
        assert read_until(client, len(port)) == port.encode()


def test_the_local_port_defaults_to_the_device_port(rce, fake_rce, forwards):
    try:
        socket.create_server(("127.0.0.1", 8087)).close()
    except OSError:
        pytest.skip("127.0.0.1:8087 is in use on this machine; the test needs it free")
    running_player(rce, fake_rce)
    fake_rce.bridge(8087).frames = [b"screensaver\n"]
    forward, line = start_forward(rce, "player", "8087")
    forwards.append(forward)

    with socket.create_connection(("127.0.0.1", 8087), timeout=10) as client:
        assert read_until(client, 12) == b"screensaver\n"
    assert "127.0.0.1:8087 to port 8087 of player (351)" in line


def test_a_local_port_in_use_is_a_usage_error(rce, fake_rce):
    running_player(rce, fake_rce)
    with socket.create_server(("127.0.0.1", 0)) as taken:
        local = taken.getsockname()[1]

        result = rce.run("forward", "player", "8085", "--local", str(local))

    assert result.returncode == 2
    assert f"cannot listen on 127.0.0.1:{local}" in result.stderr


def test_several_connections_at_once_each_get_their_own_bridge(rce, fake_rce, forwards):
    running_player(rce, fake_rce)
    bridge = fake_rce.bridge(CONSOLE)
    bridge.echo = True
    local = free_port()
    forward, _ = start_forward(rce, "player", "8085", "--local", str(local))
    forwards.append(forward)

    first = socket.create_connection(("127.0.0.1", local), timeout=10)
    second = socket.create_connection(("127.0.0.1", local), timeout=10)
    with first, second:
        second.sendall(b"two")
        first.sendall(b"one")
        assert read_until(first, 3) == b"one"
        assert read_until(second, 3) == b"two"

    assert bridge.connections == 2


def test_a_client_hanging_up_leaves_it_forwarding_until_interrupted(rce, fake_rce, forwards):
    running_player(rce, fake_rce)
    fake_rce.bridge(CONSOLE).echo = True
    local = free_port()
    forward, _ = start_forward(rce, "player", "8085", "--local", str(local))
    forwards.append(forward)

    for word in (b"first", b"second"):
        with socket.create_connection(("127.0.0.1", local), timeout=10) as client:
            client.sendall(word)
            assert read_until(client, len(word)) == word
    time.sleep(0.5)
    assert forward.poll() is None, "it stopped forwarding on its own"
    forward.send_signal(signal.SIGINT)

    assert forward.wait(timeout=20) == 130


def test_the_run_ending_under_a_connection_is_reported(rce, fake_rce, forwards):
    running_player(rce, fake_rce)
    local = free_port()
    forward, _ = start_forward(rce, "player", "8085", "--local", str(local))
    forwards.append(forward)

    with socket.create_connection(("127.0.0.1", local), timeout=10) as client:
        client.sendall(b"x")
        while not fake_rce.bridge(CONSOLE).received:
            time.sleep(0.05)
        assert rce.run("device", "stop", "player").returncode == 0
        assert read_until(client, 1) == b"", "the client was not hung up"

    assert forward.wait(timeout=20) == 4
    assert "the Run of player (351) ended" in forward.stderr.read()


def test_the_run_ending_with_no_connection_is_reported(rce, fake_rce, forwards):
    running_player(rce, fake_rce)
    forward, _ = start_forward(rce, "player", "8085", "--local", str(free_port()))
    forwards.append(forward)

    assert rce.run("device", "stop", "player").returncode == 0

    assert forward.wait(timeout=20) == 4
    assert "the Run of player (351) ended" in forward.stderr.read()


def test_dev_mode_off_warns_per_connection_and_keeps_forwarding(rce, fake_rce, forwards):
    running_player(rce, fake_rce)
    fake_rce.dev_mode = False
    local = free_port()
    forward, _ = start_forward(rce, "player", "8081", "--local", str(local))
    forwards.append(forward)

    with socket.create_connection(("127.0.0.1", local), timeout=10) as client:
        assert read_until(client, 1) == b""
    time.sleep(0.5)
    assert forward.poll() is None, "it stopped forwarding on its own"
    forward.send_signal(signal.SIGINT)

    assert forward.wait(timeout=20) == 130
    assert "forward to port 8081 unavailable: is dev mode on?" in forward.stderr.read()


def test_forward_of_a_device_that_is_not_running_says_so(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    result = rce.run("forward", "player", "8085", "--local", str(free_port()))

    assert result.returncode == 4
    assert "player (351) is not running" in result.stderr
