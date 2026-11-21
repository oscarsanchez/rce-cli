# Changelog

What changed in each release of `rce`. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/). Exit codes and `--json` shapes are a public contract: a change that breaks one starts with "Breaking:". Upgrade steps sit under the release that needs them.

## [Unreleased]

### Changed

- The Cursor setup and the Claude Code settings moved from the README to their own pages, [docs/how-to/cursor.md](docs/how-to/cursor.md) and [docs/how-to/claude-code-settings.md](docs/how-to/claude-code-settings.md), both listed in the README's new Docs list.

## [0.2.1] - 2026-11-19

### Fixed

- A Dev Password with a trailing newline now signs in. `v0.2.0`'s README set the `RCE_DEV_PASSWORD` secret by piping `rce device show <device> --dev-password` straight into `gh secret set`. That kept the newline `rce` ends the password with, `gh` stored it, and `rce` sent it as is, so every sideload and screenshot in the pipeline failed with "wrong or missing Dev Password … (401)". `rce` now drops trailing CR and LF characters from `RCE_DEV_PASSWORD`; any other character, a trailing space included, still counts as part of the Dev Password. A Dev Password stored by `rce device setup-dev` is used as stored.
- The README sets the secret without the newline: `printf %s "$(rce device show player --dev-password 2>&1 >/dev/null)" | gh secret set RCE_DEV_PASSWORD --repo <owner>/<repo>`, which works with every `rce` version and keeps the password off the command line.
- The pipeline recipes download `rce` at `v0.2.1`.

### Upgrading

If you set `RCE_DEV_PASSWORD` for a pipeline with `v0.2.0`'s README line, update `rce` (or set the secret again with today's line); nothing else changes. The Pool recipe (`RCE_DEV_PASSWORDS`) was never affected: it reads each Dev Password through `$(…)`, which drops the newline.

## [0.2.0] - 2026-11-19

### Added

- `rce device start --pool` claims a Free Cloud Device of the Pool. The Pool is the CI variable `RCE_POOL`, a JSON object from each Pool member's RCE id to its Dev Snapshot id. `rce` starts the Free Cloud Devices in random order, each from its Dev Snapshot, until RCE accepts one. That accepted start is the Claim, and RCE refuses a start on a Cloud Device that already has a Run, so two jobs never claim the same one. `--json` prints what `device start --json` prints, so `id` and `run.id` tell you which Cloud Device and which Run you got. With none free it exits 4 and starts nothing.
- `--wait-free S` waits for a Free Cloud Device instead of exiting 4. It looks again about every 15 s, for up to S seconds, then exits 5 with nothing started.
- `rce device stop <device> --run ID` stops the Cloud Device only while Run `ID` is its current Run. With another Run or none, it exits 4 with "Run ID already ended; nothing stopped" and sends no stop.
- `rce device list --pool` shows only the Pool members, in `RCE_POOL` order, with each one's Dev Snapshot state (ready, not ready, or missing, since RCE deletes a Snapshot unused for 180 days) and how many are free. It only reads.
- A GitHub Actions recipe for parallel jobs on a Pool: a matrix whose jobs each claim a Pool member, take that member's Dev Password from the `RCE_DEV_PASSWORDS` secret (masked before anything can print it), and stop their own Run with `--run`.
- Install steps for Cursor.
- Core API reads are retried on 502, 503 and 504.

### Changed

- The single-device pipeline recipe's stop step passes `--run`, so it stops only the Run its start step made; see Upgrading.
- A start answered with a gateway error (502, 503 or 504) is handled like a start that got no answer: `rce` never retries it, looks at the Cloud Device, stops any Run it finds there, and says whether the start happened.
- `rce` sends the RCE token only to RCE's own hosts. A Run address anywhere else exits 1, and nothing is sent.
- The skill's folder is now `skills/rce`, so Cursor names the skill `rce`. Claude Code still shows `rce-cli:rce`.

### Fixed

- `--no-wait` returns once RCE has given the Run an id, so its output names the Run. Before, it could fail while RCE still showed the Run as pending, with the Run billing.

### Upgrading

**Moving from the old install.** The old `install.sh` also linked the skill into `~/.claude/skills/rce`, and the old settings block added the Stop hook to `~/.claude/settings.json`. When you switch to the plugin, remove both, or Claude loads the skill twice and warns twice:

1. `rm ~/.claude/skills/rce` (removes only the link; the checkout stays).
2. In `~/.claude/settings.json`, delete the `Stop` hook entry whose command ends in `hooks/rce-stop-hook`. Keep the `permissions` block.

If you keep the CLI install too, pull and run `./install.sh` again: `rce` moved to `bin/rce`.

**Pipelines copied from `v0.1.0`.** The single-device recipe has three changes. Copy them into your workflow, and download `bin/rce` at `v0.2.0`, because `--run` doesn't exist in `v0.1.0`.

- The stop step passes `--run`. In `v0.1.0`, the stop step stopped whatever Run was on the Cloud Device. If your job's Run reached its cap and someone then started a new Run on that Cloud Device, your stop step would stop their Run. Now the start step records the Run it started (`run=$(jq .run.id start.json)`, on exit 0 only), and the stop step runs `rce device stop "$RCE_DEVICE" --run "$RCE_RUN" --json`. If no Run id was recorded, the stop step does nothing.
- The start step pipes `--json` through `tee` into `start.json`, so the step can read `run.id` from it.
- The job runs its steps with `shell: bash` (`defaults: run: shell: bash`). GitHub's default shell is `bash -e`, which has no `pipefail`, so `| tee` would hide a refused start's exit 4. With `shell: bash`, the step keeps `rce`'s exit code.

## [0.1.0] - 2026-11-19

### Changed

- `rce device show <device> --dev-password` prints the Dev Password on stderr bare and alone, so a pipe can take it into a CI secret. `rce device setup-dev --show-password` keeps its sentence.
- The skill: a console marker must be unique to its launch, since a new console connection first replays earlier lines; the console takes one client at a time; `query/app-ui` gives the SceneGraph tree; a screenshot during playback shows the video frame; and the VS Code BrightScript debugger reaches a Cloud Device natively (roku-debug 0.24+, BrightScript extension 3.0+).

## [0.1.0-rc.1] - 2026-11-18

### Added

- `rce`, a command-line client for Roku® Cloud Emulator, and a Claude Code plugin whose skill teaches Claude to use it. From any directory and any Roku project, it lists, starts and stops Cloud Devices, sideloads, reads the BrightScript console, sends ECP commands and remote keys, takes screenshots, forwards debugger ports, sets up developer mode with a Dev Snapshot, and creates and retires Cloud Devices. It needs only uv, on macOS or Linux, and your own RCE token.
- Three installs: the Claude Code plugin (the skill, the Stop hook that warns about a Run still billing, and `rce` on Claude's PATH), the terminal install (clone and `./install.sh`), and, for pipelines, the single `bin/rce` script downloaded at a release tag.

[Unreleased]: https://github.com/oscarsanchez/rce-cli/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/oscarsanchez/rce-cli/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/oscarsanchez/rce-cli/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/oscarsanchez/rce-cli/compare/v0.1.0-rc.1...v0.1.0
[0.1.0-rc.1]: https://github.com/oscarsanchez/rce-cli/releases/tag/v0.1.0-rc.1
