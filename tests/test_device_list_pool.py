import json

import pytest

from conftest import TOKEN
from fake_rce import WEBRTC_SECRETS


def pool(rce, members: dict[int, int]) -> None:
    """Set RCE_POOL as a pipeline would: RCE id -> Dev Snapshot id."""
    rce.env["RCE_POOL"] = json.dumps({str(id): snapshot for id, snapshot in members.items()})


def test_device_list_pool_shows_only_the_members_in_pool_order_and_how_many_are_free(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")  # not in the Pool
    fake_rce.add_device(375, "pool-1", "stb", running=True)
    fake_rce.add_device(376, "pool-2", "stb")
    fake_rce.add_device(377, "pool-3", "stb")
    for id, snapshot in ((375, 2001), (376, 2002), (377, 1063)):
        fake_rce.add_snapshot(id, snapshot)
    pool(rce, {377: 1063, 375: 2001, 376: 2002})

    result = rce.run("device", "list", "--pool")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "ID   DEVICE NAME  RCE NAME  TYPE  STATUS    RUN                         DEV SNAPSHOT",
        "377  -            pool-3    stb   shutdown  -                           1063 ready",
        "375  -            pool-1    stb   running   since 2026-11-16T21:00:00Z  2001 ready",
        "376  -            pool-2    stb   shutdown  -                           2002 ready",
        "2 of 3 free",
    ]


def test_device_list_pool_shows_each_dev_snapshot_as_ready_not_ready_or_missing(rce, fake_rce):
    for id in (375, 376, 377):
        fake_rce.add_device(id, f"pool-{id}", "stb")
    fake_rce.add_snapshot(375, 2001)
    fake_rce.add_snapshot(376, 2002, ready=False)  # 377's 1063 was deleted by RCE
    pool(rce, {375: 2001, 376: 2002, 377: 1063})

    result = rce.run("device", "list", "--pool")

    assert result.returncode == 0, result.stderr
    assert [line.split("  ")[-1].strip() for line in result.stdout.splitlines()[1:4]] == [
        "2001 ready",
        "2002 not ready",
        "1063 missing",
    ]
    assert "Cloud Device 377: Dev Snapshot 1063 is missing" in result.stdout
    assert "take a new one with `rce device setup-dev 377`" in result.stdout
    assert result.stdout.splitlines()[-1] == "3 of 3 free"
    reads = [r.path for r in fake_rce.requests if "/snapshots" in r.path]
    assert sorted(reads) == [
        "/api/v1/devices/375/snapshots/2001",
        "/api/v1/devices/376/snapshots/2002",
        "/api/v1/devices/377/snapshots/1063",
    ]


def test_device_list_pool_json_is_the_device_list_shape_with_each_dev_snapshot(rce, fake_rce):
    fake_rce.add_device(375, "pool-1", "stb", running=True)
    fake_rce.add_device(376, "pool-2", "tv")
    fake_rce.add_snapshot(375, 2001)
    pool(rce, {376: 2002, 375: 2001})

    devices = rce.json("device", "list", "--pool")

    assert devices == [
        {
            "id": 376,
            "device_name": None,
            "name": "pool-2",
            "type": "tv",
            "status": "shutdown",
            "run": None,
            "dev_snapshot": {"id": 2002, "status": "missing"},
        },
        {
            "id": 375,
            "device_name": None,
            "name": "pool-1",
            "type": "stb",
            "status": "running",
            "run": {
                "id": 9000,
                "created_at": "2026-11-16T21:00:00Z",
                "started_at": "2026-11-16T21:00:05Z",
                "running_at": "2026-11-16T21:01:11Z",
                "max_runtime": 3600,
                "snapshot_id": 998,
                "snapshot_name": "Live snapshot",
                "firmware_version_id": "395",
            },
            "dev_snapshot": {"id": 2001, "status": "ready"},
        },
    ]


def test_device_list_pool_counts_a_pending_run_as_busy_and_sends_only_reads(rce, fake_rce):
    fake_rce.add_device(375, "pool-1", "stb")
    fake_rce.add_device(376, "pool-2", "stb")["status"] = "pending"  # a start RCE just accepted
    fake_rce.add_device(377, "pool-3", "stb", running=True)
    for id, snapshot in ((375, 2001), (376, 2002), (377, 1063)):
        fake_rce.add_snapshot(id, snapshot)
    pool(rce, {375: 2001, 376: 2002, 377: 1063})

    result = rce.run("device", "list", "--pool")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "1 of 3 free"
    assert fake_rce.requests
    assert {r.method for r in fake_rce.requests} == {"GET"}


def test_device_list_pool_never_prints_the_token_or_webrtc_credentials(rce, fake_rce):
    fake_rce.add_device(375, "pool-1", "stb", running=True)
    fake_rce.add_snapshot(375, 2001)
    pool(rce, {375: 2001})

    for args in (["device", "list", "--pool"], ["device", "list", "--pool", "--json"]):
        result = rce.run(*args)
        assert result.returncode == 0, result.stderr
        for secret in (TOKEN, *WEBRTC_SECRETS):
            assert secret not in result.stdout + result.stderr


def test_device_list_pool_running_lists_only_members_with_a_run(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)  # not in the Pool
    fake_rce.add_device(375, "pool-1", "stb")
    fake_rce.add_device(376, "pool-2", "stb", running=True)
    for id, snapshot in ((375, 2001), (376, 2002)):
        fake_rce.add_snapshot(id, snapshot)
    pool(rce, {375: 2001, 376: 2002})

    assert [d["id"] for d in rce.json("device", "list", "--pool", "--running")] == [376]
    result = rce.run("device", "list", "--pool", "--running")
    assert result.returncode == 0, result.stderr
    assert [line.split()[0] for line in result.stdout.splitlines()] == ["ID", "376", "1"]
    assert result.stdout.splitlines()[-1] == "1 of 2 free"


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        (None, "RCE_POOL is not set"),
        ("{375: 2001}", "RCE_POOL is not JSON"),
        ("[375, 376]", "RCE_POOL is not a JSON object"),
        ("{}", "RCE_POOL is empty"),
        ('{"player": 2001}', "RCE_POOL key 'player' is not an RCE id"),
        ('{"375 ": 2001}', "RCE_POOL key '375 ' is not an RCE id"),
        ('{"375": "2001"}', "RCE_POOL value for 375 is not a Snapshot id"),
        ('{"375": 2001.5}', "RCE_POOL value for 375 is not a Snapshot id"),
        ('{"375": true}', "RCE_POOL value for 375 is not a Snapshot id"),
    ],
)
def test_device_list_pool_exits_2_naming_what_is_wrong_with_rce_pool(rce, fake_rce, value, problem):
    fake_rce.add_device(375, "pool-1", "stb")
    if value is not None:
        rce.env["RCE_POOL"] = value

    result = rce.run("device", "list", "--pool")

    assert result.returncode == 2, result.stderr
    assert problem in result.stderr
    assert result.stdout == ""
    assert fake_rce.requests == []


def test_device_list_pool_exits_3_naming_each_member_rce_does_not_know(rce, fake_rce):
    fake_rce.add_device(375, "pool-1", "stb")
    fake_rce.add_snapshot(375, 2001)
    pool(rce, {375: 2001, 998: 2002, 999: 1063})

    result = rce.run("device", "list", "--pool")

    assert result.returncode == 3, result.stderr
    assert "998, 999" in result.stderr
    assert result.stdout == ""
    assert [r.path for r in fake_rce.requests] == ["/api/v1/devices"]


def test_device_list_pool_exits_2_for_a_retired_cloud_device_in_the_pool(rce, fake_rce):
    fake_rce.add_device(375, "pool-1", "stb")
    fake_rce.add_device(376, "retired/pool-2", "stb")
    fake_rce.add_snapshot(375, 2001)
    pool(rce, {375: 2001, 376: 2002})

    result = rce.run("device", "list", "--pool")

    assert result.returncode == 2, result.stderr
    assert "Cloud Device 376 is retired (named 'retired/pool-2')" in result.stderr
    assert "remove it from RCE_POOL" in result.stderr
    assert result.stdout == ""
    assert [r.path for r in fake_rce.requests] == ["/api/v1/devices"]
