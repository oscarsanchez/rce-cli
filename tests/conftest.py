"""Seam A harness: run the real `rce` as a subprocess against the fake RCE.

Every test gets a temp HOME and XDG_CONFIG_HOME, so `rce` reads and writes only
files under tmp_path, and RCE_API_URL points at a fresh FakeRCE.
"""

from __future__ import annotations

import json
import os
import pty
import re
import select
import signal
import subprocess
import time
import tomllib
from pathlib import Path

import pytest

from fake_rce import FakeRCE

REPO = Path(__file__).resolve().parent.parent
RCE = REPO / "bin" / "rce"
TOKEN = "eyJfake.rce-token.SECRET"

# `rce` runs through `uv run --script`; keep uv's real cache and Python installs
# so a temp HOME doesn't make every test re-resolve the environment.
_UV_DIRS = {
    "UV_CACHE_DIR": ["uv", "cache", "dir"],
    "UV_PYTHON_INSTALL_DIR": ["uv", "python", "dir"],
}
_UV_ENV = {
    var: subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    for var, cmd in _UV_DIRS.items()
}
_DROPPED = {"RCE_TOKEN", "RK_RCE_TOKEN", "ROKU_RCE_CONFIG_PATH", "VIRTUAL_ENV", "CLAUDE_PLUGIN_ROOT"}


@pytest.fixture(autouse=True)
def _no_outer_git_repo(monkeypatch):
    """Git exports GIT_DIR, GIT_INDEX_FILE etc. to hooks and IDE tasks. A test that runs
    git (say, `git init` in tmp_path) would then act on the outer repo: from a worktree's
    pre-commit hook it set the main repo's core.bare=true. Tests run git on their own repos."""
    for name in [n for n in os.environ if n.startswith("GIT_")]:
        monkeypatch.delenv(name)


class Rce:
    """The `rce` command as a user runs it, in an isolated home."""

    def __init__(self, tmp_path: Path, fake: FakeRCE):
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.cwd = tmp_path / "somewhere"
        self.cwd.mkdir()
        self.env = {k: v for k, v in os.environ.items() if k not in _DROPPED}
        self.env.update(_UV_ENV)
        self.env.update(
            HOME=str(self.home),
            XDG_CONFIG_HOME=str(self.home / ".config"),
            RCE_API_URL=fake.api_url,
        )

    @property
    def rk_config(self) -> Path:
        return self.home / "roku-rce-config.json"

    def write_rk_config(self, data: dict) -> None:
        self.rk_config.write_text(json.dumps(data))
        self.rk_config.chmod(0o600)

    @property
    def config(self) -> Path:
        """The per-user config holding Device Names."""
        return self.home / ".config" / "roku-rce" / "devices.toml"

    def read_config(self) -> dict:
        return tomllib.loads(self.config.read_text())

    def name_device(self, device: str, name: str, *flags: str) -> subprocess.CompletedProcess:
        """Give a Cloud Device a Device Name, as `rce device alias` does."""  # glossary-ok
        return self.run("device", "alias", device, name, *flags)  # glossary-ok

    def run(self, *args: str, input: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(RCE), *args],
            cwd=self.cwd,
            env=self.env,
            input=input,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def spawn(self, *args: str, **env: str) -> subprocess.Popen:
        """Start `rce` in the background, e.g. a second process holding a device lock."""
        return subprocess.Popen(
            [str(RCE), *args],
            cwd=self.cwd,
            env={**self.env, **env},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    @property
    def locks(self) -> Path:
        """Where `rce` keeps its per-Cloud-Device locks."""
        return self.home / ".config" / "roku-rce" / "locks"

    def run_tty(self, *args: str, answer: str) -> subprocess.CompletedProcess:
        """Run `rce` with a terminal on stdin, typing `answer` at its prompt.

        stdout and stderr stay pipes, so tests read them as with `run`.
        """
        terminal, stdin = pty.openpty()
        try:
            process = subprocess.Popen(
                [str(RCE), *args],
                cwd=self.cwd,
                env=self.env,
                stdin=stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            os.write(terminal, f"{answer}\n".encode())
            stdout, stderr = process.communicate(timeout=60)
        finally:
            os.close(stdin)
            os.close(terminal)
        return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)

    def interactive(self, *args: str) -> Terminal:
        """Start `rce` with a terminal on stdin, for a test to answer its pauses one by one."""
        terminal, stdin = pty.openpty()
        process = subprocess.Popen(
            [str(RCE), *args],
            cwd=self.cwd,
            env=self.env,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=True,  # its own process group, so Ctrl-C reaches uv and Python  # glossary-ok: Popen's name
        )
        os.close(stdin)
        return Terminal(process, terminal)

    def json(self, *args: str):
        result = self.run(*args, "--json")
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)


class Terminal:
    """A running `rce` that a test talks to like a person at a terminal."""

    def __init__(self, process: subprocess.Popen, terminal: int):
        self.process = process
        self.terminal = terminal
        self.stderr = b""  # everything `rce` wrote to stderr so far
        self._seen = 0  # where the next expect() starts looking

    def expect(self, pattern: str, timeout: float = 60) -> str:
        """Wait until stderr shows `pattern` (a regex) after the last match; the text up to it."""
        deadline = time.monotonic() + timeout
        regex = re.compile(pattern)
        while not (match := regex.search(self.stderr.decode(errors="replace"), self._seen)):
            remaining = deadline - time.monotonic()
            ready = select.select([self.process.stderr], [], [], max(0, remaining))[0]
            chunk = os.read(self.process.stderr.fileno(), 65536) if ready else b""
            if not chunk:
                self.process.kill()
                raise AssertionError(f"rce never wrote {pattern!r}; stderr:\n{self.stderr.decode()}")
            self.stderr += chunk
        text = self.stderr.decode(errors="replace")[self._seen : match.end()]
        self._seen = match.end()
        return text

    def answer(self, line: str = "") -> None:
        """Type a line at the terminal, e.g. Enter at a pause."""
        os.write(self.terminal, f"{line}\n".encode())

    def interrupt(self) -> None:
        """Ctrl-C, as the terminal sends it: SIGINT to the whole process group."""
        os.killpg(self.process.pid, signal.SIGINT)

    def finish(self, timeout: float = 60) -> subprocess.CompletedProcess:
        stdout, rest = self.process.communicate(timeout=timeout)
        os.close(self.terminal)
        self.stderr += rest
        return subprocess.CompletedProcess(
            self.process.args, self.process.returncode, stdout.decode(), self.stderr.decode()
        )


@pytest.fixture
def fake_rce():
    fake = FakeRCE(TOKEN)
    fake.start()
    yield fake
    fake.stop()


@pytest.fixture
def rce(tmp_path, fake_rce) -> Rce:
    """`rce` with the token stored in rk's config file, as after `rk device set-rce-token`."""
    cli = Rce(tmp_path, fake_rce)
    cli.write_rk_config({"token": TOKEN})
    return cli
