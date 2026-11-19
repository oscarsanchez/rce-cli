"""Fail when `bin/rce` compares an HTTP status with 404.

Usage: lint_not_found.py [ROOT]   (default: this repo)

RCE answers "not found" with a 404 or a 403 with an empty detail (a start from a
Snapshot it doesn't have, a Cloud Device that isn't yours). `exit_code_for` holds that
rule once; everywhere else tests `error.code == NOT_FOUND`. The line that is the rule
carries `not-found-ok`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

COMPARISON = re.compile(
    r"status(_code)?\s*(==|!=)\s*404\b"
    r"|status(_code)?\s+(not\s+)?in\s*[(\[{][^)\]}]*\b404\b"
)


def main(root: Path) -> int:
    problems = 0
    path = root / "bin" / "rce"
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if COMPARISON.search(line) and "not-found-ok" not in line:
            print(
                f"bin/rce:{number}: compares a status with 404; "
                "use error.code == NOT_FOUND (a 404 or an empty 403)"
            )
            problems += 1
    return 1 if problems else 0


if __name__ == "__main__":
    default_root = Path(__file__).resolve().parent.parent
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else default_root))
