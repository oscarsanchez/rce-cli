import json


def test_retire_renames_on_rce_and_drops_the_device_name(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    fake_rce.add_device(352, "Personal RCE TV", "tv")
    rce.name_device("351", "player")
    rce.name_device("352", "tv")

    result = rce.json("device", "retire", "player", "--yes")

    [patch] = fake_rce.requests_to("PATCH", "/api/v1/devices/351")
    assert json.loads(patch.body) == {"name": "retired/Personal RCE Player"}
    assert result == {"id": 351, "name": "retired/Personal RCE Player"}
    assert rce.read_config()["devices"] == {"tv": {"id": 352, "type": "tv"}}


def test_retire_refuses_a_running_device(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.name_device("351", "player")

    result = rce.run("device", "retire", "player", "--yes")

    assert result.returncode == 4
    assert "running" in result.stderr
    assert fake_rce.requests_to("PATCH", "/api/v1/devices/351") == []
    assert rce.json("device", "resolve", "player")["id"] == 351


def test_retire_refuses_a_pending_device(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")["status"] = "pending"

    result = rce.run("device", "retire", "351", "--yes")

    assert result.returncode == 4
    assert fake_rce.requests_to("PATCH", "/api/v1/devices/351") == []


def test_retire_without_a_terminal_or_yes_refuses_and_changes_nothing(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    result = rce.run("device", "retire", "player")

    assert result.returncode == 2
    assert "--yes" in result.stderr
    assert fake_rce.requests_to("PATCH", "/api/v1/devices/351") == []
    assert rce.json("device", "resolve", "player")["id"] == 351


def test_retire_asks_first_and_y_retires(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    result = rce.run_tty("device", "retire", "player", answer="y")

    assert result.returncode == 0, result.stderr
    assert "Personal RCE Player" in result.stderr
    assert "cannot be deleted" in result.stderr
    assert fake_rce.devices[351]["name"] == "retired/Personal RCE Player"


def test_retire_declined_at_the_prompt_changes_nothing(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    result = rce.run_tty("device", "retire", "player", answer="n")

    assert result.returncode == 2
    assert fake_rce.requests_to("PATCH", "/api/v1/devices/351") == []
    assert rce.json("device", "resolve", "player")["id"] == 351


def test_retire_by_id_of_a_device_without_a_device_name(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")

    result = rce.run("device", "retire", "351", "--yes")

    assert result.returncode == 0, result.stderr
    assert fake_rce.devices[351]["name"] == "retired/Personal RCE Player"
    assert not rce.config.exists()


def test_retire_of_a_retired_device_is_refused(rce, fake_rce):
    fake_rce.add_device(351, "retired/Personal RCE Player", "stb")

    result = rce.run("device", "retire", "351", "--yes")

    assert result.returncode == 2
    assert "already retired" in result.stderr
    assert fake_rce.requests_to("PATCH", "/api/v1/devices/351") == []
    assert fake_rce.devices[351]["name"] == "retired/Personal RCE Player"


def test_retire_of_an_unknown_device_is_not_found(rce, fake_rce):
    result = rce.run("device", "retire", "999", "--yes")

    assert result.returncode == 3
