"""`rce console`: stream a running Cloud Device's BrightScript console."""

import json
import signal
import time

from conftest import TOKEN

CONSOLE = 8085


def running_player(rce, fake_rce) -> dict:
    device = fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.name_device("351", "player")
    return device


def test_until_prints_lines_and_exits_0_on_the_first_match(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.bridge(CONSOLE).frames = [b"booting\n", b"app ready: home\n", b"after\n"]

    result = rce.run("console", "player", "--until", r"ready: \w+", "--timeout", "10")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "booting\napp ready: home\n"


def test_timeout_without_a_match_exits_5(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.bridge(CONSOLE).frames = [b"booting\n"]

    result = rce.run("console", "player", "--until", "never", "--timeout", "1")

    assert result.returncode == 5
    assert result.stdout == "booting\n"
    assert "no console line matched 'never' in 1 s" in result.stderr


def test_timeout_without_until_streams_for_that_long_then_exits_5(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.bridge(CONSOLE).frames = [b"one\n"]

    result = rce.run("console", "player", "--timeout", "1")

    assert result.returncode == 5
    assert result.stdout == "one\n"
    assert "after 1 s" in result.stderr


def test_lines_split_across_frames_are_reassembled_before_matching(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.bridge(CONSOLE).frames = [b"first\nre", b"ady: ", b"caf\xc3", b"\xa9\r\n"]

    result = rce.run("console", "player", "--until", "^ready: café$", "--timeout", "10")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "first\nready: café\n"


def test_strip_ansi_removes_colour_codes_before_printing_and_matching(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.bridge(CONSOLE).frames = [b"\x1b[1;32mPASS\x1b[0m: home\n"]

    result = rce.run(
        "console", "player", "--until", "^PASS: home$", "--timeout", "10", "--strip-ansi"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "PASS: home\n"


def test_without_strip_ansi_colour_codes_pass_through(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.bridge(CONSOLE).frames = [b"\x1b[1;32mPASS\x1b[0m: home\n"]

    result = rce.run("console", "player", "--until", "^PASS: home$", "--timeout", "1")

    assert result.returncode == 5
    assert result.stdout == "\x1b[1;32mPASS\x1b[0m: home\n"


def test_json_prints_one_object_per_line(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.bridge(CONSOLE).frames = [b"booting\nready\n"]

    result = rce.run("console", "player", "--until", "ready", "--timeout", "10", "--json")

    assert result.returncode == 0, result.stderr
    assert [json.loads(line) for line in result.stdout.splitlines()] == [
        {"line": "booting", "matched": False},
        {"line": "ready", "matched": True},
    ]


def test_console_opens_the_runs_console_bridge_with_the_token_and_sends_nothing(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.bridge(CONSOLE).frames = [b"ready\n"]

    result = rce.run("console", "player", "--until", "ready", "--timeout", "10")

    assert result.returncode == 0, result.stderr
    (opened,) = fake_rce.requests_to("GET", "/instance/uuid-351/api/v0/ports/8085")  # glossary-ok
    assert opened.headers["authorization"] == f"Bearer {TOKEN}"
    assert opened.headers["upgrade"].lower() == "websocket"
    assert fake_rce.bridge(CONSOLE).connections == 1
    assert fake_rce.bridge(CONSOLE).received == b""
    assert TOKEN not in result.stdout + result.stderr


def test_without_until_it_streams_until_interrupted(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.bridge(CONSOLE).frames = [b"one\n", b"two\n"]

    console = rce.spawn("console", "player")
    assert console.stdout.readline() == "one\n"
    assert console.stdout.readline() == "two\n"
    time.sleep(0.5)
    assert console.poll() is None, "it stopped streaming on its own"
    console.send_signal(signal.SIGINT)

    assert console.wait(timeout=20) == 130


def test_dev_mode_off_says_console_unavailable(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.dev_mode = False

    result = rce.run("console", "player", "--until", "ready", "--timeout", "10")

    assert result.returncode == 4
    assert "console unavailable: is dev mode on?" in result.stderr


def test_console_of_a_device_that_is_not_running_says_so(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    result = rce.run("console", "player", "--timeout", "1")

    assert result.returncode == 4
    assert "player (351) is not running" in result.stderr


def test_the_run_ending_underneath_the_console_is_reported(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.bridge(CONSOLE).frames = [b"one\n"]
    console = rce.spawn("console", "player")
    assert console.stdout.readline() == "one\n"

    assert rce.run("device", "stop", "player").returncode == 0

    assert console.wait(timeout=20) == 4
    assert "the Run of player (351) ended" in console.stderr.read()


def test_an_invalid_regex_is_a_usage_error(rce, fake_rce):
    running_player(rce, fake_rce)

    result = rce.run("console", "player", "--until", "(")

    assert result.returncode == 2
    assert "--until" in result.stderr
