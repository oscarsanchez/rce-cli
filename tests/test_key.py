"""`rce key`: remote keys on a Run, through the Instance API's input endpoint."""

from conftest import TOKEN
from fake_rce import Response

INSTANCE = "/instance/uuid-351/api/v0"  # RCE's path; glossary-ok
KEYPRESS = f"{INSTANCE}/input/keypress/"


def running_player(rce, fake_rce) -> dict:
    device = fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.name_device("351", "player")
    return device


def keypresses(fake_rce) -> list[str]:
    return [r.path[len(KEYPRESS):] for r in fake_rce.requests if r.path.startswith(KEYPRESS)]


def test_key_presses_each_key_in_order_with_the_token(rce, fake_rce):
    running_player(rce, fake_rce)

    result = rce.run("key", "player", "Home", "Down", "Select")

    assert result.returncode == 0, result.stderr
    assert keypresses(fake_rce) == ["Home", "Down", "Select"]
    presses = [r for r in fake_rce.requests if r.path.startswith(KEYPRESS)]
    assert all(r.method == "POST" for r in presses)
    assert all(r.headers["authorization"] == f"Bearer {TOKEN}" for r in presses)
    assert "player (351)" in result.stdout


def test_key_waits_until_the_run_takes_input(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    fake_rce.input_delay = 1.0
    assert rce.run("device", "start", "player", "--no-wait").returncode == 0

    result = rce.run("key", "player", "Home")

    assert result.returncode == 0, result.stderr
    [press] = [r for r in fake_rce.requests if "/input/keypress/" in r.path]
    ready = [r for r in fake_rce.requests if r.path.endswith("/input/ready")]
    assert ready and fake_rce.requests.index(ready[-1]) < fake_rce.requests.index(press)


def test_key_waits_the_delay_between_keys(rce, fake_rce):
    running_player(rce, fake_rce)

    result = rce.run("key", "player", "Down", "Down", "--delay", "400")

    assert result.returncode == 0, result.stderr
    first, second = [r for r in fake_rce.requests if r.path.startswith(KEYPRESS)]
    assert second.at - first.at >= 0.4


def test_key_sends_literal_characters_url_encoded(rce, fake_rce):
    running_player(rce, fake_rce)

    result = rce.run("key", "player", "Lit_a", "Lit_€", "Lit_ ")

    assert result.returncode == 0, result.stderr
    assert keypresses(fake_rce) == ["Lit_a", "Lit_%E2%82%AC", "Lit_%20"]


def test_key_on_a_cloud_device_that_is_not_running_exits_4(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    result = rce.run("key", "player", "Home")

    assert result.returncode == 4
    assert "not running" in result.stderr
    assert keypresses(fake_rce) == []


def test_key_reports_a_key_the_device_did_not_take(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.fail_next(
        "POST",
        f"{KEYPRESS}Down",
        Response(
            200,
            {
                "response": "key-press",
                "response_id": "2",
                "status_code": 500,
                "status_message": "Device control unavailable",
            },
        ),
    )

    result = rce.run("key", "player", "Home", "Down", "Select")

    assert result.returncode == 4
    assert "Down" in result.stderr and "Device control unavailable" in result.stderr
    assert keypresses(fake_rce) == ["Home", "Down"]
