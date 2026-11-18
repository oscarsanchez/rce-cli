import json


def test_create_without_a_terminal_or_yes_refuses_and_creates_nothing(rce, fake_rce):
    result = rce.run("device", "create", "spare", "--type", "tv")

    assert result.returncode == 2
    assert "--yes" in result.stderr
    assert fake_rce.requests_to("POST", "/api/v1/devices") == []
    assert not rce.config.exists()


def test_create_with_yes_creates_the_device_and_records_its_device_name(rce, fake_rce):
    result = rce.json("device", "create", "spare", "--type", "tv", "--yes")

    [post] = fake_rce.requests_to("POST", "/api/v1/devices")
    assert json.loads(post.body) == {"name": "spare", "device_type": "tv"}
    assert result == {"id": 400, "device_name": "spare", "type": "tv"}
    assert rce.read_config()["devices"] == {"spare": {"id": 400, "type": "tv"}}


def test_create_prints_the_new_id(rce, fake_rce):
    result = rce.run("device", "create", "spare", "--type", "stb", "--yes")

    assert result.returncode == 0, result.stderr
    assert "400" in result.stdout


def test_create_prompt_shows_quota_and_permanence_and_y_creates(rce, fake_rce):
    fake_rce.user["organisation"].update(max_devices=10, current_devices={"tv": 3, "stb": 4})

    result = rce.run_tty("device", "create", "spare", "--type", "tv", answer="y")

    assert result.returncode == 0, result.stderr
    assert "7/10" in result.stderr
    assert "permanent, cannot be deleted" in result.stderr
    assert len(fake_rce.requests_to("POST", "/api/v1/devices")) == 1


def test_create_declined_at_the_prompt_creates_nothing(rce, fake_rce):
    result = rce.run_tty("device", "create", "spare", "--type", "tv", answer="n")

    assert result.returncode == 2
    assert fake_rce.requests_to("POST", "/api/v1/devices") == []
    assert not rce.config.exists()


def test_create_with_a_device_name_already_in_use_creates_nothing(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    result = rce.run("device", "create", "player", "--type", "stb", "--yes")

    assert result.returncode == 2
    assert "already names Cloud Device 351" in result.stderr
    assert fake_rce.requests_to("POST", "/api/v1/devices") == []


def test_create_with_an_all_digit_name_creates_nothing(rce, fake_rce):
    result = rce.run("device", "create", "1234", "--type", "stb", "--yes")

    assert result.returncode == 2
    assert fake_rce.requests_to("POST", "/api/v1/devices") == []
