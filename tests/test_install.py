"""The install step puts `rce` on PATH and leaves Claude's directory alone (the plugin covers Claude)."""

import json
import subprocess

from conftest import RCE, REPO

INSTALL = REPO / "install.sh"


def install(rce) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(INSTALL)], cwd=rce.cwd, env=rce.env, capture_output=True, text=True
    )


def test_install_links_rce_into_the_local_bin_and_is_safe_to_rerun(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player")
    link = rce.home / ".local" / "bin" / "rce"

    for _ in range(2):
        result = install(rce)
        assert result.returncode == 0, result.stderr
        assert link.is_symlink() and link.resolve() == RCE

    listed = subprocess.run(
        [str(link), "device", "list", "--json"],
        cwd=rce.cwd, env=rce.env, capture_output=True, text=True,
    )
    assert listed.returncode == 0, listed.stderr
    assert [d["id"] for d in json.loads(listed.stdout)] == [351]


def test_install_creates_nothing_under_claude_and_keeps_what_is_there(rce):
    claude = rce.home / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text("{}\n")

    for _ in range(2):
        result = install(rce)
        assert result.returncode == 0, result.stderr

    assert list(claude.rglob("*")) == [claude / "settings.json"]
    assert (claude / "settings.json").read_text() == "{}\n"


def test_install_leaves_an_unrelated_rce_file_alone(rce):
    link = rce.home / ".local" / "bin" / "rce"
    link.parent.mkdir(parents=True)
    link.write_text("someone else's rce\n")

    result = install(rce)

    assert result.returncode != 0
    assert str(link) in result.stderr
    assert link.read_text() == "someone else's rce\n"


def test_unknown_commands_are_usage_errors(rce):
    assert rce.run("device", "explode").returncode == 2
    assert rce.run().returncode == 2
