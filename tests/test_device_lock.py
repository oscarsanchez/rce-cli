"""The per-Cloud-Device lock that start and stop take, so two callers never race."""

import json
import signal
import subprocess
import time

START = "/api/v1/devices/351/start"
STOP = "/api/v1/devices/351/stop"


def player(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")


def wait_for(condition, timeout=20.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting"
        time.sleep(0.05)


def start_holding_the_lock(rce, fake_rce, *flags):
    """A start that holds the lock while it waits for a slow start."""
    fake_rce.boot_delay = 60
    owner = rce.spawn("device", "start", "player", *flags, RCE_LOCK_OWNER="agent-04")
    wait_for(lambda: fake_rce.requests_to("POST", START))
    return owner


def test_a_second_start_on_a_locked_device_fails_fast_naming_the_owner(rce, fake_rce):
    player(rce, fake_rce)
    owner = start_holding_the_lock(rce, fake_rce, "--timeout", "3")

    result = rce.run("device", "start", "player")
    owner.wait(timeout=30)

    assert result.returncode == 4
    assert "player (351) is locked" in result.stderr
    assert "agent-04" in result.stderr
    assert "rce device start player --timeout 3" in result.stderr
    assert "pid " in result.stderr
    assert "--wait-lock" in result.stderr
    assert len(fake_rce.requests_to("POST", START)) == 1


def test_the_lock_records_its_owner(rce, fake_rce):
    player(rce, fake_rce)
    owner = start_holding_the_lock(rce, fake_rce, "--timeout", "3")

    lock = json.loads((rce.locks / "351.lock").read_text())
    owner.wait(timeout=30)

    assert lock["owner"] == "agent-04"
    assert lock["command"] == "rce device start player --timeout 3"
    assert isinstance(lock["pid"], int)


def test_wait_lock_waits_for_the_owner_then_starts(rce, fake_rce):
    player(rce, fake_rce)
    owner = start_holding_the_lock(rce, fake_rce, "--timeout", "2")
    fake_rce.boot_delay = 0  # the owner's Run never boots; the next one boots at once

    result = rce.run("device", "start", "player", "--wait-lock")
    owner.wait(timeout=30)

    assert owner.returncode == 5  # the owner timed out and stopped its Run
    assert result.returncode == 0, result.stderr
    assert "agent-04" in result.stderr  # it said whom it was waiting for
    assert len(fake_rce.requests_to("POST", START)) == 2


def test_stop_takes_the_lock_too(rce, fake_rce):
    player(rce, fake_rce)
    owner = start_holding_the_lock(rce, fake_rce, "--timeout", "3")

    result = rce.run("device", "stop", "player")
    owner.wait(timeout=30)

    assert result.returncode == 4
    assert "agent-04" in result.stderr
    assert len(fake_rce.requests_to("POST", STOP)) == 1  # only the owner's own stop


def test_interrupting_a_start_stops_its_run_and_frees_the_lock(rce, fake_rce):
    player(rce, fake_rce)
    owner = start_holding_the_lock(rce, fake_rce)

    owner.send_signal(signal.SIGINT)
    _, stderr = owner.communicate(timeout=30)

    assert owner.returncode == 130
    assert "Traceback" not in stderr
    assert "stopped the Run" in stderr
    assert fake_rce.requests_to("POST", STOP)
    assert "locked" not in rce.run("device", "stop", "player").stderr


def test_a_stale_lock_whose_owner_died_is_reclaimed(rce, fake_rce):
    player(rce, fake_rce)
    dead = subprocess.Popen(["true"])
    dead.wait()
    rce.locks.mkdir(parents=True)
    (rce.locks / "351.lock").write_text(
        json.dumps({"pid": dead.pid, "command": "rce device start player", "owner": "crashed"})
    )

    result = rce.run("device", "start", "player", "--json")

    assert result.returncode == 0, result.stderr
    assert fake_rce.requests_to("POST", START)


def test_the_lock_is_per_cloud_device(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.add_device(352, "Personal RCE TV", "tv")
    owner = start_holding_the_lock(rce, fake_rce, "--timeout", "3")

    result = rce.run("device", "stop", "352")
    owner.wait(timeout=30)

    assert "locked" not in result.stderr


def test_stop_of_a_run_reads_the_device_only_once_it_holds_the_lock(rce, fake_rce):
    """The owner's Run 9000 ends while `stop --run 9000 --wait-lock` waits, so it stops nothing."""
    player(rce, fake_rce)
    owner = start_holding_the_lock(rce, fake_rce, "--timeout", "2")
    fake_rce.stop_delay = 0  # the owner's stop ends its Run at once

    result = rce.run("device", "stop", "player", "--run", "9000", "--wait-lock")
    owner.wait(timeout=30)

    assert owner.returncode == 5  # the owner timed out and stopped its Run
    assert result.returncode == 4
    assert "Run 9000 already ended; nothing stopped" in result.stderr
    assert len(fake_rce.requests_to("POST", STOP)) == 1  # only the owner's own stop
