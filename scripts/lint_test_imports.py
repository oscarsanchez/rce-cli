"""Fail when a test imports `rce` internals instead of running it as a subprocess.

Usage: lint_test_imports.py [ROOT]   (default: this repo)

`rce` has no .py suffix, so loading it in-process takes `import rce` (if someone
adds rce.py) or a loader from importlib, runpy or imp. Tests may use none of them.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

BANNED = {"rce", "importlib", "runpy", "imp"}


def imported_modules(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                yield node.lineno, imported.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.lineno, node.module
        elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "__import__":
            yield node.lineno, "__import__"


def main(root: Path) -> int:
    problems = 0
    for path in sorted((root / "tests").rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for line, module in imported_modules(tree):
            if module.split(".")[0] in BANNED | {"__import__"}:
                print(
                    f"{path.relative_to(root)}:{line}: imports {module}; "
                    "tests must run rce as a subprocess (Seam A)"
                )
                problems += 1
    return 1 if problems else 0


if __name__ == "__main__":
    default_root = Path(__file__).resolve().parent.parent
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else default_root))
