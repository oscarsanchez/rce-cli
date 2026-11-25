import json

from conftest import TOKEN
from fake_rce import WEBRTC_SECRETS, Response

PLAYER_DETAIL = {
    "id": 351,
    "device_name": "player",
    "name": "Personal RCE Player",
    "type": "stb",
    "status": "shutdown",
    "run": None,
    "created_at": "2026-11-11T17:02:11.123456Z",
    "serial_number": "XY0000000351",
    "last_snapshot_id": 997,
    "last_snapshot_name": "Initial snapshot",
}


def test_show_by_device_name_gives_the_cloud_device_in_detail(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    assert rce.json("device", "show", "player") == PLAYER_DETAIL
    assert fake_rce.requests_to("GET", "/api/v1/devices/351")


def test_show_by_raw_id_gives_the_same_detail(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    assert rce.json("device", "show", "351") == PLAYER_DETAIL


def test_show_of_an_id_without_a_device_name(rce, fake_rce):
    fake_rce.add_device(352, "Personal RCE TV", "tv")

    assert rce.json("device", "show", "352")["device_name"] is None


def test_show_of_an_unknown_name_is_not_found_without_asking_rce(rce, fake_rce):
    result = rce.run("device", "show", "nope")

    assert result.returncode == 3
    assert not fake_rce.requests


def test_show_of_an_unknown_id_is_not_found(rce, fake_rce):
    assert rce.run("device", "show", "999").returncode == 3


def test_show_json_names_the_runs_firmware(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)

    run = rce.json("device", "show", "351")["run"]

    assert (run["firmware_version_id"], run["firmware_version_display_name"]) == ("395", "v16.0.4 b853")


def test_show_prints_fields_for_people_without_secrets(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.name_device("351", "player")

    result = rce.run("device", "show", "player")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "ID:             351",
        "Device Name:    player",
        "RCE name:       Personal RCE Player",
        "Type:           stb",
        "Status:         running",
        "Run:            9000 since 2026-11-16T21:00:00Z",
        "Created:        2026-11-11T17:02:11.123456Z",
        "Serial number:  XY0000000351",
        "Last Snapshot:  997 (Initial snapshot)",
    ]
    for secret in (TOKEN, *WEBRTC_SECRETS):
        assert secret not in result.stdout + result.stderr


def store_dev_password(rce, password: str) -> None:
    """As setup-dev stores it, with the Device Name."""
    rce.config.write_text(rce.config.read_text() + f'dev_password = "{password}"\n')


def test_show_dev_password_prints_only_the_bare_value_on_stderr(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    store_dev_password(rce, "stored-PASSWORD")

    result = rce.run("device", "show", "player", "--dev-password")

    assert result.returncode == 0, result.stderr
    assert result.stderr == "stored-PASSWORD\n"  # a pipe into a CI secret takes stderr whole
    assert "stored-PASSWORD" not in result.stdout
    assert "ID:             351" in result.stdout


def test_show_dev_password_prints_nothing_when_rce_fails_to_answer(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    store_dev_password(rce, "stored-PASSWORD")
    fake_rce.fail_next("GET", "/api/v1/devices/351", Response(500, {"detail": "boom"}))

    result = rce.run("device", "show", "player", "--dev-password")

    assert result.returncode != 0
    assert "stored-PASSWORD" not in result.stdout + result.stderr


def test_show_dev_password_with_none_stored_exits_4_and_says_so(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    rce.env["RCE_DEV_PASSWORD"] = "pipeline-SECRET"  # not stored, so not shown
    asked_before = len(fake_rce.requests)

    result = rce.run("device", "show", "player", "--dev-password")

    assert result.returncode == 4
    assert len(fake_rce.requests) == asked_before  # refused before asking RCE
    assert "no Dev Password is stored for player (351)" in result.stderr
    assert "pipeline-SECRET" not in result.stdout + result.stderr


def test_show_dev_password_of_an_id_without_a_device_name_exits_4(rce, fake_rce):
    fake_rce.add_device(352, "Personal RCE TV", "tv")

    result = rce.run("device", "show", "352", "--dev-password")

    assert result.returncode == 4
    assert "no Dev Password is stored for Cloud Device 352" in result.stderr


def test_show_dev_password_never_puts_it_in_json(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    store_dev_password(rce, "stored-PASSWORD")

    result = rce.run("device", "show", "player", "--dev-password", "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == PLAYER_DETAIL
    assert "stored-PASSWORD" in result.stderr
