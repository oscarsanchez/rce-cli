"""`rce ecp`: any ECP query on a Run, through the Run's port proxy to 8060."""

from conftest import TOKEN

ECP = "/instance/uuid-351/api/v0/ports/8060/http"  # RCE's path; glossary-ok


def running_player(rce, fake_rce) -> dict:
    device = fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.name_device("351", "player")
    return device


def test_ecp_prints_the_xml_the_device_answers(rce, fake_rce):
    running_player(rce, fake_rce)

    result = rce.run("ecp", "player", "query/device-info")

    assert result.returncode == 0, result.stderr
    assert "<device-info>" in result.stdout
    assert "<model-name>Roku Native</model-name>" in result.stdout
    [request] = fake_rce.requests_to("GET", f"{ECP}/query/device-info")
    assert request.headers["authorization"] == f"Bearer {TOKEN}"


def test_ecp_json_parses_device_info(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.ecp_mode, fake_rce.dev_mode = "limited", False

    info = rce.json("ecp", "player", "query/device-info")

    assert info["model-name"] == "Roku Native"
    assert info["software-version"] == "16.0.4"
    assert info["developer-enabled"] is False
    assert info["ecp-setting-mode"] == "limited"
    assert info["keyed-developer-id"] == ""  # an empty element, <keyed-developer-id />


def test_ecp_json_parses_the_active_app(rce, fake_rce):
    running_player(rce, fake_rce)

    active = rce.json("ecp", "player", "query/active-app")

    assert active == {"app": {"name": "My Dev App", "id": "dev", "type": "appl", "version": "1.0.0"}}


def test_ecp_json_on_the_home_screen_has_an_app_with_only_a_name(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.active_app = "<app>Roku</app>"

    assert rce.json("ecp", "player", "query/active-app") == {"app": {"name": "Roku"}}


def test_ecp_json_for_other_commands_gives_the_raw_body(rce, fake_rce):
    running_player(rce, fake_rce)

    answer = rce.json("ecp", "player", "launch/dev", "--method", "POST")

    assert answer == {"path": "launch/dev", "body": ""}


def test_ecp_posts_with_the_query_string_passed_through(rce, fake_rce):
    running_player(rce, fake_rce)

    result = rce.run("ecp", "player", "/launch/dev?contentId=abc&MediaType=movie", "--method", "POST")

    assert result.returncode == 0, result.stderr
    [request] = fake_rce.requests_to("POST", f"{ECP}/launch/dev")
    assert request.query == {"contentId": ["abc"], "MediaType": ["movie"]}


def test_ecp_refused_by_limited_mobile_control_points_to_setup_dev(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.ecp_mode = "limited"

    result = rce.run("ecp", "player", "query/apps")

    assert result.returncode == 4
    assert "Control by mobile apps" in result.stderr
    assert "rce device setup-dev player" in result.stderr


def test_ecp_on_a_cloud_device_that_is_not_running_exits_4(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    result = rce.run("ecp", "player", "query/device-info")

    assert result.returncode == 4
    assert "not running" in result.stderr
