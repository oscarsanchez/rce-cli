"""The README's pipeline recipe: every rce command and flag it uses is in rce's own help."""

from __future__ import annotations

import re

from conftest import REPO

COMMAND = re.compile(r"(?<![\w/.-])rce((?: [a-z][\w-]*){1,2})(.*)")


def pipeline_section() -> str:
    readme = (REPO / "README.md").read_text()
    section = re.search(r"^## Pipelines \(CI/CD\)\n(.*?)(?=^## )", readme, re.S | re.M)
    assert section, "README has no 'Pipelines (CI/CD)' section"
    return section.group(1).replace("\\\n", " ")


def test_pipeline_recipe_uses_only_commands_and_flags_rce_has(rce):
    calls = [COMMAND.search(line) for line in pipeline_section().splitlines()]
    calls = [call for call in calls if call]
    assert calls, "the recipe calls no rce command"

    for call in calls:
        help_ = rce.run(*call.group(1).split(), "--help")
        assert help_.returncode == 0, f"rce{call.group(1)}: {help_.stderr}"
        for flag in re.findall(r"(?<!\S)--[a-z][\w-]*", call.group(2)):
            assert re.search(rf"{flag}\b", help_.stdout), f"rce{call.group(1)} has no {flag}"
