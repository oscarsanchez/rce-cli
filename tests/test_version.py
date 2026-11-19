"""`rce --version`: say exactly which rce ran, with no token, config or network."""

from __future__ import annotations

import re

from conftest import REPO


def test_version_prints_the_version_without_a_token_or_rce(rce, fake_rce):
    result = rce.run("--version")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "rce 0.2.1\n"
    assert fake_rce.requests == []


DOWNLOAD = re.compile(r"/rce-cli/(?:releases/download/)?v(\d+\.\d+\.\d+)/")  # a pipeline's `curl` of `bin/rce`
PIN = re.compile(r"Pin `rce` to a release tag \(`v(\d+\.\d+\.\d+)`")


def test_readme_pins_rce_to_the_version_it_prints(rce):
    readme = (REPO / "README.md").read_text()
    downloads, pins = DOWNLOAD.findall(readme), PIN.findall(readme)

    version = rce.run("--version").stdout.removeprefix("rce ").strip()

    assert len(downloads) >= 2, "expected both pipeline recipes to download bin/rce at a tag"
    assert len(pins) >= 1, "expected the README's 'Pin `rce` to a release tag' line"
    assert set(downloads + pins) == {version}
