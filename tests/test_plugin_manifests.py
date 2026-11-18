"""The Claude Code plugin's manifests, read as data: what `claude plugin install` reads."""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

from conftest import REPO

MANIFESTS = REPO / ".claude-plugin"
HOOK = REPO / "hooks" / "rce-stop-hook"


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def inside_repo(relative: str) -> Path:
    """A manifest path: written `./…` and resolving inside the plugin root."""
    assert relative.startswith("./"), relative
    path = (REPO / relative).resolve()
    assert path.is_relative_to(REPO), relative
    return path


def test_plugin_manifest_describes_rce_cli():
    plugin = load(MANIFESTS / "plugin.json")

    assert plugin["name"] == "rce-cli"
    assert "macOS/Linux, needs uv" in plugin["description"]
    assert plugin["license"] == "MIT"
    assert plugin["repository"].startswith("https://github.com/")
    assert plugin["repository"].endswith("/rce-cli")


def test_plugin_version_is_the_version_rce_prints(rce):
    plugin = load(MANIFESTS / "plugin.json")

    result = rce.run("--version")

    assert result.stdout == f"rce {plugin['version']}\n"


def test_plugin_skills_are_the_rce_skill_folder():
    plugin = load(MANIFESTS / "plugin.json")

    skills = [inside_repo(path) for path in plugin["skills"]]

    assert skills == [REPO / "skill"]
    assert "\nname: rce\n" in (REPO / "skill" / "SKILL.md").read_text()


def test_marketplace_lists_the_plugin_from_this_repo():
    plugin = load(MANIFESTS / "plugin.json")
    marketplace = load(MANIFESTS / "marketplace.json")

    assert marketplace["name"] == "rce-cli"
    assert marketplace["owner"]["name"]
    [entry] = marketplace["plugins"]
    assert entry["name"] == plugin["name"]
    assert inside_repo(entry["source"]) == REPO


def test_hooks_file_runs_the_stop_hook_from_the_plugin_root():
    hooks = load(REPO / "hooks" / "hooks.json")["hooks"]

    [stop] = hooks["Stop"]
    [hook] = stop["hooks"]
    assert hook["type"] == "command"
    command = shlex.split(hook["command"].replace("${CLAUDE_PLUGIN_ROOT}", str(REPO)))

    assert command == [str(HOOK)]
    assert os.access(HOOK, os.X_OK)
