"""Fail on any `_Avoid_` term from GLOSSARY.md used in the repo's code or docs.

Usage: lint_glossary.py [ROOT]   (default: this repo)

Terms match as whole words, case-sensitively, so product names like
"Roku Cloud Emulator" and "Instance API" pass. A line containing the marker
`glossary-ok` is skipped: use it for legitimate uses, such as RCE's own API
names. `_Avoid_:` lines are definitions and also pass. Skipped files:
GLOSSARY.md itself, .scratch/ (working notes) and the recorded RCE answers
(RCE's own words, in tests/fixtures/recorded/*.json).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

OPT_OUT = "glossary-ok"
AVOID = "_Avoid_:"
SKIPPED = ("GLOSSARY.md", ".scratch/")
RECORDED = re.compile(r"tests/fixtures/recorded/[^/]+\.json")


def avoided_terms(glossary: Path) -> list[str]:
    terms = []
    for line in glossary.read_text().splitlines():
        if line.startswith(AVOID):
            terms += [t.strip() for t in line.removeprefix(AVOID).split(",") if t.strip()]
    return terms


def repo_files(root: Path) -> list[str]:
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return [f for f in listed if not f.startswith(SKIPPED) and not RECORDED.fullmatch(f)]


def main(root: Path) -> int:
    terms = avoided_terms(root / "GLOSSARY.md")
    patterns = [(t, re.compile(rf"(?<!\w){re.escape(t)}(?!\w)")) for t in terms]
    problems = 0
    for name in repo_files(root):
        try:
            lines = (root / name).read_text().splitlines()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for number, line in enumerate(lines, 1):
            if OPT_OUT in line or AVOID in line:
                continue
            for term, pattern in patterns:
                if pattern.search(line):
                    print(f'{name}:{number}: "{term}" is an _Avoid_ term in GLOSSARY.md')
                    problems += 1
    if problems:
        print(f"glossary lint: {problems} problem(s); use the glossary term or mark the line {OPT_OUT}")
    return 1 if problems else 0


if __name__ == "__main__":
    default_root = Path(__file__).resolve().parent.parent
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else default_root))
