"""The README's pipeline recipes: every rce command and flag they use is in rce's own help,
and each stop step stops only the Run its job started."""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import NamedTuple

import pytest

from conftest import REPO

COMMAND = re.compile(r"(?<![\w/.-])rce((?: [a-z][\w-]*){1,2})([^|]*)")  # flags up to a pipe
START, STOP = "Start the Run", "Stop the Run"  # the recipes' step names
DEVICE = "device"  # the recipe for one Cloud Device, before the section's subsections
RECIPES = (DEVICE,)


def pipeline_section() -> str:
    readme = (REPO / "README.md").read_text()
    section = re.search(r"^## Pipelines \(CI/CD\)\n(.*?)(?=^## )", readme, re.S | re.M)
    assert section, "README has no 'Pipelines (CI/CD)' section"
    return section.group(1).replace("\\\n", " ")


def workflow(recipe: str) -> str:
    part = pipeline_section().split("\n### ")[0]
    block = re.search(r"```yaml\n(.*?)```", part, re.S)
    assert block, f"the {recipe} recipe has no yaml block"
    return block.group(1)


def recipe_steps(recipe: str) -> dict[str, dict[str, str]]:
    """The workflow's steps by name: each one's keys (`id`, `if`, `run`...), comments dropped."""
    steps = {}
    for block in re.split(r"^ {6}- ", workflow(recipe).split("    steps:\n", 1)[1], flags=re.M)[1:]:
        fields, key = {}, None
        for line in block.splitlines():
            field = re.match(r"^(?: {8})?([a-z-]+): ?(.*)$", line)
            variable = re.match(r"^ {10}([A-Z_]+): (.*)$", line)
            if field:
                key, value = field.groups()
                fields[key] = "" if value == "|" else re.sub(r"\s+#.*", "", value)
            elif key == "env" and variable:
                fields.setdefault("variables", {})[variable[1]] = variable[2]
            elif key == "run":
                fields["run"] += line.strip() + "\n"
        steps[fields.get("name", fields.get("uses"))] = fields
    return steps


class Step(NamedTuple):
    code: int
    outputs: dict[str, str]  # what it wrote to $GITHUB_OUTPUT
    calls: list[str]  # the arguments of each `rce` call
    stdout: str
    stderr: str


def run_step(
    tmp_path,
    recipe: str,
    name: str,
    exit_code: int = 0,
    stdout: str = "",
    start_outputs: dict[str, str] | None = None,
) -> Step:
    """Run one of the recipe's steps the way GitHub runs a step, with an `rce` that prints
    `stdout` and exits `exit_code`, and the step's `env:` filled from the start step's
    outputs."""
    steps = recipe_steps(recipe)
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    calls, printed = tmp_path / "rce_calls", tmp_path / "rce_stdout"
    calls.write_text("")
    printed.write_text(stdout)
    (bin_ / "rce").write_text(f'#!/bin/sh\necho "$*" >> {calls}\ncat {printed}\nexit {exit_code}\n')
    (bin_ / "rce").chmod(0o755)
    outputs = tmp_path / "github_output"
    outputs.write_text("")
    start_id = steps[START]["id"]
    variables = {
        variable: re.sub(
            rf"\$\{{\{{ steps\.{start_id}\.outputs\.(\w+) \}}\}}",
            lambda output: (start_outputs or {}).get(output[1], ""),
            value,
        )
        for variable, value in steps[name].get("variables", {}).items()
    }
    step = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", steps[name]["run"]],
        env={
            **os.environ,
            "PATH": f"{bin_}:{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(outputs),
            "RCE_DEVICE": "351",
            **variables,
        },
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    return Step(
        step.returncode,
        dict(line.split("=", 1) for line in outputs.read_text().splitlines()),
        calls.read_text().splitlines(),
        step.stdout,
        step.stderr,
    )


STARTED = {DEVICE: 351}  # the id `rce device start` names, by recipe


def started(recipe: str) -> str:
    return json.dumps({"id": STARTED[recipe], "status": "running", "run": {"id": 9000}})


def test_pipeline_recipes_use_only_commands_and_flags_rce_has(rce):
    calls = [COMMAND.search(line) for line in pipeline_section().splitlines()]
    calls = [call for call in calls if call]
    assert calls, "the recipe calls no rce command"

    for call in calls:
        help_ = rce.run(*call.group(1).split(), "--help")
        assert help_.returncode == 0, f"rce{call.group(1)}: {help_.stderr}"
        for flag in re.findall(r"(?<!\S)--[a-z][\w-]*", call.group(2)):
            assert re.search(rf"{flag}\b", help_.stdout), f"rce{call.group(1)} has no {flag}"


@pytest.mark.parametrize("recipe", RECIPES)
def test_the_recipe_runs_its_steps_with_pipefail(recipe):
    """GitHub runs a step with `bash -e` unless the workflow says `shell: bash`, which adds
    `-o pipefail`. Without it the start step's `| tee` hides `rce`'s exit code: a refused
    start would record nothing and pass."""
    assert re.search(r"^defaults:\n  run:\n    shell: bash\b", workflow(recipe), re.M), (
        "the workflow must set `defaults: run: shell: bash`"
    )


@pytest.mark.parametrize("recipe", RECIPES)
def test_a_refused_start_is_recorded_and_still_fails_the_step(tmp_path, recipe):
    assert recipe_steps(recipe)[START].get("id"), "the start step has no id to read its output by"
    start = run_step(tmp_path, recipe, START, 4)
    assert start.code == 4
    assert start.outputs, "a refused start (exit 4) records nothing"


@pytest.mark.parametrize("recipe", RECIPES)
@pytest.mark.parametrize("exit_code", [1, 5])
def test_a_start_that_may_have_made_a_run_records_no_refusal(tmp_path, recipe, exit_code):
    start = run_step(tmp_path, recipe, START, exit_code)
    assert start.code == exit_code
    assert start.outputs == {}


def test_a_start_records_the_id_of_the_run_it_started(tmp_path):
    start = run_step(tmp_path, DEVICE, START, 0, started(DEVICE))
    assert start.code == 0
    assert start.outputs == {"run": "9000"}


@pytest.mark.parametrize("recipe", RECIPES)
def test_the_stop_step_stops_only_the_run_the_start_step_started(tmp_path, recipe):
    """Without --run, a Run that reached its cap followed by someone else's start would
    have that start's Run stopped by this job."""
    start = run_step(tmp_path, recipe, START, 0, started(recipe))
    stop = run_step(tmp_path, recipe, STOP, start_outputs=start.outputs)
    assert stop.code == 0
    assert stop.calls == [f"device stop {STARTED[recipe]} --run 9000 --json"]


@pytest.mark.parametrize("recipe", RECIPES)
@pytest.mark.parametrize("exit_code", [1, 5])
def test_the_stop_step_stops_nothing_after_a_start_that_named_no_run(tmp_path, recipe, exit_code):
    """A start that failed after RCE accepted it has stopped its Run itself, or said how to."""
    start = run_step(tmp_path, recipe, START, exit_code)
    stop = run_step(tmp_path, recipe, STOP, start_outputs=start.outputs)
    assert stop.code == 0
    assert stop.calls == []


@pytest.mark.parametrize("recipe", RECIPES)
def test_the_stop_step_runs_once_the_start_step_ran_unless_it_was_refused(tmp_path, recipe):
    """`always()` keeps the stop after a failed step or a cancelled job; it must still skip
    when the start step never ran (an earlier step failed: the Run there is someone else's)
    and when the start was refused. A step that never ran has outcome `skipped`, or none."""
    steps = recipe_steps(recipe)
    start_id = steps[START]["id"]
    [(key, value)] = run_step(tmp_path, recipe, START, 4).outputs.items()
    condition = steps[STOP].get("if", "")
    ran = f"""contains(fromJSON('["success", "failure", "cancelled"]'), steps.{start_id}.outcome)"""
    refused = f"steps.{start_id}.outputs.{key} != '{value}'"
    assert condition == f"always() && {ran} && {refused}", (
        f"the stop step must run only after a start step that ran and wasn't refused: if: {condition}"
    )
