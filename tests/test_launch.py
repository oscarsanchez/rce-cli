"""`rce launch`: start the dev app on a Run over ECP, with launch params."""

from conftest import TOKEN

LAUNCH = "/instance/uuid-351/api/v0/ports/8060/http/launch/dev"  # RCE's path; glossary-ok


def running_player(rce, fake_rce) -> dict:
    device = fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.name_device("351", "player")
    return device


def test_launch_posts_launch_dev_with_the_params(rce, fake_rce):
    running_player(rce, fake_rce)

    result = rce.run("launch", "player", "--param", "contentId=abc", "--param", "mediaType=movie")

    assert result.returncode == 0, result.stderr
    [request] = fake_rce.requests_to("POST", LAUNCH)
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert request.query == {"contentId": ["abc"], "mediaType": ["movie"]}
    assert "player (351)" in result.stdout


def test_launch_url_encodes_param_values(rce, fake_rce):
    running_player(rce, fake_rce)
    proxy_base = "https://t.example/s3cr/cloud device?x=1&y=2#z"

    result = rce.run("launch", "player", "--param", f"proxyBase={proxy_base}", "--param", "case=a+b")

    assert result.returncode == 0, result.stderr
    [request] = fake_rce.requests_to("POST", LAUNCH)
    assert request.query == {"proxyBase": [proxy_base], "case": ["a+b"]}


def test_launch_without_params_sends_no_query(rce, fake_rce):
    running_player(rce, fake_rce)

    launched = rce.json("launch", "player")

    [request] = fake_rce.requests_to("POST", LAUNCH)
    assert request.query == {}
    assert launched == {"id": 351, "device_name": "player", "params": {}}


def test_launch_param_without_an_equals_sign_is_a_usage_error(rce, fake_rce):
    running_player(rce, fake_rce)

    result = rce.run("launch", "player", "--param", "contentId")

    assert result.returncode == 2
    assert "key=value" in result.stderr
    assert fake_rce.requests_to("POST", LAUNCH) == []


def test_launch_without_a_dev_app_installed_says_to_sideload_one(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.dev_app_installed = False

    result = rce.run("launch", "player")

    assert result.returncode == 3
    assert "no dev app" in result.stderr
    assert "rce sideload player" in result.stderr


def test_launch_refused_by_limited_mobile_control_points_to_setup_dev(rce, fake_rce):
    running_player(rce, fake_rce)
    fake_rce.ecp_mode = "limited"

    result = rce.run("launch", "player")

    assert result.returncode == 4
    assert "Control by mobile apps" in result.stderr
    assert "rce device setup-dev player" in result.stderr
