"""scripts/tty-drive runs a command on a pseudo-terminal, logs its output and feeds it
lines written to a FIFO, so an agent can answer a prompt the user has approved."""

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ASK = (
    "import sys\n"
    "print('tty' if sys.stdin.isatty() else 'no tty', flush=True)\n"
    "print('Go? [y/N] ', end='', flush=True)\n"
    "print('answer=' + input().strip(), flush=True)\n"
)


def wait_for(path: Path, text: str, timeout: float = 10) -> str:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists() and text in (log := path.read_text(errors="replace")):
            return log
        time.sleep(0.1)
    raise AssertionError(f"{text!r} not in {path}")


def test_the_command_sees_a_terminal_and_gets_the_answer_written_to_the_fifo(tmp_path):
    log, fifo = tmp_path / "out.log", tmp_path / "in.fifo"
    driver = subprocess.Popen(
        [sys.executable, str(REPO / "scripts" / "tty-drive"), str(log), str(fifo), "--",
         sys.executable, "-c", ASK],
    )
    try:
        wait_for(log, "[y/N]")
        fifo.write_text("y\n")
        assert driver.wait(timeout=10) == 0
    finally:
        driver.kill()

    out = log.read_text()
    assert out.startswith("tty") and "no tty" not in out
    assert "answer=y" in out
    assert "[tty-drive] exit status 0" in out
