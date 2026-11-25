"""`rce snapshot`: list a Cloud Device's Snapshots, take one, mark the Dev Snapshot."""

import json

from fake_rce import snapshot_out

TAKE = "/api/v1/devices/351/snapshots"


def player(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")


def test_list_shows_each_snapshot_and_marks_none_as_dev_without_one(rce, fake_rce):
    player(rce, fake_rce)

    snapshots = rce.json("snapshot", "list", "player")

    assert snapshots == [
        {
            "id": 997,
            "name": "Initial snapshot",
            "created_at": "2026-11-11T15:35:01.531252Z",
            "firmware_version_display_name": None,
            "ready": True,
            "base": True,
            "live": False,
            "dev_snapshot": False,
        },
        {
            "id": 998,
            "name": "Live snapshot",
            "created_at": "2026-11-11T15:35:01.531252Z",
            "firmware_version_display_name": None,
            "ready": True,
            "base": False,
            "live": True,
            "dev_snapshot": False,
        },
    ]


def test_list_for_people_shows_a_table(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.snapshots[351].append(snapshot_out(1001, "dev-ready") | {"ready": False})

    result = rce.run("snapshot", "list", "351")

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0].split() == ["ID", "NAME", "CREATED", "FIRMWARE", "READY", "BASE", "LIVE", "DEV"]
    assert lines[1].split()[:2] == ["997", "Initial"]
    assert "base" in lines[1] and "live" in lines[2]
    assert lines[3].split()[:2] == ["1001", "dev-ready"]
    assert "no" in lines[3].split()  # not ready yet


def test_list_shows_the_firmware_each_snapshot_was_saved_on(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.snapshots[351].append(
        snapshot_out(1001, "dev-ready") | {"firmware_version_display_name": "v16.0.4 b853"}
    )

    snapshots = rce.json("snapshot", "list", "player")

    firmware = {s["id"]: s["firmware_version_display_name"] for s in snapshots}
    assert firmware == {997: None, 998: None, 1001: "v16.0.4 b853"}
    assert len(fake_rce.requests_to("GET", TAKE)) == 1


def test_list_for_people_shows_the_firmware_or_a_dash(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.snapshots[351].append(
        snapshot_out(1001, "dev-ready") | {"firmware_version_display_name": "v16.0.4 b853"}
    )

    result = rce.run("snapshot", "list", "player")

    assert result.returncode == 0, result.stderr
    header, base, live, dev = result.stdout.splitlines()
    firmware = header.index("FIRMWARE")
    assert dev[firmware:].startswith("v16.0.4 b853")
    assert base[firmware:].startswith("- ") and live[firmware:].startswith("- ")


def test_list_of_an_unknown_device_exits_3(rce, fake_rce):
    result = rce.run("snapshot", "list", "999")

    assert result.returncode == 3


def dev_ready(fake_rce, ready: bool = True) -> None:
    """A Snapshot 1001 of player, as setup-dev takes it."""
    fake_rce.snapshots[351].append(snapshot_out(1001, "dev-ready") | {"ready": ready})


def test_use_as_dev_records_the_dev_snapshot_and_start_uses_it(rce, fake_rce):
    player(rce, fake_rce)
    dev_ready(fake_rce)

    marked = rce.json("snapshot", "use-as-dev", "player", "1001", "--yes")

    assert marked == {"id": 351, "device_name": "player", "dev_snapshot_id": 1001}
    assert rce.read_config()["devices"]["player"]["dev_snapshot_id"] == 1001
    listed = rce.json("snapshot", "list", "player")
    assert [s["id"] for s in listed if s["dev_snapshot"]] == [1001]
    started = rce.run("device", "start", "player")
    assert started.returncode == 0, started.stderr
    [start] = fake_rce.requests_to("POST", "/api/v1/devices/351/start")
    assert start.json()["snapshot_id"] == 1001


def test_use_as_dev_by_raw_id_records_it_with_the_device_name(rce, fake_rce):
    player(rce, fake_rce)
    dev_ready(fake_rce)

    result = rce.run("snapshot", "use-as-dev", "351", "1001", "--yes")

    assert result.returncode == 0, result.stderr
    assert rce.read_config()["devices"]["player"]["dev_snapshot_id"] == 1001


def test_use_as_dev_needs_a_device_name_to_record_it_with(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")

    result = rce.run("snapshot", "use-as-dev", "351", "998", "--yes")

    assert result.returncode == 3
    assert "Device Name" in result.stderr


def test_a_snapshot_that_is_not_ready_is_refused_as_the_dev_snapshot(rce, fake_rce):
    player(rce, fake_rce)
    dev_ready(fake_rce, ready=False)

    result = rce.run("snapshot", "use-as-dev", "player", "1001", "--yes")

    assert result.returncode == 4
    assert "Snapshot 1001 is not ready" in result.stderr
    assert "dev_snapshot_id" not in rce.read_config()["devices"]["player"]


def test_a_snapshot_that_does_not_exist_is_refused_as_the_dev_snapshot(rce, fake_rce):
    player(rce, fake_rce)

    result = rce.run("snapshot", "use-as-dev", "player", "4242", "--yes")

    assert result.returncode == 3
    assert "no Snapshot 4242" in result.stderr
    assert "dev_snapshot_id" not in rce.read_config()["devices"]["player"]


def test_use_as_dev_without_a_terminal_or_yes_changes_nothing(rce, fake_rce):
    player(rce, fake_rce)
    dev_ready(fake_rce)

    result = rce.run("snapshot", "use-as-dev", "player", "1001")

    assert result.returncode == 2
    assert "--yes" in result.stderr
    assert "dev_snapshot_id" not in rce.read_config()["devices"]["player"]


def test_use_as_dev_asks_first_and_names_the_snapshot_it_replaces(rce, fake_rce):
    player(rce, fake_rce)
    dev_ready(fake_rce)
    rce.run("snapshot", "use-as-dev", "player", "998", "--yes")

    declined = rce.run_tty("snapshot", "use-as-dev", "player", "1001", answer="n")

    assert declined.returncode == 2
    assert "dev-ready" in declined.stderr and "998" in declined.stderr
    assert rce.read_config()["devices"]["player"]["dev_snapshot_id"] == 998

    accepted = rce.run_tty("snapshot", "use-as-dev", "player", "1001", answer="y")

    assert accepted.returncode == 0, accepted.stderr
    assert rce.read_config()["devices"]["player"]["dev_snapshot_id"] == 1001


def take(rce, *flags):
    return rce.run("snapshot", "take", "player", "--label", "dev-ready", *flags)  # glossary-ok


def test_take_creates_a_snapshot_and_waits_until_it_is_ready(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.snapshot_delay = 0.5

    result = take(rce, "--yes", "--json")

    assert result.returncode == 0, result.stderr
    [created] = fake_rce.requests_to("POST", TAKE)
    assert created.json() == {"name": "dev-ready"}
    snapshot = json.loads(result.stdout)
    assert snapshot["name"] == "dev-ready" and snapshot["ready"] is True
    assert fake_rce.requests_to("GET", f"{TAKE}/{snapshot['id']}")  # it polled
    listed = rce.json("snapshot", "list", "player")
    assert any(s["id"] == snapshot["id"] and s["ready"] for s in listed)


def test_take_reports_the_firmware_the_snapshot_was_saved_on(rce, fake_rce):
    player(rce, fake_rce)

    snapshot = json.loads(take(rce, "--yes", "--json").stdout)

    [listed] = [s for s in rce.json("snapshot", "list", "player") if s["id"] == snapshot["id"]]
    assert snapshot == listed  # the same object `snapshot list` shows, Firmware included
    assert "firmware_version_display_name" in snapshot


def test_take_says_what_it_took(rce, fake_rce):
    player(rce, fake_rce)

    result = take(rce, "--yes")

    assert result.returncode == 0, result.stderr
    assert "dev-ready" in result.stdout and "ready" in result.stdout
    assert "player (351)" in result.stdout


def test_a_snapshot_not_ready_in_time_exits_5(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.snapshot_delay = 60

    result = take(rce, "--yes", "--timeout", "1")

    assert result.returncode == 5
    assert "not ready" in result.stderr
    assert "rce snapshot list player" in result.stderr


def test_the_snapshot_limit_is_explained(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.snapshot_limit = 2  # player already has its base and live Snapshots

    result = take(rce, "--yes")

    assert result.returncode == 4
    assert "Snapshot limit" in result.stderr
    assert len(fake_rce.snapshots[351]) == 2


def test_a_name_rce_would_reject_is_a_usage_error(rce, fake_rce):
    player(rce, fake_rce)

    result = rce.run("snapshot", "take", "player", "--label", "ab", "--yes")  # glossary-ok

    assert result.returncode == 2
    assert not fake_rce.requests_to("POST", TAKE)


def test_take_without_a_terminal_or_yes_takes_nothing(rce, fake_rce):
    player(rce, fake_rce)

    result = take(rce)

    assert result.returncode == 2
    assert "--yes" in result.stderr
    assert not fake_rce.requests_to("POST", TAKE)


def test_take_asks_first(rce, fake_rce):
    player(rce, fake_rce)

    declined = rce.run_tty("snapshot", "take", "player", "--label", "dev-ready", answer="n")  # glossary-ok

    assert declined.returncode == 2
    assert "dev-ready" in declined.stderr and "player (351)" in declined.stderr
    assert not fake_rce.requests_to("POST", TAKE)

    accepted = rce.run_tty("snapshot", "take", "player", "--label", "dev-ready", answer="y")  # glossary-ok

    assert accepted.returncode == 0, accepted.stderr
    assert len(fake_rce.requests_to("POST", TAKE)) == 1
