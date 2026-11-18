def test_naming_a_device_records_a_device_name_that_resolve_prints(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")

    named = rce.name_device("351", "player")
    resolve = rce.run("device", "resolve", "player")

    assert named.returncode == 0, named.stderr
    assert (resolve.returncode, resolve.stdout) == (0, "351\n")


def test_resolve_json_gives_id_and_type(rce, fake_rce):
    fake_rce.add_device(352, "Personal RCE TV", "tv")
    rce.name_device("352", "tv")

    assert rce.json("device", "resolve", "tv") == {"id": 352, "type": "tv"}


def test_resolve_works_without_a_token_or_rce(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    rce.rk_config.unlink()
    rce.env["RCE_API_URL"] = "http://127.0.0.1:9/api/v1"

    result = rce.run("device", "resolve", "player")

    assert (result.returncode, result.stdout) == (0, "351\n"), result.stderr


def test_resolve_of_an_unknown_name_is_not_found(rce):
    result = rce.run("device", "resolve", "nope")

    assert result.returncode == 3
    assert "no Device Name 'nope'" in result.stderr


def test_resolve_of_an_id_without_a_device_name_is_not_found(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")

    result = rce.run("device", "resolve", "351")

    assert result.returncode == 3
    assert "Cloud Device 351 has no Device Name" in result.stderr


def test_naming_an_unknown_id_is_not_found_and_writes_nothing(rce, fake_rce):
    result = rce.name_device("999", "ghost")

    assert result.returncode == 3, result.stderr
    assert not rce.config.exists()


def test_a_name_taken_by_another_device_is_refused(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    fake_rce.add_device(352, "Personal RCE TV", "tv")
    rce.name_device("351", "main")

    result = rce.name_device("352", "main")

    assert result.returncode == 2
    assert "already names Cloud Device 351" in result.stderr
    assert rce.json("device", "resolve", "main")["id"] == 351


def test_force_moves_a_taken_name_to_the_other_device(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    fake_rce.add_device(352, "Personal RCE TV", "tv")
    rce.name_device("351", "main")

    result = rce.name_device("352", "main", "--force")

    assert result.returncode == 0, result.stderr
    assert rce.read_config()["devices"] == {"main": {"id": 352, "type": "tv"}}


def test_naming_a_named_device_renames_it_and_keeps_its_stored_fields(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    # A field a later command stores with the Device Name.
    rce.config.write_text(rce.config.read_text() + "dev_snapshot_id = 1234\n")

    result = rce.name_device("player", "box")

    assert result.returncode == 0, result.stderr
    assert rce.read_config()["devices"] == {
        "box": {"id": 351, "type": "stb", "dev_snapshot_id": 1234}
    }
    assert rce.run("device", "resolve", "player").returncode == 3


def test_a_device_name_cannot_be_all_digits(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")

    result = rce.name_device("351", "352")

    assert result.returncode == 2
    assert not rce.config.exists()


def test_config_is_created_on_first_write_with_mode_0600(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    assert not rce.config.exists()

    rce.name_device("351", "player")

    assert rce.config.stat().st_mode & 0o777 == 0o600
    assert rce.read_config() == {"devices": {"player": {"id": 351, "type": "stb"}}}


def test_config_honours_xdg_config_home(rce, fake_rce, tmp_path):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.env["XDG_CONFIG_HOME"] = str(tmp_path / "xdg")

    rce.name_device("351", "player")

    config = tmp_path / "xdg" / "roku-rce" / "devices.toml"
    assert config.stat().st_mode & 0o777 == 0o600
    assert not rce.config.exists()


def test_config_defaults_to_dot_config_in_home(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    del rce.env["XDG_CONFIG_HOME"]

    rce.name_device("351", "player")

    assert rce.config.stat().st_mode & 0o777 == 0o600


def test_an_unreadable_config_is_a_usage_error(rce):
    rce.config.parent.mkdir(parents=True)
    rce.config.write_text("devices = [not toml")

    result = rce.run("device", "resolve", "player")

    assert result.returncode == 2
    assert str(rce.config) in result.stderr
