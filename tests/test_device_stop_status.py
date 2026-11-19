"""`rce device stop` and `rce device status`: end a Run, and check one."""

from datetime import datetime, timedelta, timezone

import pytest

from conftest import TOKEN
from fake_rce import WEBRTC_SECRETS, Response, iso

STOP = "/api/v1/devices/351/stop"


def running_player(rce, fake_rce, minutes_ago: float = 0) -> dict:
    device = fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    started = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    device["running_device"]["created_at"] = iso(started)
    rce.name_device("351", "player")
    return device


def test_stop_ends_the_run(rce, fake_rce):
    running_player(rce, fake_rce)

    result = rce.run("device", "stop", "player")

    assert result.returncode == 0, result.stderr
    assert len(fake_rce.requests_to("POST", STOP)) == 1
    assert "Stopped player (351)" in result.stdout


def test_stop_reports_what_the_run_cost(rce, fake_rce):
    running_player(rce, fake_rce, minutes_ago=30)

    stopped = rce.json("device", "stop", "player")

    assert stopped["run"]["id"] == 9000
    assert 1800 <= stopped["elapsed_s"] < 1830
    assert stopped["elapsed_cost_usd"] == pytest.approx(0.10, abs=0.001)


def test_stop_with_wait_waits_for_shutdown(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.stop_delay = 0.5

    stopped = rce.json("device", "stop", "player", "--wait")

    assert stopped["status"] == "shutdown"
    assert fake_rce.devices[351]["status"] == "shutdown"


def test_stop_with_wait_times_out_with_exit_5(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.stop_delay = 60

    result = rce.run("device", "stop", "player", "--wait", "--timeout", "1")

    assert result.returncode == 5
    assert "shut down" in result.stderr


def test_stopping_a_device_that_is_not_running_says_so(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    result = rce.run("device", "stop", "player")

    assert result.returncode == 4
    assert "player (351) is not running" in result.stderr
    assert "rce device start player" in result.stderr
    assert not fake_rce.requests_to("POST", STOP)


def test_a_stop_answered_503_fails_once(rce, fake_rce):
    """Only a start takes the careful path on a 503; a stop is neither retried nor checked."""
    running_player(rce, fake_rce)
    fake_rce.fail_next("POST", STOP, Response(503, {"detail": "Service Unavailable"}))

    result = rce.run("device", "stop", "player")

    assert result.returncode == 1
    assert "RCE answered 503: Service Unavailable" in result.stderr
    assert len(fake_rce.requests_to("POST", STOP)) == 1


def test_stop_of_an_unknown_name_is_not_found(rce, fake_rce):
    assert rce.run("device", "stop", "nope").returncode == 3


def test_status_of_a_run_shows_state_start_cap_elapsed_time_and_cost(rce, fake_rce):
    device = running_player(rce, fake_rce, minutes_ago=10)

    status = rce.json("device", "status", "player")

    run = device["running_device"]
    assert status["status"] == "running"
    assert status["run"]["created_at"] == run["created_at"]
    assert status["run"]["max_runtime"] == 3600
    assert 600 <= status["elapsed_s"] < 630
    assert status["elapsed_cost_usd"] == pytest.approx(0.0333, abs=0.001)
    started = datetime.fromisoformat(run["created_at"]).replace(microsecond=0)
    assert datetime.fromisoformat(status["auto_stop_at"]) == started + timedelta(hours=1)


def test_status_for_people_shows_the_run_without_secrets(rce, fake_rce):
    running_player(rce, fake_rce, minutes_ago=10)

    result = rce.run("device", "status", "player")

    assert result.returncode == 0, result.stderr
    for line in ("Status:", "Run started:", "Cap:", "Elapsed:"):
        assert line in result.stdout
    assert "60 min" in result.stdout
    assert "10 min" in result.stdout
    assert "$0.03" in result.stdout
    for secret in (*WEBRTC_SECRETS, TOKEN):
        assert secret not in result.stdout + result.stderr


def test_status_of_a_device_without_a_run(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    status = rce.json("device", "status", "player")

    assert status["status"] == "shutdown"
    assert status["run"] is None
    assert status["elapsed_s"] is None
    assert "shutdown" in rce.run("device", "status", "player").stdout


def test_status_of_a_starting_device(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    fake_rce.boot_delay = 60
    rce.json("device", "start", "player", "--no-wait")

    status = rce.json("device", "status", "player")

    assert status["status"] == "pending"
    assert status["elapsed_s"] is not None


def test_stop_with_the_current_runs_id_stops_it(rce, fake_rce):
    running_player(rce, fake_rce, minutes_ago=30)

    stopped = rce.json("device", "stop", "player", "--run", "9000")

    assert stopped["run"]["id"] == 9000
    assert 1800 <= stopped["elapsed_s"] < 1830
    assert len(fake_rce.requests_to("POST", STOP)) == 1


def test_stop_with_another_runs_id_stops_nothing(rce, fake_rce):
    """Job A's Run ended at its cap and job B started Run 9000: A's stop leaves it alone."""
    running_player(rce, fake_rce)

    result = rce.run("device", "stop", "player", "--run", "8999")

    assert result.returncode == 4
    assert "Run 8999 already ended; nothing stopped" in result.stderr
    assert not fake_rce.requests_to("POST", STOP)
    assert fake_rce.devices[351]["status"] == "running"


def test_stop_with_a_run_id_when_no_run_is_on_the_device_stops_nothing(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    result = rce.run("device", "stop", "player", "--run", "9000")

    assert result.returncode == 4
    assert "Run 9000 already ended; nothing stopped" in result.stderr
    assert not fake_rce.requests_to("POST", STOP)


def test_stop_with_a_run_id_that_is_not_a_number_is_a_usage_error(rce, fake_rce):
    running_player(rce, fake_rce)

    result = rce.run("device", "stop", "player", "--run", "abc")

    assert result.returncode == 2
    assert not fake_rce.requests_to("POST", STOP)


def test_stop_with_the_current_runs_id_waits_and_reports_as_a_plain_stop(rce, fake_rce):
    running_player(rce, fake_rce, minutes_ago=30)
    fake_rce.stop_delay = 0.5

    result = rce.run("device", "stop", "player", "--run", "9000", "--wait")

    assert result.returncode == 0, result.stderr
    assert "Stopped player (351): Run 9000 ran 30 min" in result.stdout
    assert "It is shut down." in result.stdout
    assert fake_rce.devices[351]["status"] == "shutdown"
