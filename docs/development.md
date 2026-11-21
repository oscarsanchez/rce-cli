# Development

```sh
git config core.hooksPath .githooks   # once per clone: run the check before every commit
scripts/check                          # the one check: the lints + the test suite
```

`scripts/check` runs:

- **glossary lint** (`scripts/lint_glossary.py`): fails on any `_Avoid_` term from GLOSSARY.md in code or docs. Matching is whole-word and case-sensitive. For a legitimate use, such as an RCE API path, put `glossary-ok` on the line (`<!-- glossary-ok -->` in Markdown). `.scratch/` is not linted.
- **test-import lint** (`scripts/lint_test_imports.py`): fails when a test imports `rce` (or uses importlib, runpy or imp to load it) instead of running it as a subprocess.
- **not-found lint** (`scripts/lint_not_found.py`): fails when `bin/rce` compares a status with 404. RCE answers "not found" with a 404 or an empty 403, a rule `exit_code_for` holds once; code tests `error.code == NOT_FOUND`. A line that must compare (the rule itself, a device's own ECP 404) carries `not-found-ok`.
- **private lint** (`scripts/lint_private.py`): fails when a term listed in `.private-terms` (gitignored, one per line, `#` for comments) appears in a file git would publish. List there the ids of your own Cloud Devices and Snapshots, so examples in code and docs use invented ones. Without the file (CI, a fresh clone) it passes.
- **tests** (`uv run pytest -n auto`, in parallel with pytest-xdist; about 30 s). The harness drops `GIT_*` variables, so a test that runs git never touches the repo it is run from.

`core.hooksPath` is relative and shared by every worktree, so each worktree runs its own branch's `.githooks/pre-commit`. A change to the hook reaches a worktree only once that branch merges it.

## Tests (Seam A)

Tests run the real `rce` as a subprocess against a fake RCE and assert only on what a user sees: stdout, the exit code, files left behind and the requests the fake received.

- `tests/fake_rce.py`: the fake RCE, a local HTTP server serving the Core API under `/api/v1` and each Run's Instance API, including the WebSocket TCP bridges. Its answers are built from real RCE answers recorded in `tests/fixtures/recorded/` (its README lists what the fake still invents); re-record them with `scripts/record-live` (`--run` starts one billed Run). Add a route by appending to `FakeRCE.routes`; force an error or rate limit with `fail_next(...)`; inspect traffic with `requests` / `requests_to(...)`. `address_origin` puts a Run's address on another host, scheme or port (or none); with `rce.proxy_through(fake)` the fake is `rce`'s HTTP(S) proxy, so whatever `rce` sends toward any other host lands in `proxied` instead of leaving the machine. Script a bridge with `bridge(port)`: the frames it sends each client, `echo`, and the bytes it `received`; `dev_mode = False` makes bridges answer 503. The installer (port 80) checks `X-Authorization` and the Digest for `dev_password`, installs into `installed_archive` (the same bytes again are "identical"), answers installs with the recorded Install pages (a failure is a 400, served for the next install after a test sets `next_install_fails`), takes screenshots only while `active_app` is the dev app, and records each multipart form in `forms`. Launching the dev app sends each later console client (port 8085) the lines its BrightScript `print`s as string literals (`console_output`), as if it ran.
- `tests/doc_pages.py`: what the doc tests share: `prose` (a markdown file's lines outside fenced code), the heading and inline-code patterns, and the pipelines page's path.
- `tests/conftest.py`: the `rce` fixture runs `rce` with a temp `HOME` and `XDG_CONFIG_HOME`, `RCE_API_URL` pointing at the fake, and the token stored in rk's config file.
