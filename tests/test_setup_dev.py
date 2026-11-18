"""`rce device setup-dev`: take a fresh Cloud Device to a Dev Snapshot.

The fake plays the Cloud Device; the test plays the person at the terminal,
doing on the "device" what each pause asks (by changing the fake's state)
before pressing Enter.
"""

import json
import re

from conftest import TOKEN
from fake_rce import snapshot_out

COMBO = "/xi/developer-settings-combo"
STOP = "/api/v1/devices/351/stop"
START = "/api/v1/devices/351/start"


def fresh_player(rce, fake_rce) -> None:
    """Player 351 as RCE creates it: in guided setup, dev mode off, ECP limited."""
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    fake_rce.in_guided_setup, fake_rce.dev_mode, fake_rce.ecp_mode = True, False, "limited"


def link_account(tty, fake_rce) -> None:
    tty.expect(r"30 minutes")
    tty.expect(r"Press Enter")
    fake_rce.in_guided_setup = False  # the person finished guided setup and the account link
    tty.answer()


def enable_dev_mode(tty, fake_rce) -> None:
    tty.expect(r"Enable installer")
    tty.expect(r"Press Enter")
    tty.answer()  # the password keyboard shows: rce types the Dev Password
    tty.expect(r"Set password and reboot")
    tty.expect(r"Press Enter")
    fake_rce.dev_mode = True  # the person set it and the Cloud Device rebooted
    tty.answer()


def allow_mobile_apps(tty, fake_rce) -> None:
    tty.expect(r"Control by mobile apps")
    instructions = tty.expect(r"Press Enter")
    # The path and choices as the live Player shows them (ticket 11).
    assert "Control by mobile apps > Network access" in instructions
    assert "Permissive" in instructions
    fake_rce.ecp_mode = "permissive"
    tty.answer()


def keys_typed(fake_rce) -> list[str]:
    return [
        r.path.rsplit("/", 1)[1]
        for r in fake_rce.requests
        if r.method == "POST" and "/input/keypress/" in r.path
    ]


def test_setup_dev_takes_a_fresh_cloud_device_to_a_dev_snapshot(rce, fake_rce):
    fresh_player(rce, fake_rce)

    tty = rce.interactive("device", "setup-dev", "player", "--yes", "--json")
    link_account(tty, fake_rce)
    enable_dev_mode(tty, fake_rce)
    allow_mobile_apps(tty, fake_rce)
    result = tty.finish()

    assert result.returncode == 0, result.stderr
    entry = rce.read_config()["devices"]["player"]
    password = entry["dev_password"]
    assert re.fullmatch(r"[A-Za-z0-9]{16,}", password)
    assert keys_typed(fake_rce) == [f"Lit_{c}" for c in password]
    [start] = fake_rce.requests_to("POST", START)
    assert start.json()["snapshot_id"] == 998  # the live state, not the base
    [combo] = [r for r in fake_rce.requests if r.path.endswith(COMBO)]
    assert combo.method == "POST" and combo.headers["authorization"] == f"Bearer {TOKEN}"
    [snapshot] = [s for s in fake_rce.snapshots[351] if s["name"] == "dev-ready"]
    assert entry["dev_snapshot_id"] == snapshot["id"]
    assert len(fake_rce.requests_to("POST", STOP)) == 1
    assert result.stdout and '"dev_snapshot_id"' in result.stdout
    assert password not in result.stdout + result.stderr
    assert rce.config.stat().st_mode & 0o777 == 0o600


def test_without_a_terminal_it_refuses_at_the_human_step_and_stops_its_run(rce, fake_rce):
    fresh_player(rce, fake_rce)

    result = rce.run("device", "setup-dev", "player", "--yes")

    assert result.returncode == 4
    assert "needs a person" in result.stderr
    assert "guided setup" in result.stderr
    assert len(fake_rce.requests_to("POST", START)) == 1
    assert len(fake_rce.requests_to("POST", STOP)) == 1


def test_without_a_terminal_or_yes_it_says_it_needs_a_person_and_starts_nothing(rce, fake_rce):
    fresh_player(rce, fake_rce)

    result = rce.run("device", "setup-dev", "player")

    assert result.returncode == 4
    assert "setup-dev needs a person at a terminal" in result.stderr
    assert fake_rce.requests_to("POST", START) == []


def test_it_asks_first_and_says_what_the_run_costs(rce, fake_rce):
    fresh_player(rce, fake_rce)

    tty = rce.interactive("device", "setup-dev", "player")
    question = tty.expect(r"\[y/N\]")
    tty.answer("n")
    result = tty.finish()

    assert "$0.20/h" in question and "Dev Snapshot" in question
    assert result.returncode == 2
    assert fake_rce.requests_to("POST", START) == []


def test_steps_the_cloud_device_already_shows_done_need_no_person(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")  # linked, and Control by mobile apps is permissive
    fake_rce.dev_mode = False

    tty = rce.interactive("device", "setup-dev", "player", "--yes")
    enable_dev_mode(tty, fake_rce)
    result = tty.finish()

    assert result.returncode == 0, result.stderr
    assert "30 minutes" not in result.stderr
    assert "Control by mobile apps" not in result.stderr


def test_after_ctrl_c_it_stops_the_run_and_a_rerun_resumes_where_it_was(rce, fake_rce):
    fresh_player(rce, fake_rce)
    tty = rce.interactive("device", "setup-dev", "player", "--yes")
    link_account(tty, fake_rce)
    enable_dev_mode(tty, fake_rce)
    tty.expect(r"Control by mobile apps")
    tty.expect(r"Press Enter")
    tty.interrupt()
    interrupted = tty.finish()
    password = rce.read_config()["devices"]["player"]["dev_password"]
    combos = len([r for r in fake_rce.requests if r.path.endswith(COMBO)])

    assert interrupted.returncode == 130
    assert len(fake_rce.requests_to("POST", STOP)) == 1
    assert rce.read_config()["devices"]["player"]["setup_dev"]["done"] == [
        "account_link",
        "dev_mode",
    ]

    tty = rce.interactive("device", "setup-dev", "player", "--yes")
    allow_mobile_apps(tty, fake_rce)
    resumed = tty.finish()

    assert resumed.returncode == 0, resumed.stderr
    assert len(fake_rce.requests_to("POST", START)) == 2
    assert len([r for r in fake_rce.requests if r.path.endswith(COMBO)]) == combos
    assert "Developer Settings" not in resumed.stderr
    entry = rce.read_config()["devices"]["player"]
    assert entry["dev_password"] == password
    assert entry["dev_snapshot_id"] == fake_rce.snapshots[351][-1]["id"]
    assert len(fake_rce.requests_to("POST", STOP)) == 2


def test_a_rerun_after_it_is_done_changes_nothing_unless_restart(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    fake_rce.dev_mode = False
    tty = rce.interactive("device", "setup-dev", "player", "--yes")
    enable_dev_mode(tty, fake_rce)
    assert tty.finish().returncode == 0
    first = rce.read_config()["devices"]["player"]["dev_snapshot_id"]
    requests = len(fake_rce.requests)

    again = rce.json("device", "setup-dev", "player", "--yes")

    assert again["dev_snapshot_id"] == first and again["stopped_run"] is False
    assert len(fake_rce.requests) == requests

    restarted = rce.json("device", "setup-dev", "player", "--yes", "--restart")

    assert restarted["dev_snapshot_id"] != first
    assert restarted["stopped_run"] is True
    assert len(fake_rce.requests_to("POST", START)) == 2


def test_dev_mode_already_on_with_a_password_rce_did_not_set_is_turned_off_first(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")  # in dev mode, set up in the RCE web viewer

    tty = rce.interactive("device", "setup-dev", "player", "--yes")
    tty.expect(r"Disable installer and restart")
    tty.expect(r"Press Enter")
    fake_rce.dev_mode = False
    tty.answer()
    enable_dev_mode(tty, fake_rce)
    result = tty.finish()

    assert result.returncode == 0, result.stderr
    assert len([r for r in fake_rce.requests if r.path.endswith(COMBO)]) == 2
    password = rce.read_config()["devices"]["player"]["dev_password"]
    assert keys_typed(fake_rce) == [f"Lit_{c}" for c in password]


def progress_written(rce, done: list[str], **setup_dev) -> None:
    """The per-user config as an earlier, interrupted setup-dev left it.

    Player's table is the file's last, as `device alias` leaves it."""  # glossary-ok
    fields = "".join(f"{key} = {value}\n" for key, value in setup_dev.items())
    with rce.config.open("a") as config:
        config.write(
            'dev_password = "Pa55wordFromBefore"\n\n'
            f"[devices.player.setup_dev]\ndone = {json.dumps(done)}\n{fields}"
        )


def test_a_failed_step_stops_the_run_it_started(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    progress_written(rce, ["account_link", "dev_mode"])
    fake_rce.snapshot_limit = 2  # the base and live Snapshots fill it

    result = rce.run("device", "setup-dev", "player", "--yes")

    assert result.returncode == 4
    assert "Snapshot limit" in result.stderr
    assert "dev_snapshot_id" not in rce.read_config()["devices"]["player"]
    assert len(fake_rce.requests_to("POST", STOP)) == 1


def test_verification_failure_saves_no_snapshot_and_a_rerun_redoes_that_step(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    progress_written(rce, ["account_link", "dev_mode", "mobile_apps"])
    fake_rce.ecp_mode = "limited"  # the setting didn't stick

    result = rce.run("device", "setup-dev", "player", "--yes")

    assert result.returncode == 4
    assert '"Control by mobile apps" is limited' in result.stderr
    assert fake_rce.requests_to("POST", "/api/v1/devices/351/snapshots") == []
    assert rce.read_config()["devices"]["player"]["setup_dev"]["done"] == [
        "account_link",
        "dev_mode",
    ]
    assert len(fake_rce.requests_to("POST", STOP)) == 1


def test_a_rerun_waits_for_the_snapshot_it_asked_for_without_a_run(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    fake_rce.snapshots[351].append(snapshot_out(1001, "dev-ready"))
    progress_written(
        rce, ["account_link", "dev_mode", "mobile_apps", "verify"], snapshot_id=1001
    )

    result = rce.json("device", "setup-dev", "player", "--yes")

    assert result["dev_snapshot_id"] == 1001 and result["stopped_run"] is False
    assert fake_rce.requests_to("POST", "/api/v1/devices/351/snapshots") == []
    assert fake_rce.requests_to("POST", START) == []


def test_keep_running_leaves_the_run_going(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    progress_written(rce, ["account_link", "dev_mode"])

    result = rce.json("device", "setup-dev", "player", "--yes", "--keep-running")

    assert result["stopped_run"] is False
    assert fake_rce.requests_to("POST", STOP) == []


def test_a_run_it_did_not_start_keeps_going_with_a_warning(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.name_device("351", "player")
    progress_written(rce, ["account_link", "dev_mode"])

    result = rce.run("device", "setup-dev", "player", "--yes", "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["stopped_run"] is False
    assert fake_rce.requests_to("POST", START) == []
    assert fake_rce.requests_to("POST", STOP) == []
    assert "still running and billing" in result.stderr
    assert "rce device stop player" in result.stderr


def test_keep_running_leaves_it_going_on_failure_too(rce, fake_rce):
    fresh_player(rce, fake_rce)

    result = rce.run("device", "setup-dev", "player", "--yes", "--keep-running")

    assert result.returncode == 4
    assert fake_rce.requests_to("POST", STOP) == []
    assert "still running" in result.stderr


def test_show_password_shows_it_once_for_you_to_type(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    fake_rce.dev_mode = False

    tty = rce.interactive("device", "setup-dev", "player", "--yes", "--show-password")
    enable_dev_mode(tty, fake_rce)
    result = tty.finish()

    assert result.returncode == 0, result.stderr
    password = rce.read_config()["devices"]["player"]["dev_password"]
    assert result.stderr.count(password) == 1
    assert f"The Dev Password of player (351) is: {password}" in result.stderr
    assert password not in result.stdout
    assert keys_typed(fake_rce) == []  # you type it


def test_a_cloud_device_without_a_device_name_exits_3(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")

    result = rce.run("device", "setup-dev", "351", "--yes")

    assert result.returncode == 3
    assert "Device Name" in result.stderr


def test_setup_dev_generates_its_own_dev_password_even_with_rce_dev_password_set(rce, fake_rce):
    fresh_player(rce, fake_rce)
    rce.env["RCE_DEV_PASSWORD"] = "pipeline-SECRET"

    tty = rce.interactive("device", "setup-dev", "player", "--yes")
    link_account(tty, fake_rce)
    enable_dev_mode(tty, fake_rce)
    allow_mobile_apps(tty, fake_rce)
    result = tty.finish()

    assert result.returncode == 0, result.stderr
    password = rce.read_config()["devices"]["player"]["dev_password"]
    assert re.fullmatch(r"[A-Za-z0-9]{16,}", password)
    assert keys_typed(fake_rce) == [f"Lit_{c}" for c in password]
