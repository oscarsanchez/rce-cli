"""Fail when a private term appears in a file git would publish.

Usage: lint_private.py [ROOT]   (default: this repo)

The terms (ids of the maintainer's own Cloud Devices and Snapshots: not secret, but
examples use invented ids so readers don't copy real ones) are listed one per line in
`.private-terms` at the root, a gitignored file: listing them in a tracked file would
defeat it. A worktree has no copy, so without one at the root the lint reads the main
checkout's (the parent of `git rev-parse --git-common-dir`). Lines starting with `#` are
comments. With no such file anywhere (CI, a fresh clone) the lint passes. Matching is
whole-term: `4242` doesn't match `42420` or `142425`.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

TERMS_FILE = ".private-terms"


def main_checkout(root: Path) -> Path:
    common_dir = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return Path(common_dir).parent


def read_terms(root: Path) -> list[str]:
    path = root / TERMS_FILE
    if not path.exists():
        path = main_checkout(root) / TERMS_FILE
    if not path.exists():
        return []
    lines = (line.strip() for line in path.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def publishable_files(root: Path) -> list[str]:
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return [name for name in listed if name != TERMS_FILE]


def main(root: Path) -> int:
    terms = read_terms(root)
    if not terms:
        return 0
    pattern = re.compile(
        r"(?<![0-9A-Za-z])(" + "|".join(map(re.escape, terms)) + r")(?![0-9A-Za-z])"
    )
    problems = 0
    for name in publishable_files(root):
        try:
            text = (root / name).read_text()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                print(f"{name}:{number}: holds a term from {TERMS_FILE}; use an invented one")
                problems += 1
    return 1 if problems else 0


if __name__ == "__main__":
    default_root = Path(__file__).resolve().parent.parent
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else default_root))
