# rce-cli

CLI (`rce`) and Claude skill for using Roku Cloud Emulator from any Roku project: list, start, stop, sideload, console, ECP, screenshot, forward ports, set up dev mode, create and retire Cloud Devices. Vocabulary: `GLOSSARY.md`. Review rules: `CODING_STANDARDS.md`. Running or changing the check, lints or tests: `docs/development.md`. Before starting a Run or any billed RCE call: `docs/agents/live-rce.md`. Checking a new user's install at a tag: `docs/agents/fresh-install-check.md`.

## Agent skills

### Issue tracker

Issues and specs live as local markdown under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix), recorded as a `Status:` line. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `GLOSSARY.md`; decision records are local, in `.scratch/decisions/`. See `docs/agents/domain.md`.
