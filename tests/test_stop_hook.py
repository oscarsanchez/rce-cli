"""The Claude Code Stop hook warns about Runs still billing, and is otherwise silent."""

import json
import os
import shutil
import socket
import subprocess
from datetime import datetime, timedelta, timezone

from conftest import REPO, RCE

HOOK = REPO / "hooks" / "rce-stop-hook"
HOOKS_FILE = REPO / "hooks" / "hooks.json"


def stop_hook(rce, **env: str) -> subprocess.CompletedProcess:
    """Run the hook as Claude Code does: `rce` on PATH, the Stop event's JSON on stdin."""
    bin = rce.home / ".local" / "bin"
    bin.mkdir(parents=True, exist_ok=True)
    if not (bin / "rce").exists():
        (bin / "rce").symlink_to(RCE)
    return run_hook([str(HOOK)], rce, {**rce.env, "PATH": f"{bin}{os.pathsep}{rce.env['PATH']}", **env})


def plugin_stop_hook(rce) -> subprocess.CompletedProcess:
    """Run the hook as the installed plugin does: the hooks file's command with
    CLAUDE_PLUGIN_ROOT exported, and no `rce` anywhere on PATH."""
    [stop] = json.loads(HOOKS_FILE.read_text())["hooks"]["Stop"]
    [hook] = stop["hooks"]
    bin = rce.home / "uv-only-bin"
    bin.mkdir()
    (bin / "uv").symlink_to(shutil.which("uv"))
    env = {**rce.env, "PATH": os.pathsep.join([str(bin), "/usr/bin", "/bin"]), "CLAUDE_PLUGIN_ROOT": str(REPO)}
    return run_hook(["sh", "-c", hook["command"]], rce, env)


def run_hook(command: list[str], rce, env: dict[str, str]) -> subprocess.CompletedProcess:
    """The Stop event's JSON on stdin, as Claude Code sends it."""
    return subprocess.run(
        command,
        cwd=rce.cwd,
        env=env,
        input=json.dumps({"hook_event_name": "Stop", "stop_hook_active": False}),
        capture_output=True,
        text=True,
        timeout=30,
    )


def billing_since(device: dict, elapsed: timedelta) -> None:
    started = datetime.now(timezone.utc) - elapsed
    device["running_device"]["created_at"] = started.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_warns_naming_each_running_cloud_device_and_its_elapsed_time(rce, fake_rce):
    fake_rce.add_device(350, "Idle TV", "tv")
    billing_since(fake_rce.add_device(351, "Personal RCE Player", running=True), timedelta(minutes=12, seconds=30))
    billing_since(fake_rce.add_device(352, "Personal RCE TV", "tv", running=True), timedelta(hours=1, minutes=5, seconds=30))
    rce.name_device("351", "player")

    result = stop_hook(rce)

    assert result.returncode == 0, result.stderr
    warning = json.loads(result.stdout)["systemMessage"]
    assert "player (351) for 12 min" in warning
    assert "Personal RCE TV (352) for 1 h 05 min" in warning
    assert "Idle TV" not in warning
    assert "rce device stop" in warning


def test_plugin_hook_warns_using_the_plugins_own_rce(rce, fake_rce):
    billing_since(fake_rce.add_device(351, "Personal RCE Player", running=True), timedelta(minutes=3, seconds=10))

    result = plugin_stop_hook(rce)

    assert result.returncode == 0, result.stderr
    assert "Personal RCE Player (351) for 3 min" in json.loads(result.stdout)["systemMessage"]


def test_silent_when_nothing_is_running(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player")

    result = stop_hook(rce)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_silent_without_a_token(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", running=True)
    rce.rk_config.unlink()

    result = stop_hook(rce)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_silent_when_rce_is_unreachable(rce):
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]

    result = stop_hook(rce, RCE_API_URL=f"http://127.0.0.1:{port}/api/v1")

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_silent_when_rce_does_not_answer_in_time(rce, fake_rce):
    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen()  # accepts connections, never answers
        port = silent.getsockname()[1]

        result = stop_hook(rce, RCE_API_URL=f"http://127.0.0.1:{port}/api/v1")

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
