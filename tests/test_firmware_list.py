"""`rce firmware list`: the Firmware RCE offers, and which one `device start` uses by default."""

from fake_rce import Response

FIRMWARE = "/api/v1/firmwareVersions"


def test_json_lists_every_firmware_in_rces_order_marking_one_default_per_device_type(rce, fake_rce):
    firmware = rce.json("firmware", "list")

    assert firmware == [
        {"firmware_version_id": "303", "device_type": "tv", "display_name": "v15.3.4 b872", "default": False},
        {"firmware_version_id": "304", "device_type": "stb", "display_name": "v15.3.4 b872", "default": False},
        {"firmware_version_id": "395", "device_type": "stb", "display_name": "v16.0.4 b853", "default": True},
        {"firmware_version_id": "396", "device_type": "tv", "display_name": "v16.0.4 b853", "default": True},
    ]


def test_the_default_is_the_firmware_device_start_sends_when_given_none(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    fake_rce.add_device(352, "Personal RCE TV", "tv")
    fake_rce.one_run_at_a_time = False
    defaults = {f["device_type"]: f["firmware_version_id"] for f in rce.json("firmware", "list") if f["default"]}

    for device_id in (351, 352):
        rce.json("device", "start", str(device_id), "--no-wait")

    sent = {
        device_type: start.json()["firmware_version_id"]
        for device_type, device_id in (("stb", 351), ("tv", 352))
        for start in fake_rce.requests_to("POST", f"/api/v1/devices/{device_id}/start")
    }
    assert sent == defaults


def test_type_asks_rce_for_that_device_types_firmware_only(rce, fake_rce):
    firmware = rce.json("firmware", "list", "--type", "tv")

    assert [(f["firmware_version_id"], f["default"]) for f in firmware] == [("303", False), ("396", True)]
    [read] = fake_rce.requests_to("GET", FIRMWARE)
    assert read.query == {"device_type": ["tv"], "items": ["0"]}


def test_human_output_is_a_row_per_firmware_marking_each_device_types_default(rce, fake_rce):
    result = rce.run("firmware", "list")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "ID   TYPE  DISPLAY NAME  DEFAULT",
        "303  tv    v15.3.4 b872  -",
        "304  stb   v15.3.4 b872  -",
        "395  stb   v16.0.4 b853  default",
        "396  tv    v16.0.4 b853  default",
    ]
    [read] = fake_rce.requests
    assert (read.method, read.path, read.query) == ("GET", FIRMWARE, {"items": ["0"]})


def test_a_firmware_without_a_display_name_shows_a_dash(rce, fake_rce):
    unnamed = {"firmware_version_id": "500", "device_type": "tv", "display_name": None}
    fake_rce.fail_next("GET", FIRMWARE, Response(200, [unnamed]))

    result = rce.run("firmware", "list")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[1:] == ["500  tv    -             default"]


def test_no_firmware_prints_nothing_or_an_empty_json_list(rce, fake_rce):
    fake_rce.fail_next("GET", FIRMWARE, Response(200, []), times=2)

    human = rce.run("firmware", "list")
    as_json = rce.json("firmware", "list")

    assert (human.returncode, human.stdout) == (0, "")
    assert as_json == []


def test_an_unknown_type_is_an_argument_error_and_asks_rce_nothing(rce, fake_rce):
    result = rce.run("firmware", "list", "--type", "phone")

    assert result.returncode == 2
    assert fake_rce.requests == []


def test_device_starts_firmware_help_points_to_firmware_list(rce):
    result = rce.run("device", "start", "--help")

    assert "rce firmware list" in " ".join(result.stdout.split())
