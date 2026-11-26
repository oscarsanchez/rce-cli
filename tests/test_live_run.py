"""`scripts/live-run`: one Run on the agents' Cloud Device, keeping the standing OK's rules.

Run against the fake RCE; the agents' Cloud Device is `bot` (RCE id 361).
"""

import os
import signal
import subprocess
import time

from conftest import REPO, RCE
from fake_rce import ALREADY_RUNNING, Response

LIVE_RUN = REPO / "scripts" / "live-run"
START = "/api/v1/devices/361/start"
STOP = "/api/v1/devices/361/stop"
DEVICE = "/api/v1/devices/361"
REFUSED = Response(409, {"detail": "The device is locked."})


def agents_device(rce, fake_rce) -> None:
    """The agents' Cloud Device, with Dev Snapshot 1001, named in RCE_AGENT_DEVICE."""
    fake_rce.add_device(361, "Agents RCE Player", "stb")
    rce.name_device("361", "bot")
    rce.config.write_text(
        rce.config.read_text().replace("[devices.bot]\n", "[devices.bot]\ndev_snapshot_id = 1001\n")
    )
    rce.env["RCE_AGENT_DEVICE"] = "bot"
    fake_rce.requests.clear()  # naming it read the Cloud Device


def someone_running(fake_rce) -> None:
    """Another Cloud Device with a Run, which the agents' Cloud Device must wait for."""
    fake_rce.add_device(362, "Someone's RCE Player", "stb", running=True)


def short_waits(rce, wait_s: float) -> None:
    rce.env.update(LIVE_RUN_POLL_S="0.1", LIVE_RUN_WAIT_S=str(wait_s))


def live_run(rce, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(LIVE_RUN), *args],
        cwd=rce.cwd,
        env=rce.env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_without_the_agents_device_it_calls_no_rce(rce, fake_rce):
    result = live_run(rce, "ticket-03", "--", "true")

    assert result.returncode == 2
    assert "RCE_AGENT_DEVICE" in result.stderr
    assert fake_rce.requests == []


def test_a_cap_over_ten_minutes_is_refused_before_any_rce_call(rce, fake_rce):
    agents_device(rce, fake_rce)

    result = live_run(rce, "ticket-03", "--max-runtime", "601", "--", "true")

    assert result.returncode == 2
    assert "600" in result.stderr
    assert fake_rce.requests == []


def test_the_command_runs_on_a_capped_run_from_the_dev_snapshot_which_is_then_stopped(rce, fake_rce):
    agents_device(rce, fake_rce)

    result = live_run(
        rce, "ticket-03", "--max-runtime", "300", "--",
        "sh", "-c", 'echo "$RCE_DEVICE $RCE_RUN $RCE_LOCK_OWNER"',
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "bot 9000 ticket-03\n"
    [start] = fake_rce.requests_to("POST", START)
    assert start.json()["snapshot_id"] == 1001
    assert start.json()["max_runtime"] == 300
    assert len(fake_rce.requests_to("POST", STOP)) == 1
    assert rce.json("device", "list", "--running") == []


def test_firmware_is_passed_on_to_the_start(rce, fake_rce):
    agents_device(rce, fake_rce)

    result = live_run(rce, "ticket-04", "--firmware", "304", "--", "true")

    assert result.returncode == 0, result.stderr
    [start] = fake_rce.requests_to("POST", START)
    assert start.json()["firmware_version_id"] == "304"
    assert start.json()["snapshot_id"] == 1001
    assert len(fake_rce.requests_to("POST", STOP)) == 1


def test_an_empty_firmware_is_refused_before_any_rce_call(rce, fake_rce):
    agents_device(rce, fake_rce)

    result = live_run(rce, "ticket-04", "--firmware", "", "--", "true")

    assert result.returncode == 2
    assert "--firmware" in result.stderr
    assert fake_rce.requests == []


def test_a_failing_command_still_stops_the_run_and_its_status_is_passed_on(rce, fake_rce):
    agents_device(rce, fake_rce)

    result = live_run(rce, "ticket-03", "--", "sh", "-c", "exit 7")

    assert result.returncode == 7
    assert len(fake_rce.requests_to("POST", STOP)) == 1
    assert rce.json("device", "list", "--running") == []


def test_the_record_names_the_run_and_the_usage_before_and_after(rce, fake_rce):
    agents_device(rce, fake_rce)

    result = live_run(rce, "ticket-03", "--", "true")

    assert result.returncode == 0, result.stderr
    assert "Run 9000 on bot" in result.stderr
    assert " s from start to stop" in result.stderr
    assert result.stderr.count("min used") == 2  # `rce usage` before and after


def test_the_stop_spares_a_run_that_is_no_longer_its_own(rce, fake_rce):
    agents_device(rce, fake_rce)
    someone_else = f'{RCE} device stop bot --wait && {RCE} device start bot'

    result = live_run(rce, "ticket-03", "--", "sh", "-c", someone_else)

    assert result.returncode == 0, result.stderr
    assert len(fake_rce.requests_to("POST", STOP)) == 1  # the command's own stop
    [still] = rce.json("device", "list", "--running")
    assert still["run"]["id"] == 9001
    assert "still running: bot (Run 9001)" in result.stderr


def test_a_refused_start_runs_nothing_and_starts_nothing_more(rce, fake_rce):
    agents_device(rce, fake_rce)
    fake_rce.fail_next("POST", START, ALREADY_RUNNING)  # another start won the race
    ran = rce.cwd / "ran"

    result = live_run(rce, "ticket-03", "--", "touch", str(ran))

    assert result.returncode == 4
    assert not ran.exists()
    assert len(fake_rce.requests_to("POST", START)) == 1
    assert fake_rce.requests_to("POST", STOP) == []


def test_it_waits_while_something_runs_then_gives_up_starting_nothing(rce, fake_rce):
    agents_device(rce, fake_rce)
    someone_running(fake_rce)
    short_waits(rce, wait_s=2)

    result = live_run(rce, "ticket-03", "--", "true")

    assert result.returncode == 5  # timed out, as `rce` says it; a refused start is 4
    assert len(fake_rce.requests_to("GET", "/api/v1/devices")) >= 2  # it looked again
    assert "Someone's RCE Player (Run 9000)" in result.stderr
    assert "Started nothing" in result.stderr
    assert fake_rce.requests_to("POST", START) == []


def test_it_starts_once_the_other_run_ends(rce, fake_rce):
    agents_device(rce, fake_rce)
    someone_running(fake_rce)
    fake_rce.free_after("GET", "/api/v1/devices", 362, times=2)
    short_waits(rce, wait_s=60)

    result = live_run(rce, "ticket-03", "--", "true")

    assert result.returncode == 0, result.stderr
    assert "waiting" in result.stderr
    assert len(fake_rce.requests_to("POST", START)) == 1


def live_run_in_background(rce, *command: str) -> subprocess.Popen:
    return subprocess.Popen(
        [str(LIVE_RUN), "ticket-03", "--", *command],
        cwd=rce.cwd,
        env=rce.env,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,  # its own process group, as a terminal's Ctrl-C reaches
    )


def wait_for(condition, what: str) -> None:
    deadline = time.monotonic() + 30
    while not condition():
        assert time.monotonic() < deadline, what
        time.sleep(0.05)


def live_run_until_told(rce):
    """live-run in the background with a command that has started and ends once `go` exists:
    the test changes the fake RCE before the stop."""
    started, go = rce.cwd / "started", rce.cwd / "go"
    command = f"touch {started}; while [ ! -e {go} ]; do sleep 0.05; done"
    live = live_run_in_background(rce, "sh", "-c", command)
    wait_for(started.exists, "the command never ran")
    return live, go


def test_ctrl_c_during_the_command_still_stops_the_run(rce, fake_rce):
    agents_device(rce, fake_rce)
    started = rce.cwd / "started"
    live = live_run_in_background(rce, "sh", "-c", f"touch {started}; sleep 60")
    wait_for(started.exists, "the command never ran")

    os.killpg(live.pid, signal.SIGINT)
    _, stderr = live.communicate(timeout=60)

    assert live.returncode == 130, stderr
    assert len(fake_rce.requests_to("POST", STOP)) == 1
    assert rce.json("device", "list", "--running") == []


def test_sigterm_is_passed_on_to_the_command_and_the_run_still_stopped(rce, fake_rce):
    agents_device(rce, fake_rce)
    started, got = rce.cwd / "started", rce.cwd / "got-sigterm"
    command = f"trap 'touch {got}; kill $!; exit 0' TERM; touch {started}; sleep 60 & wait"
    live = live_run_in_background(rce, "sh", "-c", command)
    wait_for(started.exists, "the command never ran")

    live.terminate()  # to live-run alone, not its process group
    _, stderr = live.communicate(timeout=60)

    assert got.exists(), stderr
    assert live.returncode == 130, stderr  # interrupted, though the command exited 0
    assert len(fake_rce.requests_to("POST", STOP)) == 1
    assert rce.json("device", "list", "--running") == []


def test_a_signal_during_the_start_stops_the_run_and_runs_nothing(rce, fake_rce):
    agents_device(rce, fake_rce)
    fake_rce.start_delay = 2  # RCE has made the Run but not answered yet
    ran = rce.cwd / "ran"
    live = live_run_in_background(rce, "touch", str(ran))
    wait_for(lambda: fake_rce.requests_to("POST", START), "it never started")

    live.terminate()
    _, stderr = live.communicate(timeout=60)

    assert live.returncode == 130, stderr
    assert not ran.exists()
    assert len(fake_rce.requests_to("POST", STOP)) == 1
    assert rce.json("device", "list", "--running") == []


def test_a_signal_while_waiting_its_turn_starts_nothing(rce, fake_rce):
    agents_device(rce, fake_rce)
    someone_running(fake_rce)
    rce.env.update(LIVE_RUN_POLL_S="600", LIVE_RUN_WAIT_S="600")  # it would sleep 10 min
    live = live_run_in_background(rce, "true")
    wait_for(lambda: fake_rce.requests_to("GET", "/api/v1/devices"), "it never looked")

    live.terminate()
    _, stderr = live.communicate(timeout=30)

    assert live.returncode == 130, stderr
    assert fake_rce.requests_to("POST", START) == []


def test_a_stop_that_leaves_its_run_running_is_tried_again(rce, fake_rce):
    agents_device(rce, fake_rce)
    fake_rce.fail_next("POST", STOP, REFUSED)  # `rce` exits 4, as for a Run already ended

    result = live_run(rce, "ticket-03", "--", "true")

    assert result.returncode == 0, result.stderr
    assert len(fake_rce.requests_to("POST", STOP)) == 2
    assert rce.json("device", "list", "--running") == []


def test_a_stop_that_twice_leaves_its_run_running_failed(rce, fake_rce):
    agents_device(rce, fake_rce)
    fake_rce.fail_next("POST", STOP, REFUSED, times=2)

    result = live_run(rce, "ticket-03", "--", "true")

    assert result.returncode == 1
    assert "the stop failed: Run 9000 may still bill" in result.stderr
    assert len(fake_rce.requests_to("POST", STOP)) == 2


def test_a_stop_whose_run_cannot_be_read_failed(rce, fake_rce):
    agents_device(rce, fake_rce)
    live, go = live_run_until_told(rce)
    fake_rce.fail_next("GET", DEVICE, REFUSED, times=100)  # from the stop on, the Run can't be read
    go.touch()

    _, stderr = live.communicate(timeout=60)

    assert live.returncode == 1, stderr
    assert "the stop failed: Run 9000 may still bill" in stderr


def test_a_failed_look_at_other_runs_after_the_stop_still_prints_the_record(rce, fake_rce):
    agents_device(rce, fake_rce)
    live, go = live_run_until_told(rce)
    fake_rce.fail_next("GET", "/api/v1/devices", REFUSED, times=100)  # `rce device list` fails
    go.touch()

    _, stderr = live.communicate(timeout=60)

    assert live.returncode == 0, stderr  # the command's: the list is only informational
    assert "record: Run 9000 on bot" in stderr
    assert "usage after:" in stderr
    assert rce.json("device", "status", "bot")["run"] is None
