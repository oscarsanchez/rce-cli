from conftest import TOKEN
from fake_rce import WEBRTC_SECRETS


def test_device_list_json_shows_each_cloud_device(rce, fake_rce):
    fake_rce.add_device(352, "Personal RCE TV", "tv")
    fake_rce.add_device(351, "Personal RCE Player", "stb")

    devices = rce.json("device", "list")

    assert devices == [
        {
            "id": 352,
            "device_name": None,
            "name": "Personal RCE TV",
            "type": "tv",
            "status": "shutdown",
            "run": None,
        },
        {
            "id": 351,
            "device_name": None,
            "name": "Personal RCE Player",
            "type": "stb",
            "status": "shutdown",
            "run": None,
        },
    ]
    [request] = fake_rce.requests_to("GET", "/api/v1/devices")
    assert request.headers["authorization"] == f"Bearer {TOKEN}"


def test_device_list_json_shows_each_device_name(rce, fake_rce):
    fake_rce.add_device(352, "Personal RCE TV", "tv")
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    devices = rce.json("device", "list")

    assert [(d["id"], d["device_name"]) for d in devices] == [(352, None), (351, "player")]


def test_device_list_json_shows_the_active_run_without_webrtc_credentials(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)

    [device] = rce.json("device", "list")

    assert device["status"] == "running"
    assert device["run"] == {
        "id": 9000,
        "created_at": "2026-11-16T21:00:00Z",
        "started_at": "2026-11-16T21:00:05Z",
        "running_at": "2026-11-16T21:01:11Z",
        "max_runtime": 3600,
        "snapshot_id": 998,
        "snapshot_name": "Live snapshot",
        "firmware_version_id": "395",
        "firmware_version_display_name": "v16.0.4 b853",
    }


def test_device_list_json_gives_no_firmware_name_when_the_device_names_another_firmware(
    rce, fake_rce
):
    device = fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    device["firmware_version_id"] = "304"  # the Cloud Device's Firmware isn't the Run's
    device["firmware_version_display_name"] = "v15.3.4 b872"

    [device] = rce.json("device", "list")

    assert device["run"]["firmware_version_id"] == "395"
    assert device["run"]["firmware_version_display_name"] is None


def test_device_list_never_prints_the_token_or_webrtc_credentials(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)

    for args in (["device", "list"], ["device", "list", "--json"]):
        result = rce.run(*args)
        assert result.returncode == 0, result.stderr
        output = result.stdout + result.stderr
        for secret in (TOKEN, *WEBRTC_SECRETS):
            assert secret not in output


def test_device_list_for_people_falls_back_to_the_firmware_id_without_a_name(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)["firmware_version_id"] = "304"

    result = rce.run("device", "list")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[1].split()[-1] == "395"
    assert [(r.method, r.path) for r in fake_rce.requests] == [("GET", "/api/v1/devices")]


def test_device_list_running_shows_only_cloud_devices_with_a_run(rce, fake_rce):
    fake_rce.add_device(352, "Personal RCE TV", "tv")
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)

    devices = rce.json("device", "list", "--running")

    assert [d["id"] for d in devices] == [351]


def test_device_list_running_says_so_when_nothing_is_running(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")

    assert rce.json("device", "list", "--running") == []
    result = rce.run("device", "list", "--running")
    assert (result.returncode, result.stdout) == (0, "No running Cloud Devices.\n")


def test_device_list_prints_a_table_for_people(rce, fake_rce):
    fake_rce.add_device(352, "Personal RCE TV", "tv")
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.name_device("351", "player")

    result = rce.run("device", "list")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "ID   DEVICE NAME  RCE NAME             TYPE  STATUS    RUN                         FIRMWARE",
        "352  -            Personal RCE TV      tv    shutdown  -                           -",
        "351  player       Personal RCE Player  stb   running   since 2026-11-16T21:00:00Z  v16.0.4 b853",
    ]
