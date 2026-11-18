"""`rce screenshot`: the foreground dev app, through the installer's inspect page (port 80)."""

import re

from conftest import TOKEN
from fake_rce import SCREENSHOT_JPEG, SCREENSHOT_NOT_OK, Response, inspect_page, recorded_answer

PORT_80 = "/instance/uuid-351/api/v0/ports/80/http"  # RCE's path; glossary-ok
INSPECT = f"{PORT_80}/plugin_inspect"
IMAGE = f"{PORT_80}/pkgs/dev.jpg"
HOME_SCREEN = '<app id="562859" type="appl" version="1.0.0">Roku</app>'


def running_player(rce, fake_rce, password: str | None = None) -> None:
    """A running Cloud Device named player, with its Dev Password stored as setup-dev stores it."""
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.name_device("351", "player")
    if password is not None:
        rce.config.write_text(rce.config.read_text() + f'dev_password = "{password}"\n')


def test_screenshot_writes_the_installers_image_to_the_file(rce, fake_rce):
    running_player(rce, fake_rce, fake_rce.dev_password)

    result = rce.run("screenshot", "player", "-o", "shot.jpg")

    assert result.returncode == 0, result.stderr
    assert (rce.cwd / "shot.jpg").read_bytes() == SCREENSHOT_JPEG
    assert fake_rce.forms[0]["mysubmit"] == (None, b"Screenshot")
    [download] = [r for r in fake_rce.requests_to("GET", IMAGE) if "authorization" in r.headers]
    [time] = re.findall(r"pkgs/dev\.jpg\?time=(\d+)", recorded_answer("installer-inspect-screenshot")["body"])
    assert download.query == {"time": [time]}  # the link in the recorded page
    for request in fake_rce.requests_to("POST", INSPECT) + fake_rce.requests_to("GET", IMAGE):
        assert request.headers["x-authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in request.headers.get("authorization", "")
    assert "shot.jpg" in result.stdout
    for secret in (TOKEN, fake_rce.dev_password):
        assert secret not in result.stdout + result.stderr


def test_screenshot_json_names_the_file_and_its_size(rce, fake_rce):
    running_player(rce, fake_rce, fake_rce.dev_password)

    shot = rce.json("screenshot", "player", "-o", "shot.jpg")

    assert shot == {
        "id": 351,
        "device_name": "player",
        "path": str(rce.cwd / "shot.jpg"),
        "bytes": len(SCREENSHOT_JPEG),
    }


def test_screenshot_retries_while_the_installer_takes_none(rce, fake_rce):
    running_player(rce, fake_rce, fake_rce.dev_password)
    fake_rce.fail_next("POST", INSPECT, Response(200, inspect_page(SCREENSHOT_NOT_OK)))

    result = rce.run("screenshot", "player", "-o", "shot.jpg")

    assert result.returncode == 0, result.stderr
    assert (rce.cwd / "shot.jpg").read_bytes() == SCREENSHOT_JPEG


def test_screenshot_without_a_dev_app_in_the_foreground_exits_4(rce, fake_rce):
    running_player(rce, fake_rce, fake_rce.dev_password)
    fake_rce.active_app = HOME_SCREEN

    result = rce.run("screenshot", "player", "-o", "shot.jpg")

    assert result.returncode == 4
    assert "no dev app in the foreground" in result.stderr
    assert "(Screenshot not ok)" in result.stderr  # the installer's own words
    assert "rce launch player" in result.stderr
    assert len(fake_rce.forms) > 1  # it retried
    assert not (rce.cwd / "shot.jpg").exists()


def test_screenshot_with_a_wrong_dev_password_exits_4(rce, fake_rce):
    running_player(rce, fake_rce, "not-the-PASSWORD")

    result = rce.run("screenshot", "player", "-o", "shot.jpg")

    assert result.returncode == 4
    assert "wrong or missing Dev Password for player" in result.stderr
    assert "not-the-PASSWORD" not in result.stdout + result.stderr


def test_screenshot_without_a_dev_password_names_setup_dev_and_the_variable(rce, fake_rce):
    running_player(rce, fake_rce)

    result = rce.run("screenshot", "player", "-o", "shot.jpg")

    assert result.returncode == 4
    assert "rce device setup-dev player" in result.stderr
    assert "RCE_DEV_PASSWORD" in result.stderr
    assert fake_rce.requests_to("POST", INSPECT) == []


def test_screenshot_needs_an_output_file(rce, fake_rce):
    running_player(rce, fake_rce, fake_rce.dev_password)

    result = rce.run("screenshot", "player")

    assert result.returncode == 2
    assert "-o" in result.stderr


def test_screenshot_into_a_missing_directory_is_a_usage_error(rce, fake_rce):
    running_player(rce, fake_rce, fake_rce.dev_password)

    result = rce.run("screenshot", "player", "-o", "nowhere/shot.jpg")

    assert result.returncode == 2
    assert "cannot write nowhere/shot.jpg" in result.stderr


def test_screenshot_signs_in_with_rce_dev_password_by_id_without_a_device_name(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.env["RCE_DEV_PASSWORD"] = fake_rce.dev_password

    result = rce.run("screenshot", "351", "-o", "shot.jpg")

    assert result.returncode == 0, result.stderr
    assert (rce.cwd / "shot.jpg").read_bytes() == SCREENSHOT_JPEG
    assert fake_rce.dev_password not in result.stdout + result.stderr
