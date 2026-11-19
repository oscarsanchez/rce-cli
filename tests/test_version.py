"""`rce --version`: say exactly which rce ran, with no token, config or network."""

from __future__ import annotations


def test_version_prints_the_version_without_a_token_or_rce(rce, fake_rce):
    result = rce.run("--version")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "rce 0.2.0\n"
    assert fake_rce.requests == []
