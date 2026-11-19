"""`rce sideload`: install a zip or RSG package through the Run's installer (port 80)."""

import json

import pytest

from conftest import TOKEN
from fake_rce import GATEWAY_RATE_LIMIT, Response

INSTALL = "/instance/uuid-351/api/v0/ports/80/http/plugin_install"  # RCE's path; glossary-ok
ARCHIVE = b"PK\x03\x04 a tiny dev app \x00\xff"


def running_player(rce, fake_rce, password: str | None = None) -> None:
    """A running Cloud Device named player, with its Dev Password stored as setup-dev stores it."""
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.name_device("351", "player")
    if password is not None:
        rce.config.write_text(rce.config.read_text() + f'dev_password = "{password}"\n')


def app_zip(rce, content: bytes = ARCHIVE):
    path = rce.cwd / "app.zip"
    path.write_bytes(content)
    return path


def assert_no_secrets(result, fake_rce) -> None:
    for secret in (TOKEN, fake_rce.dev_password):
        assert secret not in result.stdout + result.stderr


def test_sideload_installs_the_archive_with_digest_and_the_token_in_x_authorization(rce, fake_rce):
    running_player(rce, fake_rce, fake_rce.dev_password)
    app_zip(rce)

    result = rce.run("sideload", "player", "app.zip")

    assert result.returncode == 0, result.stderr
    assert fake_rce.installed_archive == ARCHIVE
    challenge, signed = fake_rce.requests_to("POST", INSTALL)
    for request in (challenge, signed):
        assert request.headers["x-authorization"] == f"Bearer {TOKEN}"
        assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert "authorization" not in challenge.headers  # the token never goes to the device
    assert signed.headers["authorization"].startswith("Digest ")
    [form] = fake_rce.forms
    assert form["mysubmit"] == (None, b"Install")
    assert form["archive"] == ("app.zip", ARCHIVE)
    assert "Installed app.zip on player (351)" in result.stdout
    assert_no_secrets(result, fake_rce)


def test_sideload_of_an_unchanged_archive_reports_identical(rce, fake_rce):
    running_player(rce, fake_rce, fake_rce.dev_password)
    app_zip(rce)
    fake_rce.installed_archive = ARCHIVE

    result = rce.run("sideload", "player", "app.zip", "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "id": 351,
        "device_name": "player",
        "file": "app.zip",
        "outcome": "identical",
    }


def test_sideload_json_reports_installed(rce, fake_rce):
    running_player(rce, fake_rce, fake_rce.dev_password)
    app_zip(rce)

    assert rce.json("sideload", "player", "app.zip")["outcome"] == "installed"


def test_a_failed_install_exits_4_with_the_installers_reason(rce, fake_rce):
    """Live, the device answers a failed install 400 with its Install page."""
    running_player(rce, fake_rce, fake_rce.dev_password)
    app_zip(rce)
    fake_rce.next_install_fails = True

    result = rce.run("sideload", "player", "app.zip")

    assert result.returncode == 4, result.stderr
    assert (
        "player (351) did not install app.zip: "
        "Install Failure: Unzip failed. Invalid or corrupt zip archive.  Unloading."
    ) in result.stderr
    assert "Application Received" not in result.stderr  # the reason, not every message
    assert result.stdout == ""


def test_a_failed_install_leaves_no_dev_app_to_launch(rce, fake_rce):
    """The recorded failure page lists no installed package: the old dev app is gone."""
    running_player(rce, fake_rce, fake_rce.dev_password)
    app_zip(rce)
    fake_rce.installed_archive = b"the dev app before"
    fake_rce.next_install_fails = True

    rce.run("sideload", "player", "app.zip")
    result = rce.run("launch", "player")

    assert result.returncode == 3, result.stderr
    assert "no dev app is installed" in result.stderr


def test_a_wrong_dev_password_says_so_and_exits_4(rce, fake_rce):
    running_player(rce, fake_rce, "not-the-PASSWORD")
    app_zip(rce)

    result = rce.run("sideload", "player", "app.zip")

    assert result.returncode == 4
    assert "wrong or missing Dev Password for player" in result.stderr
    assert fake_rce.installed_archive is None
    assert "not-the-PASSWORD" not in result.stdout + result.stderr
    assert_no_secrets(result, fake_rce)


def test_rces_own_401_blames_the_token_not_the_dev_password(rce, fake_rce):
    running_player(rce, fake_rce, fake_rce.dev_password)
    app_zip(rce)
    fake_rce.fail_next("POST", INSTALL, Response(401, {"detail": "Not authenticated"}))

    result = rce.run("sideload", "player", "app.zip")

    assert result.returncode == 4
    assert "rejected the token" in result.stderr
    assert "Dev Password" not in result.stderr
    assert_no_secrets(result, fake_rce)


def test_no_dev_password_names_setup_dev_and_the_variable(rce, fake_rce):
    running_player(rce, fake_rce)
    app_zip(rce)

    result = rce.run("sideload", "player", "app.zip")

    assert result.returncode == 4
    assert "no Dev Password" in result.stderr
    assert "rce device setup-dev player" in result.stderr
    assert "RCE_DEV_PASSWORD" in result.stderr
    assert fake_rce.requests_to("POST", INSTALL) == []


def test_a_cloud_device_without_a_device_name_has_no_stored_dev_password(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    app_zip(rce)

    result = rce.run("sideload", "351", "app.zip")

    assert result.returncode == 4
    assert "no Dev Password" in result.stderr
    assert "rce device alias 351 <name>" in result.stderr  # glossary-ok: the command's name
    assert "rce device setup-dev <name>" in result.stderr
    assert "rce device setup-dev 351" not in result.stderr  # exits 3 without a Device Name
    assert "RCE_DEV_PASSWORD" in result.stderr
    assert fake_rce.requests_to("POST", INSTALL) == []


def test_sideload_to_a_stopped_cloud_device_exits_4(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    rce.config.write_text(rce.config.read_text() + 'dev_password = "x"\n')
    app_zip(rce)

    result = rce.run("sideload", "player", "app.zip")

    assert result.returncode == 4
    assert "not running" in result.stderr


def test_a_rate_limit_from_the_device_port_is_never_retried(rce, fake_rce):
    """The device's answer passes through RCE as is, so it could carry the gateway's markers."""
    running_player(rce, fake_rce, fake_rce.dev_password)
    app_zip(rce)
    fake_rce.fail_next("POST", INSTALL, GATEWAY_RATE_LIMIT, times=4)

    result = rce.run("sideload", "player", "app.zip")

    assert result.returncode == 4
    assert len(fake_rce.requests_to("POST", INSTALL)) == 1
    assert fake_rce.installed_archive is None


def test_sideload_of_a_missing_file_is_a_usage_error(rce, fake_rce):
    running_player(rce, fake_rce, fake_rce.dev_password)

    result = rce.run("sideload", "player", "missing.zip")

    assert result.returncode == 2
    assert "cannot read missing.zip" in result.stderr
    assert fake_rce.requests_to("POST", INSTALL) == []


def test_sideload_sends_an_rsg_package_as_is(rce, fake_rce):
    running_player(rce, fake_rce, fake_rce.dev_password)
    package = rce.cwd / "package.bin"
    package.write_bytes(b"hsqs squashfs RSG build")

    assert rce.json("sideload", "player", str(package))["outcome"] == "installed"
    assert fake_rce.forms[-1]["archive"] == ("package.bin", b"hsqs squashfs RSG build")


def test_rce_dev_password_signs_in_without_a_stored_one(rce, fake_rce):
    running_player(rce, fake_rce)
    rce.env["RCE_DEV_PASSWORD"] = fake_rce.dev_password
    app_zip(rce)

    result = rce.run("sideload", "player", "app.zip")

    assert result.returncode == 0, result.stderr
    assert fake_rce.installed_archive == ARCHIVE
    assert_no_secrets(result, fake_rce)


@pytest.mark.parametrize("ending", ["\n", "\r\n"])
def test_rce_dev_password_signs_in_without_its_trailing_newline(rce, fake_rce, ending):
    running_player(rce, fake_rce)
    rce.env["RCE_DEV_PASSWORD"] = fake_rce.dev_password + ending  # a `gh secret set` pipe, a file
    app_zip(rce)

    result = rce.run("sideload", "player", "app.zip")

    assert result.returncode == 0, result.stderr
    assert fake_rce.installed_archive == ARCHIVE


def test_rce_dev_password_keeps_a_trailing_space(rce, fake_rce):
    fake_rce.dev_password = "dev-PASSWORD-secret "  # one set in the web viewer could end in a space
    running_player(rce, fake_rce)
    rce.env["RCE_DEV_PASSWORD"] = fake_rce.dev_password
    app_zip(rce)

    result = rce.run("sideload", "player", "app.zip")

    assert result.returncode == 0, result.stderr
    assert fake_rce.installed_archive == ARCHIVE


def test_a_stored_dev_password_is_used_as_stored(rce, fake_rce):
    fake_rce.dev_password = "stored-PASSWORD\n"
    running_player(rce, fake_rce, "stored-PASSWORD\\n")  # TOML's escape for the newline
    app_zip(rce)

    result = rce.run("sideload", "player", "app.zip")

    assert result.returncode == 0, result.stderr
    assert fake_rce.installed_archive == ARCHIVE


def test_rce_dev_password_wins_over_a_stored_one(rce, fake_rce):
    running_player(rce, fake_rce, "not-the-PASSWORD")
    rce.env["RCE_DEV_PASSWORD"] = fake_rce.dev_password
    app_zip(rce)

    result = rce.run("sideload", "player", "app.zip")

    assert result.returncode == 0, result.stderr
    assert fake_rce.installed_archive == ARCHIVE


def test_rce_dev_password_serves_a_cloud_device_addressed_by_id_without_a_device_name(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.env["RCE_DEV_PASSWORD"] = fake_rce.dev_password
    app_zip(rce)

    result = rce.run("sideload", "351", "app.zip")

    assert result.returncode == 0, result.stderr
    assert fake_rce.installed_archive == ARCHIVE
    assert_no_secrets(result, fake_rce)


def test_a_wrong_rce_dev_password_says_which_it_was(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.env["RCE_DEV_PASSWORD"] = "not-the-PASSWORD"
    app_zip(rce)

    result = rce.run("sideload", "351", "app.zip")

    assert result.returncode == 4
    assert "wrong or missing Dev Password for Cloud Device 351" in result.stderr
    assert "RCE_DEV_PASSWORD" in result.stderr
    assert "not-the-PASSWORD" not in result.stdout + result.stderr
