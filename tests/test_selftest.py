"""`rce selftest --live`: start, use and stop a real Cloud Device end to end.

Against the fake, the fake's dev app prints what the test app's BrightScript
`print`s once it is launched, so the console steps see the marker only if the
generated app really prints it.
"""

import io
import signal
import time
import zipfile

from conftest import TOKEN
from fake_rce import Response

START = "/api/v1/devices/351/start"
STOP = "/api/v1/devices/351/stop"
STEPS = ["start", "device-info", "sideload", "launch", "console", "screenshot", "forward", "stop"]


def player(rce, fake_rce, password: str | None = None) -> None:
    """A stopped Cloud Device named player, with its Dev Password stored as setup-dev stores it."""
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    rce.config.write_text(
        rce.config.read_text() + f'dev_password = "{password or fake_rce.dev_password}"\n'
    )


def assert_no_secrets(result, fake_rce) -> None:
    for secret in (TOKEN, fake_rce.dev_password):
        assert secret not in result.stdout + result.stderr


def test_all_steps_pass_and_the_run_is_stopped(rce, fake_rce):
    player(rce, fake_rce)

    result = rce.run("selftest", "--live", "--device", "player", "--yes")

    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    for number, step in enumerate(STEPS, 1):
        assert any(line.startswith(f"ok   {number} {step}") for line in lines), result.stdout
    assert "FAIL" not in result.stdout
    assert len(fake_rce.requests_to("POST", START)) == 1
    assert len(fake_rce.requests_to("POST", STOP)) == 1
    assert fake_rce.devices[351]["status"] == "shutdown"
    assert fake_rce.bridge(8085).connections == 2  # the console step's, then the forward's
    assert_no_secrets(result, fake_rce)


def test_the_test_app_is_a_zip_with_a_manifest_generated_at_runtime(rce, fake_rce):
    player(rce, fake_rce)

    result = rce.run("selftest", "--live", "--device", "player", "--yes")

    assert result.returncode == 0, result.stdout + result.stderr
    with zipfile.ZipFile(io.BytesIO(fake_rce.installed_archive)) as app:
        manifest = app.read("manifest").decode()
        assert "title=" in manifest and "major_version=" in manifest
        assert "source/main.brs" in app.namelist()


def test_a_failing_step_is_reported_and_the_run_is_still_stopped(rce, fake_rce):
    player(rce, fake_rce)
    fake_rce.next_install_fails = True

    result = rce.run("selftest", "--live", "--device", "player", "--yes")

    assert result.returncode == 4
    assert "FAIL 3 sideload: " in result.stdout
    assert "Install Failure: Unzip failed." in result.stdout
    assert "launch" not in result.stdout  # the steps after a failure don't run
    assert "ok   8 stop" in result.stdout
    assert "selftest failed at sideload" in result.stderr
    assert len(fake_rce.requests_to("POST", STOP)) == 1
    assert fake_rce.devices[351]["status"] == "shutdown"


def test_interrupting_it_stops_the_run(rce, fake_rce):
    player(rce, fake_rce)
    # The launch is answered without running the app, so the console never shows the marker.
    launch = "/instance/uuid-351-9000/api/v0/ports/8060/http/launch/dev"  # glossary-ok
    fake_rce.fail_next("POST", launch, Response(200, ""))
    selftest = rce.spawn("selftest", "--live", "--device", "player", "--yes")
    deadline = time.monotonic() + 30
    while not fake_rce.bridge(8085).connections:  # waiting on the console for the marker
        assert time.monotonic() < deadline, selftest.stderr.read()
        time.sleep(0.1)

    selftest.send_signal(signal.SIGINT)
    stdout, stderr = selftest.communicate(timeout=30)

    assert selftest.returncode == 130, stderr
    assert "Traceback" not in stderr
    assert "ok   8 stop" in stdout
    assert len(fake_rce.requests_to("POST", STOP)) == 1
    assert fake_rce.devices[351]["status"] == "shutdown"


def test_it_shows_the_projected_minutes_and_cost_and_asks_first(rce, fake_rce):
    player(rce, fake_rce)

    result = rce.run_tty("selftest", "--live", "--device", "player", answer="n")

    assert result.returncode == 2
    assert "about 5 min (about $0.02 at $0.20/h), capped at 10 min ($0.03)" in result.stderr
    assert "cancelled" in result.stderr
    assert fake_rce.requests_to("POST", START) == []


def test_answering_yes_at_the_prompt_runs_it(rce, fake_rce):
    player(rce, fake_rce)

    result = rce.run_tty("selftest", "--live", "--device", "player", answer="y")

    assert result.returncode == 0, result.stdout + result.stderr
    assert len(fake_rce.requests_to("POST", STOP)) == 1


def test_without_a_terminal_or_yes_it_starts_nothing(rce, fake_rce):
    player(rce, fake_rce)

    result = rce.run("selftest", "--live", "--device", "player")

    assert result.returncode == 2
    assert "needs confirmation" in result.stderr
    assert fake_rce.requests_to("POST", START) == []


def test_without_live_it_explains_the_offline_tests_are_the_pytest_suite(rce, fake_rce):
    player(rce, fake_rce)

    result = rce.run("selftest")

    assert result.returncode == 2
    assert "pytest" in result.stderr
    assert "--live" in result.stderr
    assert fake_rce.requests == [r for r in fake_rce.requests if r.method == "GET"]
    assert fake_rce.requests_to("POST", START) == []


def test_it_never_stops_a_run_it_did_not_start(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    rce.name_device("351", "player")
    rce.config.write_text(rce.config.read_text() + f'dev_password = "{fake_rce.dev_password}"\n')

    result = rce.run("selftest", "--live", "--device", "player", "--yes")

    assert result.returncode == 4
    assert "FAIL 1 start" in result.stdout
    assert "already running" in result.stdout
    assert fake_rce.requests_to("POST", STOP) == []


def test_without_a_dev_password_it_says_so_before_starting(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")

    result = rce.run("selftest", "--live", "--device", "player", "--yes")

    assert result.returncode == 4
    assert "rce device setup-dev player" in result.stderr
    assert fake_rce.requests_to("POST", START) == []


def test_without_device_it_uses_the_only_device_name(rce, fake_rce):
    player(rce, fake_rce)

    report = rce.json("selftest", "--live", "--yes")

    assert (report["id"], report["device_name"]) == (351, "player")


def test_json_reports_every_step(rce, fake_rce):
    player(rce, fake_rce)

    report = rce.json("selftest", "--live", "--device", "player", "--yes")

    assert report["passed"] is True
    assert [s["step"] for s in report["steps"]] == STEPS
    assert all(s["ok"] for s in report["steps"])
