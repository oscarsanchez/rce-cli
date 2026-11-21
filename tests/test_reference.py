"""The reference documents every subcommand `rce` has and every exit code it defines."""

from __future__ import annotations

import re

from conftest import RCE, REPO
from test_doc_links import HEADING, prose

REFERENCE = REPO / "docs" / "reference"
SUBCOMMAND = re.compile(r"^ {4}([a-z][\w-]*)", re.M)  # a `--help` entry; any second name follows in ()


def headings(page: str) -> list[str]:
    return [h[1].lower() for _, line in prose(REFERENCE / page) if (h := HEADING.match(line))]


def names(heading: str, command: str) -> bool:
    """The heading names every word of the command (`device stop` in "`device start`, `stop`…")."""
    return all(re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", heading) for word in command.split())


def test_every_subcommand_has_a_heading_on_the_commands_page(rce):
    commands = []
    for group in ("", "device", "snapshot"):
        result = rce.run(*group.split(), "--help")
        assert result.returncode == 0, result.stderr
        commands += [f"{group} {name}".strip() for name in SUBCOMMAND.findall(result.stdout)]

    on_page = headings("commands.md")
    missing = [c for c in commands if not any(names(h, c) for h in on_page)]

    assert {"device stop", "snapshot take", "selftest"} <= set(commands)
    assert not missing, f"no heading on docs/reference/commands.md for: {', '.join(missing)}"


def test_every_exit_code_rce_defines_has_a_row_on_the_exit_codes_page():
    block = re.search(r"^# Exit codes:.*?\n(.*?)\n\n", RCE.read_text(), re.S | re.M)
    assert block, "bin/rce has no '# Exit codes:' block"
    codes = re.findall(r"\b\d+\b", re.sub(r"#.*|^[^=]*=", "", block[1], flags=re.M))

    rows = re.findall(r"^\| (\d+) \|", (REFERENCE / "exit-codes.md").read_text(), re.M)
    missing = [code for code in codes if code not in rows]

    assert {"0", "4", "130"} <= set(codes)
    assert not missing, f"no row on docs/reference/exit-codes.md for exit codes: {', '.join(missing)}"
