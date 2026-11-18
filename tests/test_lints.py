"""The check command's two lints, run on a throwaway repo."""

import subprocess
import sys

from conftest import REPO

GLOSSARY = """\
**Run**:
One start-to-stop period of a Cloud Device.
_Avoid_: session, boot

**Snapshot**:
Saved Cloud Device state.
_Avoid_: base image, backup
"""


def lint(name: str, root) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / name), str(root)],
        capture_output=True, text=True,
    )


def repo_with(tmp_path, files: dict[str, str]):
    for path, text in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def test_glossary_lint_flags_avoided_terms_in_code_and_docs(tmp_path):
    root = repo_with(tmp_path, {
        "GLOSSARY.md": GLOSSARY,
        "README.md": "Start a new session.\n",  # glossary-ok
        "tool.py": "# keep the base image\n",  # glossary-ok
    })

    result = lint("lint_glossary.py", root)

    assert result.returncode == 1
    assert 'README.md:1: "session"' in result.stdout  # glossary-ok
    assert 'tool.py:1: "base image"' in result.stdout  # glossary-ok


def test_glossary_lint_reads_our_docs_beside_the_recorded_answers(tmp_path):
    root = repo_with(tmp_path, {
        "GLOSSARY.md": GLOSSARY,
        "tests/fixtures/recorded/README.md": "Recorded in one session.\n",  # glossary-ok
    })

    result = lint("lint_glossary.py", root)

    assert result.returncode == 1
    assert 'recorded/README.md:1: "session"' in result.stdout  # glossary-ok


def test_glossary_lint_passes_clean_files_opt_outs_and_unrelated_words(tmp_path):
    root = repo_with(tmp_path, {
        "GLOSSARY.md": GLOSSARY,
        "README.md": "Start a Run. Sessions and reboot are other words.\n",
        "tool.py": "requests.Session()  # a Session is fine with a capital S\n",
        "notes.md": "RCE calls it a session here. <!-- glossary-ok -->\n",  # glossary-ok
        ".scratch/research.md": "an old session note\n",  # glossary-ok
        "tests/fixtures/recorded/answer.json": '{"body": "RCE says session"}\n',  # glossary-ok
    })

    result = lint("lint_glossary.py", root)

    assert result.returncode == 0, result.stdout


def test_test_import_lint_flags_tests_that_import_rce_internals(tmp_path):
    root = repo_with(tmp_path, {
        "tests/test_a.py": "import rce\n",
        "tests/test_b.py": "import importlib.util\n",
        "tests/test_c.py": "from runpy import run_path\n",
    })

    result = lint("lint_test_imports.py", root)

    assert result.returncode == 1
    for line in ("test_a.py:1", "test_b.py:1", "test_c.py:1"):
        assert line in result.stdout


def test_test_import_lint_passes_subprocess_tests(tmp_path):
    root = repo_with(tmp_path, {
        "tests/test_ok.py": "import subprocess\nfrom fake_rce import FakeRCE\n",
    })

    result = lint("lint_test_imports.py", root)

    assert result.returncode == 0, result.stdout
