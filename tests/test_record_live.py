"""`scripts/record-live`: record RCE's real answers, redacted, for the fake.

Run against the fake RCE, which plays the live service: its token, Dev Password,
WebRTC credentials, serial numbers and identity are the secrets that must not
reach a recorded file.
"""

import json
import signal
import subprocess
import time

from conftest import REPO, TOKEN
from fake_rce import USER_ID, WEBRTC_SECRETS, Response

RECORD_LIVE = REPO / "scripts" / "record-live"
START = "/api/v1/devices/351/start"
STOP = "/api/v1/devices/351/stop"
CORE_FILES = {
    "user-me", "devices", "device", "snapshots", "snapshot",
    "firmware-versions", "trial-status", "usage-user",
}
RUN_FILES = {
    "device-running", "input-ready", "ecp-device-info", "ecp-active-app",
    "installer-wrong-password", "installer-inspect",
    "install-installed", "install-identical", "install-failed", "install-form-error",
    "ecp-launch-dev", "installer-inspect-screenshot",
}
RUN_UUID = "00000000-0000-4000-8000-000000000000"
IDENTITY = ("someone.real@corp.test", "Real Person", "Real Org Ltd")


def record(rce, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(RECORD_LIVE), *args, "--out", str(rce.cwd / "recorded")],
        cwd=rce.cwd,
        env=rce.env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def player(rce, fake_rce, password: str | None = None) -> None:
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    if password is not None:
        rce.config.write_text(rce.config.read_text() + f'dev_password = "{password}"\n')
    email, full_name, org = IDENTITY
    fake_rce.user.update(username=email, email=email, full_name=full_name)
    fake_rce.user["organisation"]["name"] = org


def recorded(rce) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in (rce.cwd / "recorded").glob("*.json")}


def secrets_in(rce, fake_rce) -> list[str]:
    text = "".join(p.read_text() for p in (rce.cwd / "recorded").glob("*.json"))
    secrets = [TOKEN, fake_rce.dev_password, *WEBRTC_SECRETS, *IDENTITY, USER_ID, "XY0000000351"]
    return [s for s in secrets if s in text]


def test_without_run_it_records_only_free_core_api_reads(rce, fake_rce):
    player(rce, fake_rce)

    result = record(rce, "player")

    assert result.returncode == 0, result.stderr
    files = recorded(rce)
    assert set(files) == CORE_FILES
    assert files["device"] == {
        "request": "GET /api/v1/devices/351",
        "status": 200,
        "headers": {"content-type": "application/json"},
        "body": files["device"]["body"],
    }
    assert files["device"]["body"]["id"] == 351
    assert not fake_rce.requests_to("POST", START)
    assert secrets_in(rce, fake_rce) == []


def test_identity_fields_hold_a_placeholder(rce, fake_rce):
    player(rce, fake_rce)

    record(rce, "player")

    user = recorded(rce)["user-me"]["body"]
    assert (user["email"], user["username"], user["full_name"]) == ("REDACTED",) * 3
    assert user["organisation"]["name"] == "REDACTED"
    assert user["id"] == "REDACTED"  # the account's id, also the Run's creator_id
    assert recorded(rce)["device"]["body"]["serial_number"] == "REDACTED"


def test_run_records_the_runs_answers_and_stops_it(rce, fake_rce):
    player(rce, fake_rce, fake_rce.dev_password)

    result = record(rce, "player", "--run")

    assert result.returncode == 0, result.stderr
    files = recorded(rce)
    assert set(files) == CORE_FILES | RUN_FILES
    assert fake_rce.requests_to("POST", START)[0].json()["max_runtime"] == 600
    assert fake_rce.requests_to("POST", STOP)
    assert fake_rce.devices[351]["status"] == "shutdown"
    assert files["device-running"]["body"]["status"] == "running"
    assert files["input-ready"]["body"] == {"ready": True}
    assert "<device-info>" in files["ecp-device-info"]["body"]
    assert files["installer-wrong-password"]["status"] == 401
    assert files["installer-wrong-password"]["headers"]["www-authenticate"].startswith("Digest ")
    assert "Screenshot" in files["installer-inspect"]["body"]
    assert secrets_in(rce, fake_rce) == []


def test_run_records_the_installers_pages_for_each_outcome(rce, fake_rce):
    player(rce, fake_rce, fake_rce.dev_password)
    fake_rce.next_install_fails = True  # record-live installs the app meant to fail first

    result = record(rce, "player", "--run")

    assert result.returncode == 0, result.stderr
    files = recorded(rce)
    assert files["install-failed"]["status"] == 400
    assert "Install Success" in files["install-installed"]["body"]
    assert "Identical to previous version" in files["install-identical"]["body"]
    assert "Application File is Empty" in files["install-form-error"]["body"]
    assert files["ecp-launch-dev"]["status"] in (200, 204)  # live: 204 in Run 4291, 200 in Run 4300
    assert "pkgs/dev.jpg" in files["installer-inspect-screenshot"]["body"]
    installs = [form for form in fake_rce.forms if form["mysubmit"] == (None, b"Install")]
    failed, without_archive, installed, identical = installs
    assert identical["archive"] == installed["archive"]
    assert failed["archive"] != installed["archive"]
    assert "archive" not in without_archive
    assert secrets_in(rce, fake_rce) == []


def test_run_secrets_hold_a_placeholder(rce, fake_rce):
    player(rce, fake_rce, fake_rce.dev_password)

    record(rce, "player", "--run")

    run = recorded(rce)["device-running"]["body"]["running_device"]
    assert (run["janus_pin"], run["janus_token"]) == ("REDACTED", "REDACTED")
    assert {s["credential"] for s in run["janus_ice_servers"]} == {"REDACTED"}
    assert "XY0000000351" not in recorded(rce)["ecp-device-info"]["body"]


def test_run_stops_the_run_when_a_step_fails(rce, fake_rce):
    player(rce, fake_rce, fake_rce.dev_password)
    device_info = "/instance/uuid-351-9000/api/v0/ports/8060/http/query/device-info"  # glossary-ok
    fake_rce.fail_next("GET", device_info, Response(500, {"detail": "boom"}))

    result = record(rce, "player", "--run")

    assert result.returncode != 0
    assert "boom" in result.stderr
    assert fake_rce.requests_to("POST", STOP)
    assert fake_rce.devices[351]["status"] == "shutdown"
    assert not (rce.cwd / "recorded").exists()


def test_run_starts_nothing_without_a_dev_password(rce, fake_rce):
    player(rce, fake_rce)  # the installer step could not succeed

    result = record(rce, "player", "--run")

    assert result.returncode != 0
    assert "Dev Password" in result.stderr
    assert not fake_rce.requests_to("POST", START)


def test_run_starts_nothing_while_a_cloud_device_is_running(rce, fake_rce):
    player(rce, fake_rce, fake_rce.dev_password)
    fake_rce.add_device(352, "Personal RCE TV", "tv", running=True)

    result = record(rce, "player", "--run")

    assert result.returncode != 0
    assert "352" in result.stderr
    assert not fake_rce.requests_to("POST", START)
    assert not fake_rce.requests_to("POST", "/api/v1/devices/352/stop")


def test_run_exits_non_zero_when_the_run_did_not_stop(rce, fake_rce):
    player(rce, fake_rce, fake_rce.dev_password)
    fake_rce.fail_next("POST", STOP, Response(500, {"detail": "stop broke"}), times=5)

    result = record(rce, "player", "--run")

    assert result.returncode != 0
    assert "still running" in result.stderr
    assert "rce device stop player" in result.stderr
    assert not (rce.cwd / "recorded").exists()


def test_a_kill_while_the_run_starts_still_stops_it(rce, fake_rce):
    player(rce, fake_rce, fake_rce.dev_password)
    fake_rce.boot_delay = 3
    process = subprocess.Popen(
        [str(RECORD_LIVE), "player", "--run", "--out", str(rce.cwd / "recorded")],
        cwd=rce.cwd, env=rce.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    deadline = time.monotonic() + 60
    while not fake_rce.requests_to("POST", START) and time.monotonic() < deadline:
        time.sleep(0.05)
    process.send_signal(signal.SIGTERM)

    _, stderr = process.communicate(timeout=60)

    assert process.returncode != 0, stderr
    assert fake_rce.requests_to("POST", STOP)
    assert fake_rce.devices[351]["status"] == "shutdown"
    assert not (rce.cwd / "recorded").exists()


def test_creator_and_idp_ids_hold_a_placeholder_even_when_nothing_else_names_them(rce, fake_rce):
    player(rce, fake_rce, fake_rce.dev_password)
    fake_rce.user["id"] = "a-different-account-id"  # the Run's creator_id matches nothing else
    fake_rce.user["organisation"]["idp_id"] = "idp-of-the-real-org"

    record(rce, "player", "--run")

    files = recorded(rce)
    assert files["device-running"]["body"]["running_device"]["creator_id"] == "REDACTED"
    assert files["user-me"]["body"]["organisation"]["idp_id"] == "REDACTED"
    text = "".join(p.read_text() for p in (rce.cwd / "recorded").glob("*.json"))
    assert USER_ID not in text
    assert "idp-of-the-real-org" not in text


def test_the_runs_instance_uuid_holds_the_placeholder_everywhere(rce, fake_rce):
    player(rce, fake_rce, fake_rce.dev_password)

    record(rce, "player", "--run")

    files = recorded(rce)
    run = files["device-running"]["body"]["running_device"]
    assert run["instance_uuid"] == RUN_UUID
    assert run["instance_api_url"].endswith(f"/instance/{RUN_UUID}")  # glossary-ok
    assert run["janus_websocket_url"].endswith(f"/instance/{RUN_UUID}/janus")  # glossary-ok
    assert files["input-ready"]["request"] == f"GET /instance/{RUN_UUID}/api/v0/input/ready"  # glossary-ok
    text = "".join(p.read_text() for p in (rce.cwd / "recorded").glob("*.json"))
    assert "uuid-351-" not in text  # the fake's instance_uuid for the Run


def test_the_organisation_id_holds_the_placeholder(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.user["organisation"]["id"] = 4321

    record(rce, "player")

    assert recorded(rce)["user-me"]["body"]["organisation"]["id"] == 1


# An installer page as Roku OS serves it, cut down: the lines `rce` and the fake
# read (a status line, the messages, a rendered message, the screenshot link) amid Roku's own.
KEPT_LINES = [
    '<font color="red">Install Success.</font>',
    """      var params = JSON.parse('{"messages":[{"text":"Install Success.","type":"success"}]}');""",
    "      Shell.create('Roku.Message').trigger('Set message type', 'success')"
    ".trigger('Set message content', 'Screenshot ok').trigger('Render', node);",
    """      screenshoot.innerHTML = '<hr /><img src="pkgs/dev.jpg?time=1794937786">';""",
]
FULL_PAGE = "\n".join([
    "<!--   ",
    "(c) 2019-2023 Roku, Inc.  All content herein is protected by U.S.",
    "-->",
    "<html>",
    "<head><title> Roku Development Kit </title></head>",
    '<body><div style="display:none">',
    KEPT_LINES[0],
    "</div>",
    '<script type="text/javascript">',
    KEPT_LINES[1],
    "      var hasPackage = params.packages.length > 0;",
    KEPT_LINES[2],
    KEPT_LINES[3],
    "</script></body></html>",
])


def test_installer_pages_keep_only_the_lines_rce_reads(rce, fake_rce):
    player(rce, fake_rce, fake_rce.dev_password)
    install = "/instance/uuid-351-9000/api/v0/ports/80/http/plugin_install"  # glossary-ok
    fake_rce.fail_next("POST", install, Response(200, FULL_PAGE, {"content-type": "text/html"}))

    result = record(rce, "player", "--run")

    assert result.returncode == 0, result.stderr
    assert recorded(rce)["install-failed"]["body"] == "".join(f"{line}\n" for line in KEPT_LINES)
