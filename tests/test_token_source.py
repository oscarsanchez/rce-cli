"""Where `rce` finds the RCE token: RCE_TOKEN, then RK_RCE_TOKEN, then rk's file."""

import json

from conftest import TOKEN

OTHER = "eyJother.rce-token.SECRET"


def sent_tokens(fake_rce) -> list[str]:
    return [r.headers.get("authorization") for r in fake_rce.requests]


def test_rce_token_overrides_rk_token_and_rk_config_file(rce, fake_rce):
    rce.write_rk_config({"token": OTHER})
    rce.env.update(RCE_TOKEN=TOKEN, RK_RCE_TOKEN=OTHER)

    assert rce.json("device", "list") == []
    assert sent_tokens(fake_rce) == [f"Bearer {TOKEN}"]


def test_rk_rce_token_overrides_rk_config_file(rce, fake_rce):
    rce.write_rk_config({"token": OTHER})
    rce.env["RK_RCE_TOKEN"] = TOKEN

    assert rce.json("device", "list") == []
    assert sent_tokens(fake_rce) == [f"Bearer {TOKEN}"]


def test_rk_config_file_keeps_other_keys_readable(rce, fake_rce):
    rce.write_rk_config({"token": TOKEN, "something_rk_stores": 1})

    assert rce.json("device", "list") == []


def test_missing_token_is_a_usage_error_naming_where_rce_looked(rce, fake_rce):
    rce.rk_config.unlink()

    result = rce.run("device", "list")

    assert result.returncode == 2
    assert "RCE_TOKEN" in result.stderr
    assert "RK_RCE_TOKEN" in result.stderr
    assert str(rce.rk_config) in result.stderr
    assert "rce token set" in result.stderr
    assert fake_rce.requests == []


def test_rk_config_file_without_a_token_counts_as_missing(rce, fake_rce):
    rce.write_rk_config({})

    result = rce.run("device", "list")

    assert result.returncode == 2
    assert str(rce.rk_config) in result.stderr


def test_roku_rce_config_path_moves_rks_file_as_it_does_for_rk(rce, fake_rce, tmp_path):
    moved = tmp_path / "elsewhere.json"
    moved.write_text(json.dumps({"token": TOKEN}))
    rce.write_rk_config({"token": OTHER})
    rce.env["ROKU_RCE_CONFIG_PATH"] = str(moved)

    assert rce.json("device", "list") == []
    assert sent_tokens(fake_rce) == [f"Bearer {TOKEN}"]


def test_token_set_writes_where_roku_rce_config_path_points(rce, fake_rce, tmp_path):
    moved = tmp_path / "elsewhere.json"
    rce.env["ROKU_RCE_CONFIG_PATH"] = str(moved)
    before = rce.rk_config.read_text()

    result = rce.run("token", "set", input=OTHER)

    assert result.returncode == 0, result.stderr
    assert json.loads(moved.read_text()) == {"token": OTHER}
    assert rce.rk_config.read_text() == before
