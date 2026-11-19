"""`rce device start --pool`: claim a Free Cloud Device of the Pool by starting it."""

import fcntl
import json
import time

import pytest
from fake_rce import (
    ALREADY_RUNNING,
    NO_ANSWER,
    OVER_CAP,
    SNAPSHOT_NOT_READY,
    TRIAL_EXHAUSTED,
    TRIAL_RUN_LIMIT,
    WEBRTC_SECRETS,
    Response,
)
from test_device_start import wait_for_request

DEVICES = "/api/v1/devices"


def start_path(id: int) -> str:
    return f"/api/v1/devices/{id}/start"


def pool(rce, fake_rce, members: dict[int, int], running: tuple[int, ...] = ()) -> None:
    """A Pool on a subscription (many Runs at once): each member a Cloud Device with its
    Dev Snapshot, and RCE_POOL set as a pipeline would."""
    fake_rce.one_run_at_a_time = False
    for id, snapshot in members.items():
        fake_rce.add_device(id, f"pool-{id}", "stb", running=id in running)
        fake_rce.add_snapshot(id, snapshot)
    rce.env["RCE_POOL"] = json.dumps({str(id): snapshot for id, snapshot in members.items()})


def starts(fake_rce) -> dict[int, list[dict]]:
    """The start requests the fake received, by Cloud Device."""
    sent: dict[int, list[dict]] = {}
    for request in fake_rce.requests:
        if request.method == "POST" and request.path.endswith("/start"):
            sent.setdefault(int(request.path.split("/")[-2]), []).append(request.json())
    return sent


def test_pool_claims_the_free_member_from_its_own_dev_snapshot(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002}, running=(375,))

    result = rce.run("device", "start", "--pool", "--max-runtime", "900")

    assert result.returncode == 0, result.stderr
    assert starts(fake_rce) == {376: [{"snapshot_id": 2002, "firmware_version_id": "395", "max_runtime": 900}]}
    run_id = fake_rce.devices[376]["running_device"]["id"]
    assert f"Claimed Cloud Device 376 (Run {run_id})" in result.stdout
    assert f"Cloud Device 376 is running: Run {run_id}, $0.20/h, auto-stops around" in result.stdout
    for secret in WEBRTC_SECRETS:
        assert secret not in result.stdout + result.stderr


def test_pool_json_is_device_starts_json_for_the_claimed_member(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002, 377: 1063}, running=(375, 377))

    claimed = rce.json("device", "start", "--pool")

    assert claimed["id"] == 376
    assert claimed["run"]["id"] == fake_rce.devices[376]["running_device"]["id"]
    assert claimed["status"] == "running"
    assert set(claimed) == {
        "id", "device_name", "name", "type", "status", "run",
        "hourly_cost_usd", "auto_stop_at", "elapsed_s", "elapsed_cost_usd",
    }
    assert len(fake_rce.requests_to("GET", DEVICES)) == 1


def test_no_free_member_exits_4_and_starts_nothing(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002}, running=(375, 376))

    result = rce.run("device", "start", "--pool")

    assert result.returncode == 4
    assert "no Free Cloud Device in the Pool (2 members, none free)" in result.stderr
    assert "waiting" not in result.stderr
    assert len(fake_rce.requests_to("GET", DEVICES)) == 1
    assert result.stdout == ""
    assert starts(fake_rce) == {}


def assert_claimed_after_skips(result, fake_rce, claimed: int, skipped: set[int]) -> None:
    """`claimed` got the one accepted start; each member was tried at most once, and no
    member but these was tried; nothing was stopped."""
    assert result.returncode == 0, result.stderr
    sent = starts(fake_rce)
    assert claimed in sent and set(sent) <= skipped | {claimed}
    assert all(len(tries) == 1 for tries in sent.values())
    assert fake_rce.devices[claimed]["status"] == "running"
    assert not [r for r in fake_rce.requests if r.path.endswith("/stop")]
    assert f"Claimed Cloud Device {claimed} " in result.stdout


def test_a_member_rce_says_is_already_running_is_skipped(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002, 377: 1063, 378: 1064}, running=(378,))
    for id in (375, 376):
        fake_rce.fail_next("POST", start_path(id), ALREADY_RUNNING)

    result = rce.run("device", "start", "--pool")

    assert_claimed_after_skips(result, fake_rce, 377, {375, 376})


def assert_all_skipped(result, fake_rce, tried: set[int], members: int) -> None:
    """No Claim: each member in `tried` got exactly one start, no other member any, and
    nothing was stopped."""
    assert result.returncode == 4, result.stderr
    assert f"no Free Cloud Device in the Pool ({members} members, none free)" in result.stderr
    assert result.stdout == ""
    assert {id: len(tries) for id, tries in starts(fake_rce).items()} == {id: 1 for id in tried}
    assert not [r for r in fake_rce.requests if r.path.endswith("/stop")]


def test_every_member_rce_says_is_already_running_is_tried_once_then_none_is_free(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002, 377: 1063})
    for id in (375, 376, 377):
        fake_rce.fail_next("POST", start_path(id), ALREADY_RUNNING)

    result = rce.run("device", "start", "--pool")

    assert_all_skipped(result, fake_rce, {375, 376, 377}, 3)


def test_members_taken_between_the_look_and_the_start_are_skipped(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002})
    for id in (375, 376):  # other jobs claim them just after our look
        fake_rce.take_after("GET", DEVICES, id)

    result = rce.run("device", "start", "--pool")

    assert_all_skipped(result, fake_rce, set(), 2)


def test_a_member_taken_just_before_its_start_is_skipped(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002}, running=(376,))
    fake_rce.take_after("GET", "/api/v1/devices/375", 375)  # between our read and our start

    result = rce.run("device", "start", "--pool")

    assert_all_skipped(result, fake_rce, {375}, 2)


def test_members_whose_snapshot_is_not_ready_are_skipped_with_a_warning_naming_each(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002})
    for id in (375, 376):
        fake_rce.fail_next("POST", start_path(id), SNAPSHOT_NOT_READY)

    result = rce.run("device", "start", "--pool")

    assert_all_skipped(result, fake_rce, {375, 376}, 2)
    assert "Cloud Device 375: its Dev Snapshot 2001 is not ready" in result.stderr
    assert "Cloud Device 376: its Dev Snapshot 2002 is not ready" in result.stderr


def test_a_member_whose_device_lock_another_rce_holds_is_skipped(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002}, running=(376,))
    rce.locks.mkdir(parents=True)
    with open(rce.locks / "375.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)  # another local rce starting or stopping it
        result = rce.run("device", "start", "--pool")

    assert_all_skipped(result, fake_rce, set(), 2)
    assert not fake_rce.requests_to("GET", "/api/v1/devices/375")


def looked_after_its_start(fake_rce, id: int) -> bool:
    """Whether rce read the Cloud Device after sending it a start."""
    paths = [(r.method, r.path) for r in fake_rce.requests]
    sent = paths.index(("POST", start_path(id)))
    return ("GET", f"/api/v1/devices/{id}") in paths[sent:]


@pytest.mark.parametrize("status", [502, 503, 504])
@pytest.mark.parametrize("run_made", [False, True])
def test_a_start_answered_a_gateway_error_skips_the_member_with_a_warning_and_stops_nothing(
    rce, fake_rce, status, run_made
):
    """A Run found on the member may be another job's Claim, so rce neither looks nor stops."""
    pool(rce, fake_rce, {375: 2001, 376: 2002})
    if run_made:
        fake_rce.start_status = status
    else:
        for id in (375, 376):
            fake_rce.fail_next("POST", start_path(id), Response(status, {"detail": "Bad Gateway"}))

    result = rce.run("device", "start", "--pool")

    assert_all_skipped(result, fake_rce, {375, 376}, 2)
    for id in (375, 376):
        assert f"Cloud Device {id}: RCE answered its start with {status}; skipped" in result.stderr
        assert not looked_after_its_start(fake_rce, id)
    assert "may have made a Run" in result.stderr


@pytest.mark.parametrize("run_made", [False, True])
def test_a_start_with_no_answer_skips_the_member_with_a_warning_and_stops_nothing(
    rce, fake_rce, run_made
):
    pool(rce, fake_rce, {375: 2001, 376: 2002})
    if run_made:
        fake_rce.start_status = NO_ANSWER.status
    else:
        for id in (375, 376):
            fake_rce.fail_next("POST", start_path(id), NO_ANSWER)

    result = rce.run("device", "start", "--pool")

    assert_all_skipped(result, fake_rce, {375, 376}, 2)
    for id in (375, 376):
        assert f"Cloud Device {id}: RCE gave its start no answer" in result.stderr
        assert not looked_after_its_start(fake_rce, id)
    assert "may have made a Run" in result.stderr


def test_a_member_whose_dev_snapshot_rce_deleted_is_skipped_with_a_warning(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002})
    for id, snapshot in ((375, 2001), (376, 2002)):
        fake_rce.delete_snapshot(id, snapshot)

    result = rce.run("device", "start", "--pool")

    assert_all_skipped(result, fake_rce, {375, 376}, 2)
    assert "Cloud Device 375: Dev Snapshot 2001 is missing" in result.stderr
    assert "take a new one with `rce device setup-dev 376`" in result.stderr


@pytest.mark.parametrize(
    ("response", "words"),
    [
        (Response(401, {"detail": "Not authenticated"}), "RCE rejected the token"),
        (TRIAL_EXHAUSTED, "the RCE free trial is used up"),
        (TRIAL_RUN_LIMIT, "the RCE trial runs one Cloud Device at a time"),
        (OVER_CAP, "--max-runtime 999999 s is more than your organisation's maximum"),
    ],
)
def test_a_refusal_every_member_would_get_stops_the_claim_after_one_start(
    rce, fake_rce, response, words
):
    pool(rce, fake_rce, {375: 2001, 376: 2002, 377: 1063})
    for id in (375, 376, 377):
        fake_rce.fail_next("POST", start_path(id), response)

    result = rce.run("device", "start", "--pool", "--max-runtime", "999999")

    assert result.returncode == 4
    assert words in result.stderr
    assert "no Free Cloud Device" not in result.stderr
    assert result.stdout == ""
    assert sum(len(tries) for tries in starts(fake_rce).values()) == 1
    assert not [r for r in fake_rce.requests if r.path.endswith("/stop")]


def stops(fake_rce) -> list[str]:
    return [r.path for r in fake_rce.requests if r.method == "POST" and r.path.endswith("/stop")]


def test_a_claim_not_ready_in_time_stops_that_run_once_exits_5_and_tries_no_other(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002})
    fake_rce.boot_delay = 60

    result = rce.run("device", "start", "--pool", "--timeout", "1")

    assert result.returncode == 5
    [claimed] = starts(fake_rce)
    assert stops(fake_rce) == [f"/api/v1/devices/{claimed}/stop"]
    assert f"stopped the Run of Cloud Device {claimed}" in result.stderr


@pytest.mark.parametrize(
    ("response", "code"),
    [(Response(401, {"detail": "Not authenticated"}), 1), (Response(404, {"detail": "Not Found"}), 3)],
)
def test_a_claim_whose_wait_fails_stops_that_run_once_and_tries_no_other(
    rce, fake_rce, response, code
):
    """After the Claim it is today's `device start`: a failure while waiting, even one that
    would skip a member before the start, stops that Run and never exits 4."""
    pool(rce, fake_rce, {375: 2001, 376: 2002})
    fake_rce.start_delay = 1  # time to script the read that follows the start
    start = rce.spawn("device", "start", "--pool", "--no-wait")
    deadline = time.monotonic() + 30
    while not starts(fake_rce) and time.monotonic() < deadline:
        time.sleep(0.05)
    [claimed] = starts(fake_rce)
    fake_rce.fail_next("GET", f"/api/v1/devices/{claimed}", response)
    _, stderr = start.communicate(timeout=60)

    assert start.returncode == code, stderr
    assert stops(fake_rce) == [f"/api/v1/devices/{claimed}/stop"]
    assert starts(fake_rce).keys() == {claimed}


def test_ctrl_c_during_a_start_request_stops_nothing_and_warns_it_may_bill(rce, fake_rce):
    """RCE took the start and holds its answer: a Run on that member may be another job's
    Claim, so rce neither looks nor stops."""
    pool(rce, fake_rce, {375: 2001})
    fake_rce.start_delay = 30
    tty = rce.interactive("device", "start", "--pool")
    wait_for_request(fake_rce, "POST", start_path(375))
    tty.interrupt()
    result = tty.finish()

    assert result.returncode == 130
    assert not stops(fake_rce)
    assert not looked_after_its_start(fake_rce, 375)
    assert "Cloud Device 375: interrupted before RCE answered its start" in result.stderr
    assert "may have made a Run, which bills until its --max-runtime" in result.stderr


def test_ctrl_c_after_the_claim_stops_its_run(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001})
    fake_rce.boot_delay = 60
    tty = rce.interactive("device", "start", "--pool")
    wait_for_request(fake_rce, "POST", start_path(375))
    looked = len(fake_rce.requests_to("GET", "/api/v1/devices/375"))
    wait_for_request(fake_rce, "GET", "/api/v1/devices/375", looked + 1)
    tty.interrupt()
    result = tty.finish()

    assert result.returncode == 130
    assert "stopped the Run of Cloud Device 375" in result.stderr
    assert stops(fake_rce) == ["/api/v1/devices/375/stop"]


def test_no_wait_json_prints_the_claimed_id_and_run_id(rce, fake_rce):
    """Live RCE answers the start with no Run, and shows it on a later read (Run 4615)."""
    pool(rce, fake_rce, {375: 2001, 376: 2002}, running=(375,))
    fake_rce.boot_delay = 60
    fake_rce.run_hidden_reads = 2

    claimed = rce.json("device", "start", "--pool", "--no-wait", "--firmware", "304")

    assert claimed["id"] == 376 and claimed["status"] == "pending"
    assert claimed["run"]["id"] == fake_rce.devices[376]["running_device"]["id"]
    assert starts(fake_rce)[376][0]["firmware_version_id"] == "304"
    assert not stops(fake_rce)


@pytest.mark.parametrize(
    ("flags", "problem"),
    [
        (["--pool", "375"], "--pool takes no <device>"),
        (["--pool", "--snapshot", "2001"], "--pool takes no --snapshot"),
        (["--pool", "--wait-lock"], "--pool takes no --wait-lock"),
        (["375", "--wait-free", "60"], "--wait-free waits for a Free Cloud Device of the Pool"),
        (["--pool", "--wait-free", "0"], "--wait-free takes a number of seconds above 0"),
        (["--pool", "--wait-free", "-5"], "--wait-free takes a number of seconds above 0"),
        ([], "name a <device>, or pass --pool"),
    ],
)
def test_contradictory_flags_exit_2_before_sending_anything(rce, fake_rce, flags, problem):
    pool(rce, fake_rce, {375: 2001})

    result = rce.run("device", "start", *flags)

    assert result.returncode == 2
    assert problem in result.stderr
    assert fake_rce.requests == []


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        (None, "RCE_POOL is not set"),
        ("{375: 2001}", "RCE_POOL is not JSON"),
        ("{}", "RCE_POOL is empty"),
        ('{"player": 2001}', "RCE_POOL key 'player' is not an RCE id"),
        ('{"375": "2001"}', "RCE_POOL value for 375 is not a Snapshot id"),
    ],
)
def test_a_malformed_rce_pool_exits_2_before_sending_anything(rce, fake_rce, value, problem):
    pool(rce, fake_rce, {375: 2001})
    rce.env.pop("RCE_POOL")
    if value is not None:
        rce.env["RCE_POOL"] = value

    result = rce.run("device", "start", "--pool")

    assert result.returncode == 2
    assert problem in result.stderr
    assert fake_rce.requests == []


def test_a_member_rce_does_not_know_exits_3_after_only_the_look(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001})
    rce.env["RCE_POOL"] = json.dumps({"375": 2001, "999": 2002})

    result = rce.run("device", "start", "--pool")

    assert result.returncode == 3
    assert "999" in result.stderr
    assert [r.path for r in fake_rce.requests] == [DEVICES]


def test_a_retired_member_exits_2_after_only_the_look(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001})
    fake_rce.add_device(376, "retired/pool-376", "stb")
    rce.env["RCE_POOL"] = json.dumps({"375": 2001, "376": 2002})

    result = rce.run("device", "start", "--pool")

    assert result.returncode == 2
    assert "remove it from RCE_POOL" in result.stderr
    assert [r.path for r in fake_rce.requests] == [DEVICES]


# -- --wait-free S -------------------------------------------------------------


def waiting(rce) -> None:
    """Looks a few milliseconds apart instead of about 15 s (the test-only variable)."""
    rce.env["RCE_POOL_LOOK_SECONDS"] = "0.01"


def test_wait_free_claims_a_member_freed_after_some_looks(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002}, running=(375, 376))
    waiting(rce)
    fake_rce.free_after("GET", DEVICES, 376, times=3)  # another job stops it after our 3rd look

    result = rce.run("device", "start", "--pool", "--wait-free", "30")

    assert result.returncode == 0, result.stderr
    assert len(fake_rce.requests_to("GET", DEVICES)) == 4
    assert starts(fake_rce).keys() == {376}
    assert len(starts(fake_rce)[376]) == 1
    assert f"Claimed Cloud Device 376 (Run {fake_rce.devices[376]['running_device']['id']})" in result.stdout


def test_wait_free_exits_5_after_s_seconds_with_nothing_started(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002}, running=(375, 376))
    waiting(rce)
    began = time.monotonic()

    result = rce.run("device", "start", "--pool", "--wait-free", "0.5")

    assert result.returncode == 5
    assert time.monotonic() - began >= 0.5
    assert "no Free Cloud Device in the Pool in 0.5 s (2 members); nothing started" in result.stderr
    assert result.stdout == ""
    assert len(fake_rce.requests_to("GET", DEVICES)) > 1
    assert starts(fake_rce) == {}
    assert not stops(fake_rce)


@pytest.mark.parametrize(
    ("response", "words"),
    [
        (Response(401, {"detail": "Not authenticated"}), "RCE rejected the token"),
        (TRIAL_EXHAUSTED, "the RCE free trial is used up"),
        (TRIAL_RUN_LIMIT, "the RCE trial runs one Cloud Device at a time"),
        (OVER_CAP, "--max-runtime 999999 s is more than your organisation's maximum"),
    ],
)
def test_a_refusal_every_member_would_get_ends_the_wait_at_once(rce, fake_rce, response, words):
    pool(rce, fake_rce, {375: 2001, 376: 2002}, running=(375, 376))
    waiting(rce)
    fake_rce.free_after("GET", DEVICES, 375)
    fake_rce.fail_next("POST", start_path(375), response)

    result = rce.run("device", "start", "--pool", "--wait-free", "30", "--max-runtime", "999999")

    assert result.returncode == 4
    assert words in result.stderr
    assert result.stdout == ""
    assert result.stderr.count("free, waiting…") == 1  # the first look; none after the refusal
    assert starts(fake_rce).keys() == {375}
    assert not stops(fake_rce)


def test_each_look_says_how_many_are_free_on_stderr_and_json_stdout_is_unchanged(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002}, running=(375,))
    waiting(rce)
    fake_rce.take_after("GET", DEVICES, 376)  # another job claims it just after our 1st look
    fake_rce.free_after("GET", DEVICES, 375, times=2)  # and frees another after our 2nd

    result = rce.run("device", "start", "--pool", "--wait-free", "30", "--json")

    assert result.returncode == 0, result.stderr
    waits = [line for line in result.stderr.splitlines() if "waiting…" in line]
    assert waits == ["rce: 1 of 2 free, waiting…", "rce: 0 of 2 free, waiting…"]
    claimed = json.loads(result.stdout)
    assert claimed["id"] == 375
    assert claimed["run"]["id"] == fake_rce.devices[375]["running_device"]["id"]


def test_ctrl_c_while_waiting_exits_130_with_nothing_started(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001, 376: 2002}, running=(375, 376))
    rce.env["RCE_POOL_LOOK_SECONDS"] = "30"  # so the Ctrl-C lands while it waits
    tty = rce.interactive("device", "start", "--pool", "--wait-free", "120")
    tty.expect("0 of 2 free, waiting…")
    tty.interrupt()
    result = tty.finish()

    assert result.returncode == 130
    assert result.stdout == ""
    assert len(fake_rce.requests_to("GET", DEVICES)) == 1
    assert starts(fake_rce) == {}
    assert not stops(fake_rce)


def test_ctrl_c_after_a_claim_made_while_waiting_stops_its_run(rce, fake_rce):
    pool(rce, fake_rce, {375: 2001}, running=(375,))
    waiting(rce)
    fake_rce.free_after("GET", DEVICES, 375)
    fake_rce.boot_delay = 60  # the claimed Run takes its time to come up
    tty = rce.interactive("device", "start", "--pool", "--wait-free", "30")
    wait_for_request(fake_rce, "POST", start_path(375))
    looked = len(fake_rce.requests_to("GET", "/api/v1/devices/375"))
    wait_for_request(fake_rce, "GET", "/api/v1/devices/375", looked + 1)
    tty.interrupt()
    result = tty.finish()

    assert result.returncode == 130
    assert "stopped the Run of Cloud Device 375" in result.stderr
    assert stops(fake_rce) == ["/api/v1/devices/375/stop"]
