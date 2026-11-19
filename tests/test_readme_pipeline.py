"""The README's pipeline recipe: every rce command and flag it uses is in rce's own help,
and its stop step stops only the Run this job started."""

from __future__ import annotations

import json
import os
import re
import subprocess

import pytest

from conftest import REPO

COMMAND = re.compile(r"(?<![\w/.-])rce((?: [a-z][\w-]*){1,2})([^|]*)")  # flags up to a pipe
START, STOP = "Start the Run", "Stop the Run"  # the recipe's step names


def pipeline_section() -> str:
    readme = (REPO / "README.md").read_text()
    section = re.search(r"^## Pipelines \(CI/CD\)\n(.*?)(?=^## )", readme, re.S | re.M)
    assert section, "README has no 'Pipelines (CI/CD)' section"
    return section.group(1).replace("\\\n", " ")


def recipe_steps() -> dict[str, dict[str, str]]:
    """The workflow's steps by name: each one's keys (`id`, `if`, `run`...), comments dropped."""
    workflow = re.search(r"```yaml\n(.*?)```", pipeline_section(), re.S)
    assert workflow, "the recipe has no yaml block"
    steps = {}
    for block in re.split(r"^ {6}- ", workflow.group(1).split("    steps:\n", 1)[1], flags=re.M)[1:]:
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


def run_step(
    tmp_path, name: str, exit_code: int, stdout: str = "", env: dict[str, str] | None = None
) -> tuple[int, dict[str, str], list[str]]:
    """Run one of the recipe's steps the way GitHub runs a step, with an `rce` that prints
    `stdout` and exits `exit_code`. Returns the step's exit code, the outputs it wrote and
    the arguments of each `rce` call."""
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    calls, printed = tmp_path / "rce_calls", tmp_path / "rce_stdout"
    calls.write_text("")
    printed.write_text(stdout)
    (bin_ / "rce").write_text(f'#!/bin/sh\necho "$*" >> {calls}\ncat {printed}\nexit {exit_code}\n')
    (bin_ / "rce").chmod(0o755)
    outputs = tmp_path / "github_output"
    outputs.write_text("")
    step = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", recipe_steps()[name]["run"]],
        env={
            **os.environ,
            "PATH": f"{bin_}:{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(outputs),
            "RCE_DEVICE": "351",
            **(env or {}),
        },
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    return (
        step.returncode,
        dict(line.split("=", 1) for line in outputs.read_text().splitlines()),
        calls.read_text().splitlines(),
    )


def run_start_step(tmp_path, exit_code: int, stdout: str = "") -> tuple[int, dict[str, str]]:
    code, outputs, _ = run_step(tmp_path, START, exit_code, stdout)
    return code, outputs


def run_stop_step(tmp_path, start_outputs: dict[str, str]) -> tuple[int, list[str]]:
    """Run the stop step with its `env:` filled from the start step's outputs, as GitHub does."""
    start_id = recipe_steps()[START]["id"]
    env = {
        variable: re.sub(
            rf"\$\{{\{{ steps\.{start_id}\.outputs\.(\w+) \}}\}}",
            lambda output: start_outputs.get(output[1], ""),
            value,
        )
        for variable, value in recipe_steps()[STOP].get("variables", {}).items()
    }
    code, _, calls = run_step(tmp_path, STOP, 0, env=env)
    return code, calls


STARTED = json.dumps({"id": 351, "status": "running", "run": {"id": 9000}})


def test_pipeline_recipe_uses_only_commands_and_flags_rce_has(rce):
    calls = [COMMAND.search(line) for line in pipeline_section().splitlines()]
    calls = [call for call in calls if call]
    assert calls, "the recipe calls no rce command"

    for call in calls:
        help_ = rce.run(*call.group(1).split(), "--help")
        assert help_.returncode == 0, f"rce{call.group(1)}: {help_.stderr}"
        for flag in re.findall(r"(?<!\S)--[a-z][\w-]*", call.group(2)):
            assert re.search(rf"{flag}\b", help_.stdout), f"rce{call.group(1)} has no {flag}"


def test_a_refused_start_is_recorded_and_still_fails_the_step(tmp_path):
    assert recipe_steps()[START].get("id"), "the start step has no id to read its output by"
    code, outputs = run_start_step(tmp_path, 4)
    assert code == 4
    assert outputs, "a refused start (exit 4) records nothing"


@pytest.mark.parametrize("exit_code", [1, 5])
def test_a_start_that_may_have_made_a_run_records_no_refusal(tmp_path, exit_code):
    code, outputs = run_start_step(tmp_path, exit_code)
    assert code == exit_code
    assert outputs == {}


def test_a_start_records_the_id_of_the_run_it_started(tmp_path):
    code, outputs = run_start_step(tmp_path, 0, STARTED)
    assert code == 0
    assert outputs == {"run": "9000"}


def test_the_stop_step_stops_only_the_run_the_start_step_started(tmp_path):
    """Without --run, a Run that reached its cap followed by someone else's start would
    have that start's Run stopped by this job."""
    _, outputs = run_start_step(tmp_path, 0, STARTED)
    code, calls = run_stop_step(tmp_path, outputs)
    assert code == 0
    assert calls == ["device stop 351 --run 9000 --json"]


@pytest.mark.parametrize("exit_code", [1, 5])
def test_the_stop_step_stops_nothing_after_a_start_that_named_no_run(tmp_path, exit_code):
    """A start that failed after RCE accepted it has stopped its Run itself, or said how to."""
    _, outputs = run_start_step(tmp_path, exit_code)
    code, calls = run_stop_step(tmp_path, outputs)
    assert code == 0
    assert calls == []


def test_the_stop_step_runs_once_the_start_step_ran_unless_it_was_refused(tmp_path):
    """`always()` keeps the stop after a failed step or a cancelled job; it must still skip
    when the start step never ran (an earlier step failed: the Run there is someone else's)
    and when the start was refused. A step that never ran has outcome `skipped`, or none."""
    steps = recipe_steps()
    start_id = steps[START]["id"]
    [(key, value)] = run_start_step(tmp_path, 4)[1].items()
    condition = steps[STOP].get("if", "")
    ran = f"""contains(fromJSON('["success", "failure", "cancelled"]'), steps.{start_id}.outcome)"""
    refused = f"steps.{start_id}.outputs.{key} != '{value}'"
    assert condition == f"always() && {ran} && {refused}", (
        f"the stop step must run only after a start step that ran and wasn't refused: if: {condition}"
    )
