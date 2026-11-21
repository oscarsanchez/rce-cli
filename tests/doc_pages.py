"""The repo's markdown pages, read as text the way the doc tests read them."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from conftest import REPO

PIPELINES = REPO / "docs" / "how-to" / "pipelines.md"

FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")
HEADING = re.compile(r"^#{1,6}\s+(.*)$")


def prose(path: Path) -> Iterator[tuple[int, str]]:
    """The file's numbered lines outside fenced code blocks."""
    fenced = False
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            yield number, line
