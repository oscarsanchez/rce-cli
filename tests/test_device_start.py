"""`rce device start`: a Run with safe defaults that comes back ready to use."""

import time
from datetime import datetime, timedelta

import pytest
from conftest import TOKEN
from fake_rce import (
    ALREADY_RUNNING,
    NO_ANSWER,
    OVER_CAP,
    SNAPSHOT_NOT_READY,
    Response,
    TRIAL_EXHAUSTED,
    TRIAL_OVER_CAP,
    TRIAL_RUN_LIMIT,
    WEBRTC_SECRETS,
)

DEVICE = "/api/v1/devices/351"
START = "/api/v1/devices/351/start"
STOP = "/api/v1/devices/351/stop"


def player(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")


def record_dev_snapshot(rce, name: str, snapshot_id: int) -> None:
    """Record a Dev Snapshot in the per-user config, as `snapshot use-as-dev` does."""
    rce.config.write_text(
        rce.config.read_text().replace(f"[devices.{name}]\n", f"[devices.{name}]\ndev_snapshot_id = {snapshot_id}\n")
    )


def test_start_defaults_to_an_hour_the_latest_firmware_and_the_live_state(rce, fake_rce):
    player(rce, fake_rce)

    result = rce.run("device", "start", "player", "--json")

    assert result.returncode == 0, result.stderr
    [start] = fake_rce.requests_to("POST", START)
    assert start.json() == {"snapshot_id": 998, "firmware_version_id": "395", "max_runtime": 3600}


def test_start_without_a_dev_snapshot_warns_that_it_uses_the_live_state(rce, fake_rce):
    player(rce, fake_rce)

    result = rce.run("device", "start", "player")

    assert result.returncode == 0, result.stderr
    assert "no Dev Snapshot" in result.stderr
    assert "998" in result.stderr


def test_start_uses_the_dev_snapshot_when_one_is_recorded(rce, fake_rce):
    player(rce, fake_rce)
    record_dev_snapshot(rce, "player", 1001)

    result = rce.run("device", "start", "player")

    assert result.returncode == 0, result.stderr
    assert "Dev Snapshot" not in result.stderr
    [start] = fake_rce.requests_to("POST", START)
    assert start.json()["snapshot_id"] == 1001


def test_snapshot_firmware_and_cap_can_be_overridden(rce, fake_rce):
    player(rce, fake_rce)
    record_dev_snapshot(rce, "player", 1001)

    result = rce.run(
        "device", "start", "player", "--snapshot", "997", "--firmware", "304", "--max-runtime", "600"
    )

    assert result.returncode == 0, result.stderr
    [start] = fake_rce.requests_to("POST", START)
    assert start.json() == {"snapshot_id": 997, "firmware_version_id": "304", "max_runtime": 600}


def test_start_by_raw_id_works_too(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")

    assert rce.run("device", "start", "351").returncode == 0
    assert fake_rce.requests_to("POST", START)


def test_start_waits_until_running_and_input_ready_at_the_runs_own_address(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.boot_delay = 0.5
    fake_rce.input_delay = 0.5

    run = rce.json("device", "start", "player")

    assert run["status"] == "running"
    uuid = fake_rce.devices[351]["running_device"]["instance_uuid"]
    ready = fake_rce.requests_to("GET", f"/instance/{uuid}/api/v0/input/ready")  # glossary-ok
    assert ready and all(r.headers["authorization"] == f"Bearer {TOKEN}" for r in ready)


def test_a_run_address_without_a_scheme_takes_the_core_apis(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.address_scheme = ""  # as RCE's spec documents instance_api_url

    run = rce.json("device", "start", "player")

    assert run["status"] == "running"


def test_start_reports_the_hourly_cost_and_auto_stop_time(rce, fake_rce):
    player(rce, fake_rce)

    run = rce.json("device", "start", "player")

    assert run["hourly_cost_usd"] == 0.2
    created = datetime.fromisoformat(run["run"]["created_at"]).replace(microsecond=0)
    assert datetime.fromisoformat(run["auto_stop_at"]) == created + timedelta(seconds=3600)


def test_start_prints_cost_and_auto_stop_for_people_without_secrets(rce, fake_rce):
    player(rce, fake_rce)

    result = rce.run("device", "start", "player")

    assert result.returncode == 0, result.stderr
    assert "player (351) is running" in result.stdout
    assert "$0.20/h" in result.stdout
    assert "auto-stops" in result.stdout
    for secret in (*WEBRTC_SECRETS, TOKEN):
        assert secret not in result.stdout + result.stderr


def test_start_json_never_includes_run_credentials(rce, fake_rce):
    player(rce, fake_rce)

    result = rce.run("device", "start", "player", "--json")

    for secret in (*WEBRTC_SECRETS, TOKEN):
        assert secret not in result.stdout + result.stderr


def test_no_wait_returns_once_rce_accepts_the_start(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.boot_delay = 60

    run = rce.json("device", "start", "player", "--no-wait")

    assert run["status"] == "pending"
    assert not [r for r in fake_rce.requests if r.path.endswith("/input/ready")]


def test_a_start_that_is_not_ready_in_time_exits_5_and_stops_the_run(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.boot_delay = 60

    result = rce.run("device", "start", "player", "--timeout", "1")

    assert result.returncode == 5
    assert "not ready" in result.stderr
    assert fake_rce.requests_to("POST", STOP)
    assert "stopped" in result.stderr


def test_starting_a_device_that_is_already_running_is_refused(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.name_device("351", "player")

    result = rce.run("device", "start", "player")

    assert result.returncode == 4
    assert "already running" in result.stderr
    assert not fake_rce.requests_to("POST", STOP)


def test_the_trial_run_limit_names_the_running_cloud_device_and_stops_nothing(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.add_device(352, "Personal RCE TV", "tv", running=True)
    rce.name_device("352", "tv")

    result = rce.run("device", "start", "player")

    assert result.returncode == 4
    assert "tv (352)" in result.stderr
    assert "one Cloud Device at a time" in result.stderr
    assert len(fake_rce.requests_to("POST", START)) == 1  # a 429 on a write is not retried
    assert not [r for r in fake_rce.requests if r.path.endswith("/stop")]


def test_the_trial_run_limit_names_a_running_device_without_a_device_name(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.add_device(352, "Personal RCE TV", "tv", running=True)

    result = rce.run("device", "start", "player")

    assert result.returncode == 4
    assert "Personal RCE TV (352)" in result.stderr


def refusal(rce, fake_rce, response, *flags):
    player(rce, fake_rce)
    fake_rce.fail_next("POST", START, response)
    return rce.run("device", "start", "player", *flags)


def test_an_exhausted_trial_is_explained(rce, fake_rce):
    result = refusal(rce, fake_rce, TRIAL_EXHAUSTED)

    assert result.returncode == 4
    assert "free trial is used up" in result.stderr


def test_a_snapshot_that_is_not_ready_is_explained(rce, fake_rce):
    result = refusal(rce, fake_rce, SNAPSHOT_NOT_READY, "--snapshot", "1001")

    assert result.returncode == 4
    assert "Snapshot 1001 is not ready" in result.stderr


def test_a_cap_over_the_trial_time_left_is_explained(rce, fake_rce):
    result = refusal(rce, fake_rce, TRIAL_OVER_CAP, "--max-runtime", "99999")

    assert result.returncode == 4
    assert "more than the trial time you have left" in result.stderr


def test_a_cap_over_the_organisations_maximum_is_explained(rce, fake_rce):
    result = refusal(rce, fake_rce, OVER_CAP, "--max-runtime", "999999")

    assert result.returncode == 4
    assert (
        "--max-runtime 999999 s is more than your organisation's maximum of 172800 s (48 h)"
        in result.stderr
    )


def test_another_bad_request_within_the_cap_keeps_rces_reason(rce, fake_rce):
    result = refusal(rce, fake_rce, Response(400, {"detail": "Unknown firmware version."}))

    assert result.returncode == 4
    assert "Unknown firmware version." in result.stderr
    assert "organisation's maximum of" not in result.stderr


def wait_for_request(fake_rce, method, path, count=1):
    """Until the fake has received `count` requests to METHOD path."""
    deadline = time.monotonic() + 30
    while len(fake_rce.requests_to(method, path)) < count and time.monotonic() < deadline:
        time.sleep(0.05)


def interrupt_once_rce_has_the_start(rce, fake_rce, *flags):
    """Ctrl-C `device start` while RCE holds its answer to the start it accepted."""
    player(rce, fake_rce)
    fake_rce.start_delay = 30
    tty = rce.interactive("device", "start", "player", *flags)
    wait_for_request(fake_rce, "POST", START)
    tty.interrupt()
    return tty.finish()


def test_ctrl_c_while_rce_has_not_answered_the_start_stops_the_run(rce, fake_rce):
    result = interrupt_once_rce_has_the_start(rce, fake_rce)

    assert result.returncode == 130
    assert "stopped the Run of player (351) so it doesn't keep billing" in result.stderr
    assert fake_rce.requests_to("POST", STOP)


def test_with_no_wait_ctrl_c_before_rce_answers_stops_the_run_too(rce, fake_rce):
    result = interrupt_once_rce_has_the_start(rce, fake_rce, "--no-wait")

    assert result.returncode == 130
    assert "stopped the Run of player (351)" in result.stderr
    assert fake_rce.requests_to("POST", STOP)


def test_a_start_that_loses_its_answer_after_rce_accepted_it_stops_the_run(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.start_dropped = True

    result = rce.run("device", "start", "player")

    assert result.returncode == 1
    assert "cannot reach RCE" in result.stderr
    assert "RCE had started a Run anyway, and rce stopped it" in result.stderr
    assert "refused" not in result.stderr
    assert fake_rce.requests_to("POST", STOP)


def test_a_start_that_gets_no_answer_and_no_run_says_the_start_didnt_happen(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.fail_next("POST", START, NO_ANSWER)

    result = rce.run("device", "start", "player")

    assert result.returncode == 1
    assert "player (351) has no Run: the start didn't happen" in result.stderr
    assert "refused" not in result.stderr
    assert not fake_rce.requests_to("POST", STOP)


@pytest.mark.parametrize(
    "response", [OVER_CAP, TRIAL_EXHAUSTED, SNAPSHOT_NOT_READY, ALREADY_RUNNING, TRIAL_RUN_LIMIT]
)
def test_rces_own_refusals_stop_nothing(rce, fake_rce, response):
    result = refusal(rce, fake_rce, response, "--snapshot", "1001")

    assert result.returncode == 4
    assert not fake_rce.requests_to("POST", STOP)
    assert "warning: stopped" not in result.stderr


def test_ctrl_c_before_rce_got_the_start_says_it_didnt_happen_when_the_stop_fails(rce, fake_rce):
    """No Run to stop, so the stop fails: that is no Run billing."""
    player(rce, fake_rce)
    fake_rce.fail_next("POST", START, Response(503, "upstream connect error", delay=30))
    fake_rce.fail_next("POST", STOP, Response(409, {"detail": "The device is not running."}))
    tty = rce.interactive("device", "start", "player")
    wait_for_request(fake_rce, "POST", START)
    tty.interrupt()
    result = tty.finish()

    assert result.returncode == 130
    assert "player (351) has no Run: the start didn't happen" in result.stderr
    assert "is billing" not in result.stderr
    assert fake_rce.requests_to("POST", STOP)


def test_a_start_with_no_answer_that_cannot_check_for_a_run_stops_any_run(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.start_dropped, fake_rce.start_delay = True, 1
    tty = rce.interactive("device", "start", "player")
    wait_for_request(fake_rce, "POST", START)
    fake_rce.fail_next("GET", DEVICE, Response(500, {"detail": "Internal Server Error"}))
    result = tty.finish()

    assert result.returncode == 1
    assert "cannot reach RCE" in result.stderr
    assert "rce could not check whether RCE started a Run" in result.stderr
    assert "stopped the Run of player (351)" in result.stderr
    assert fake_rce.requests_to("POST", STOP)


def test_ctrl_c_while_checking_for_a_run_after_a_start_with_no_answer_stops_the_run(
    rce, fake_rce
):
    player(rce, fake_rce)
    fake_rce.start_dropped, fake_rce.start_delay = True, 1
    tty = rce.interactive("device", "start", "player")
    wait_for_request(fake_rce, "POST", START)
    looked = len(fake_rce.requests_to("GET", DEVICE))
    fake_rce.fail_next("GET", DEVICE, Response(500, "held", delay=30))
    wait_for_request(fake_rce, "GET", DEVICE, looked + 1)
    tty.interrupt()
    result = tty.finish()

    assert result.returncode == 130
    assert "stopped the Run of player (351)" in result.stderr
    assert fake_rce.requests_to("POST", STOP)


def test_ctrl_c_while_explaining_rces_refusal_still_ends_with_the_stop(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.fail_next("POST", START, TRIAL_RUN_LIMIT)
    fake_rce.fail_next("GET", "/api/v1/devices", Response(500, "held", delay=30))
    tty = rce.interactive("device", "start", "player")
    wait_for_request(fake_rce, "GET", "/api/v1/devices")
    tty.interrupt()
    result = tty.finish()

    assert result.returncode == 130
    assert fake_rce.requests_to("POST", STOP)
    assert "is billing" not in result.stderr
