"""Every relative link and `#anchor` in the tracked markdown resolves, as GitHub renders it."""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from conftest import REPO

FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")
LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*)$")
EXTERNAL = re.compile(r"^(https?:|mailto:)")


def prose(path: Path) -> Iterator[tuple[int, str]]:
    """The file's numbered lines outside fenced code blocks."""
    fenced = False
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            yield number, line


def anchors(path: Path) -> set[str]:
    """GitHub's heading slugs: lowercase, punctuation dropped, spaces to `-`, `-1` on a repeat."""
    seen, slugs = Counter(), set()
    for _, line in prose(path):
        if heading := HEADING.match(line):
            text = re.sub(r"<!--.*?-->", "", heading[1]).strip().lower()
            slug = re.sub(r"[^\w\- ]", "", text).replace(" ", "-")
            slugs.add(f"{slug}-{seen[slug]}" if seen[slug] else slug)
            seen[slug] += 1
    return slugs


def broken_links(root: Path, files: list[str]) -> list[str]:
    """`file:line: target` for each relative link whose file or anchor doesn't resolve.
    A symlinked file is checked once, at its target, with links read from there."""
    root, checked, broken = root.resolve(), set(), []
    for name in files:
        path = (root / name).resolve()
        if path in checked:
            continue
        checked.add(path)
        for number, line in prose(path):
            for target in LINK.findall(INLINE_CODE.sub("", line)):
                if EXTERNAL.match(target):
                    continue
                file, _, anchor = target.partition("#")
                linked = (path.parent / file).resolve() if file else path
                if not linked.exists() or anchor and anchor not in anchors(linked):
                    broken.append(f"{path.relative_to(root)}:{number}: {target}")
    return broken


def test_tracked_markdown_has_no_broken_links():
    files = subprocess.run(
        ["git", "ls-files", "--", "*.md", ":!:.scratch/*"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.split()

    broken = broken_links(REPO, files)
    assert not broken, "broken links:\n" + "\n".join(broken)


def test_broken_files_and_anchors_are_named_by_file_and_line(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Pipelines (CI/CD)\n"
        "## Setup\n"
        "## Setup\n"
        "[here](#pipelines-cicd) [second](#setup-1) [up](../README.md#top)\n"
    )
    (tmp_path / "README.md").write_text(
        "# Top\n"
        "[guide](docs/guide.md#setup-1) [web](https://example.com/gone.md) [mail](mailto:a@b.c)\n"
        "[gone](docs/missing.md)\n"
        "[bad anchor](docs/guide.md#nope)\n"
        "```\n"
        "[in code](nowhere.md)\n"
        "# not a heading\n"
        "```\n"
        "[fenced heading](#not-a-heading) `[inline code](nowhere.md)`\n"
    )
    (tmp_path / "skill").mkdir()
    (tmp_path / "skill" / "README.md").symlink_to("../README.md")
    (tmp_path / "skill" / "SKILL.md").write_text("# Skill\n[ref](README.md#top)\n[ref](README.md#gone)\n")

    broken = broken_links(tmp_path, ["README.md", "docs/guide.md", "skill/README.md", "skill/SKILL.md"])

    assert broken == [
        "README.md:3: docs/missing.md",
        "README.md:4: docs/guide.md#nope",
        "README.md:9: #not-a-heading",
        "skill/SKILL.md:3: README.md#gone",
    ]
