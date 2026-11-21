# rce

`rce` is a command-line client for Roku® Cloud Emulator (RCE), and a Claude Code plugin whose skill teaches Claude to use it. It's for Roku app developers who want to start and stop Cloud Devices, sideload, read the console, press keys and take screenshots from a terminal, a script, a pipeline or an agent. It works from any directory and any Roku project, and needs only [uv](https://docs.astral.sh/uv/) (no Node). Vocabulary: [GLOSSARY.md](GLOSSARY.md).

`rce-cli` is a client for Roku® Cloud Emulator, not affiliated with or endorsed by Roku, Inc. ROKU is a trademark and/or registered trademark of Roku, Inc. in the United States and other countries.

Issues are welcome on GitHub Issues; pull requests aren't accepted yet. To report a security problem, see [SECURITY.md](SECURITY.md). What changed in each release, and how to upgrade: [CHANGELOG.md](CHANGELOG.md). Licence: [MIT](LICENSE).

## Prerequisites

- macOS or Linux (WSL counts as Linux). Windows isn't supported.
- [uv](https://docs.astral.sh/uv/) on your PATH (`brew install uv`). `rce` is a single-file uv script: uv fetches Python and its dependencies on the first run and reuses them after.
- An RCE token: in the RCE web console, Tokens > Add token.

## Install

There are three installs, one for each way of using `rce`. Only the plugin adds anything to Claude Code (the skill and the Stop hook), so nothing runs twice. [Cursor](#cursor) uses the terminal install's `rce` and the plugin's skill.

### Claude Code: the plugin

```sh
claude plugin marketplace add oscarsanchez/rce-cli
claude plugin install rce-cli@rce-cli
```

The plugin gives Claude the `rce` skill, the Stop hook, and `rce` on the PATH of Claude's Bash tool. It can't add permission rules; for those, see [Claude Code settings](#claude-code-settings).

The plugin's `rce` is on Claude's PATH only, not your terminal's. The steps you run yourself at a terminal (`rce token set`, `rce device setup-dev`) need the CLI install below too. With both installed, your own PATH comes first, so Claude also runs the CLI install's `rce`.

### Terminal: clone and `install.sh`

```sh
git clone https://github.com/oscarsanchez/rce-cli.git
cd rce-cli
./install.sh
```

This links `bin/rce` into `~/.local/bin` (put that on your PATH), so `git pull` updates it. It installs only the CLI and creates nothing under `~/.claude`. Run it again whenever you like; it only refreshes the link, and it refuses (changing nothing) when `~/.local/bin/rce` exists and is not a link.

### Pipelines

A pipeline downloads the single `bin/rce` script at a release tag, with no clone and no install. See [Pipelines (CI/CD)](#pipelines-cicd).

### Cursor

Cursor's agent runs the terminal install's `rce`, so do that install first. The plugin's `rce` is not on Cursor's PATH.

Signed in to Cursor, its agent also loads skills from installed Claude Code plugins, so with the plugin installed it already has the `rce` skill: add nothing, or Cursor loads it twice. Without the plugin, or if Cursor doesn't list `rce` among its skills, link the skill from your clone:

```sh
mkdir -p ~/.cursor/skills
ln -sfn "$PWD/skills/rce" ~/.cursor/skills/rce    # from the rce-cli clone
```

Cursor doesn't run the plugin's Stop hook, so nothing warns you when its agent finishes with a Run still billing. Check with `rce device list --running`.

## Getting started

```sh
pbpaste | rce token set               # or `rce token set` and paste at the hidden prompt
rce token status                      # who the token belongs to, expiry, trial minutes left
rce device list                       # your Cloud Devices and their RCE ids
rce device create player --type stb   # only if you have none: permanent, counts against the org quota
rce device alias 351 player           # or give one you already have a Device Name (glossary-ok)
rce device setup-dev player           # once per Cloud Device: developer mode and a Dev Snapshot
```

`setup-dev` runs in your terminal and pauses for the steps only you can do (linking your Roku account in the RCE web console, accepting the developer licence); see [Dev setup](docs/reference/commands.md#dev-setup). After it, every Run starts dev-ready. A typical day:

```sh
rce device start player                                    # waits until it takes input
rce console player --until 'app ready' --timeout 120 &     # connect before launching
rce sideload player build/app.zip
rce launch player --param contentId=abc
rce screenshot player -o shot.jpg
rce device stop player                                     # billing ends here
rce device list --running                                  # check nothing is left on
```

To watch a Run live, open the Cloud Device in the RCE web console.

### Costs

A Run costs $0.20 per hour, billed by the minute from the moment the start is requested, and RCE has no idle stop: it bills until you stop it or it reaches its cap (60 minutes by default). The trial gives 600 free minutes and allows one Run at a time across the organisation. Creating a Cloud Device is permanent: it counts against the organisation's quota for good. `rce device status` shows a Run's elapsed cost, and `rce usage` the minutes used. Details: [Runs](docs/reference/commands.md#runs).

## Pipelines (CI/CD)

A pipeline can run your app on a Cloud Device: start a Run from the Dev Snapshot, sideload, wait for a console line, and always stop.

Dev setup is done once, by a person, from a terminal: `rce device setup-dev` pauses for steps only a person can do (see [Dev setup](docs/reference/commands.md#dev-setup)), so a pipeline can't do it. After it, put what the pipeline needs into its settings:

```sh
rce snapshot list player    # the Dev Snapshot's id: the row marked DEV
rce device show player      # the Cloud Device's RCE id
printf %s "$(rce device show player --dev-password 2>&1 >/dev/null)" | gh secret set RCE_DEV_PASSWORD --repo <owner>/<repo>
```

The last line sets the `RCE_DEV_PASSWORD` secret from stderr, which carries only the Dev Password, so it never shows on screen. `$(…)` drops the newline `rce` ends it with, which `gh secret set` would otherwise keep in the secret (`rce` v0.2.0 and earlier then get a 401 on sideload; later versions drop it themselves), and `printf`, a shell builtin, keeps it out of process lists. In GitHub, under Settings > Secrets and variables > Actions, also add the secret `RCE_TOKEN` (an RCE token), and the variables `RCE_DEVICE` (the RCE id) and `RCE_SNAPSHOT` (the Dev Snapshot's id). A runner has no per-user config, so it addresses the Cloud Device by RCE id and starts from the Dev Snapshot by id.

```yaml
name: roku

on:
  push:

concurrency:
  group: rce-${{ vars.RCE_DEVICE }}   # one job at a time on this Cloud Device

defaults:
  run:
    shell: bash   # adds pipefail, so `| tee` keeps rce's exit code

jobs:
  roku:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      RCE_TOKEN: ${{ secrets.RCE_TOKEN }}
      RCE_DEV_PASSWORD: ${{ secrets.RCE_DEV_PASSWORD }}
      RCE_DEVICE: ${{ vars.RCE_DEVICE }}
      RCE_SNAPSHOT: ${{ vars.RCE_SNAPSHOT }}
    steps:
      - uses: actions/checkout@v7.0.1
      - uses: astral-sh/setup-uv@v10.3.3
      - name: Install rce
        run: |
          mkdir -p "$RUNNER_TEMP/bin"
          curl -fsSL -o "$RUNNER_TEMP/bin/rce" https://raw.githubusercontent.com/oscarsanchez/rce-cli/v0.2.1/bin/rce
          chmod +x "$RUNNER_TEMP/bin/rce"
          echo "$RUNNER_TEMP/bin" >> "$GITHUB_PATH"
      - name: Build
        run: zip -r app.zip manifest source components images   # your build
      - name: Start the Run
        id: start
        run: |
          status=0
          rce device start "$RCE_DEVICE" --snapshot "$RCE_SNAPSHOT" --max-runtime 1500 --json | tee start.json || status=$?
          if [ "$status" -eq 4 ]; then echo "refused=true" >> "$GITHUB_OUTPUT"; fi   # no Run of ours to stop
          if [ "$status" -eq 0 ]; then echo "run=$(jq .run.id start.json)" >> "$GITHUB_OUTPUT"; fi   # the Run to stop
          exit "$status"
      - name: Sideload and wait for the app
        run: |
          rce console "$RCE_DEVICE" --until 'app ready' --timeout 120 --strip-ansi &
          console=$!
          rce sideload "$RCE_DEVICE" app.zip
          rce launch "$RCE_DEVICE"
          wait "$console"
      - name: Stop the Run
        if: always() && contains(fromJSON('["success", "failure", "cancelled"]'), steps.start.outcome) && steps.start.outputs.refused != 'true'
        env:
          RCE_RUN: ${{ steps.start.outputs.run }}
        run: |
          if [ -z "$RCE_RUN" ]; then exit 0; fi   # the start failed and dealt with any Run it made
          rce device stop "$RCE_DEVICE" --run "$RCE_RUN" --json
```

Pin `rce` to a release tag (`v0.2.1` above) and change the tag to upgrade. Replace `app ready` with a line your app prints when it is ready. Keep `shell: bash`: without it GitHub runs each step with `bash -e`, which has no `pipefail`, so the start step's `| tee` would hide a refused start's exit 4.

- **One Cloud Device per pipeline.** The `concurrency` group serialises this pipeline's jobs on its Cloud Device. The device lock can't do it: it only coordinates `rce` processes on one machine, and each job runs on its own runner. Give the pipeline its own Cloud Device and don't use it yourself: a start of yours is refused while the job's Run is on, and the job's start is refused while yours is.
- **The stop step stops only a Run this job may have started.** It runs once the start step has run (its `outcome` is `success`, `failure` or `cancelled`), even after a failed later step or a cancelled job, since `if: always()` keeps it. It skips when the start step never ran (an earlier step failed, or the job was cancelled first: its `outcome` is `skipped`), and when the start was refused: `rce device start` exits 4 only when RCE refused the start, or the Cloud Device was already running or locked, so that call made no Run; the Run on the Cloud Device, if any, is someone else's. The start step records that (`refused=true`). Any other way the start can fail may have made a Run, so the stop step runs then (see `--run` below for what it stops); a start step that is cancelled or killed records nothing.
- **`--run` keeps the stop to this job's Run.** The start step records the started Run's id (`run`), and the stop step passes it with `--run`: if the Cloud Device's current Run has another id, or there is none, `rce device stop --run` exits 4 with "Run <id> already ended; nothing stopped" and sends no stop. So when this job's Run reaches its cap and someone else then starts one, this job doesn't stop theirs. A start that fails after RCE accepted it records no id, and then the stop step does nothing, on purpose: `rce device start` stops the Run it made once, and if that stop fails it says how to stop it; `--max-runtime` bounds whatever is left; and a stop without `--run` would reopen the race `--run` closes, stopping a Run someone else started since. `--run` leaves a small race: `rce` reads the Cloud Device, then stops it, and RCE's stop takes no Run id, so a start by someone else between the two is stopped.
- **Only the newest waiting job runs.** GitHub keeps at most one running and one pending job per `concurrency` group: a newer push cancels the older pending job, while the running job finishes. Adding `cancel-in-progress: true` to the group also cancels the running job; its stop step still runs once its start step has run, since `if: always()` covers a cancelled job.
- **One Run at a time.** The trial allows one Run at a time across the organisation, so while a job's Run is going any other start, from another pipeline or from you at a terminal, is refused (exit 4).
- **A killed job bills until the cap.** If the runner dies before the stop step runs, the Run bills until its cap: 60 minutes by default, or `--max-runtime` (25 minutes above, a little over the job's `timeout-minutes`). `rce device list --running` shows a Run left on.

### Parallel jobs on a Pool

Jobs that run at the same time each claim a Free Cloud Device from a Pool (see [Claiming from a Pool](docs/reference/commands.md#claiming-from-a-pool)), so there is no `concurrency` group. A person sets up each member once, from a terminal, with `rce device setup-dev` (see [Dev setup](docs/reference/commands.md#dev-setup)). Then, in GitHub, under your organisation's Settings > Secrets and variables > Actions, add the variable `RCE_POOL` (each member's RCE id to its Dev Snapshot id, e.g. `{"375": 2001, "376": 2002}`, from `rce snapshot list <member>`) and the secrets `RCE_TOKEN` and `RCE_DEV_PASSWORDS`, a JSON object from each member's RCE id to its Dev Password, e.g. `{"375": "<its Dev Password>", "376": "<its Dev Password>"}`.

With `RCE_POOL` set in your terminal too, `rce device list --pool` shows each member, its Dev Snapshot's state and how many are free.

```yaml
name: roku

on:
  push:

defaults:
  run:
    shell: bash   # adds pipefail, so `| tee` keeps rce's exit code

jobs:
  roku:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    strategy:
      matrix:
        suite: [smoke, playback, settings]   # one job per suite, all at once
    env:
      RCE_TOKEN: ${{ secrets.RCE_TOKEN }}
      RCE_POOL: ${{ vars.RCE_POOL }}
    steps:
      - uses: actions/checkout@v7.0.1
      - uses: astral-sh/setup-uv@v10.3.3
      - name: Install rce
        run: |
          mkdir -p "$RUNNER_TEMP/bin"
          curl -fsSL -o "$RUNNER_TEMP/bin/rce" https://raw.githubusercontent.com/oscarsanchez/rce-cli/v0.2.1/bin/rce
          chmod +x "$RUNNER_TEMP/bin/rce"
          echo "$RUNNER_TEMP/bin" >> "$GITHUB_PATH"
      - name: Build
        run: zip -r app.zip manifest source components images   # your build
      - name: Start the Run
        id: start
        run: |
          status=0
          rce device start --pool --wait-free 300 --max-runtime 1500 --json | tee start.json || status=$?
          if [ "$status" -eq 4 ]; then echo "refused=true" >> "$GITHUB_OUTPUT"; fi   # no Run of ours to stop
          if [ "$status" -eq 0 ]; then
            echo "id=$(jq .id start.json)" >> "$GITHUB_OUTPUT"   # the claimed Cloud Device
            echo "run=$(jq .run.id start.json)" >> "$GITHUB_OUTPUT"   # the Run to stop
          fi
          exit "$status"
      - name: Take its Dev Password
        env:
          RCE_DEV_PASSWORDS: ${{ secrets.RCE_DEV_PASSWORDS }}
          RCE_ID: ${{ steps.start.outputs.id }}
        run: |
          password=$(jq -er --arg id "$RCE_ID" '.[$id]' <<< "$RCE_DEV_PASSWORDS")   # fails if it has none
          echo "::add-mask::$password"   # first, so no later output shows it
          echo "RCE_DEV_PASSWORD=$password" >> "$GITHUB_ENV"
      - name: Sideload and wait for the app
        env:
          RCE_ID: ${{ steps.start.outputs.id }}
        run: |
          rce console "$RCE_ID" --until 'app ready' --timeout 120 --strip-ansi &
          console=$!
          rce sideload "$RCE_ID" app.zip
          rce launch "$RCE_ID"
          wait "$console"
      - name: Stop the Run
        if: always() && contains(fromJSON('["success", "failure", "cancelled"]'), steps.start.outcome) && steps.start.outputs.refused != 'true'
        env:
          RCE_ID: ${{ steps.start.outputs.id }}
          RCE_RUN: ${{ steps.start.outputs.run }}
        run: |
          if [ -z "$RCE_RUN" ]; then exit 0; fi   # the start failed and dealt with any Run it made
          rce device stop "$RCE_ID" --run "$RCE_RUN" --json
```

The matrix starts its three jobs at once, and each claims its own member. The start, password and stop steps are what make it safe to copy:

- **The start step records the claimed Cloud Device and its Run.** As in the recipe above it records `refused=true` on exit 4 and still fails, and on success it records `id` and `run.id` from `--json`. Every later step addresses `$RCE_ID`, the Cloud Device this job claimed.
- **The password step masks before it exports.** GitHub masks a secret's whole value, not a value taken out of it, so the step picks the claimed member's Dev Password out of `RCE_DEV_PASSWORDS` with `jq`, runs `::add-mask::` on it first, and only then exports it as `RCE_DEV_PASSWORD` for the later steps. It never echoes the value. A member missing from the map fails the step, and the stop step still runs.
- **The stop step stops only this job's Run.** It has the same `always()` and refused-start guard as the recipe above, and passes the claimed `run.id` with `--run`: once this job's Run reaches its cap another job may claim the member, and `--run` leaves that Run alone, except in the small race between `rce`'s read and its stop (see the `--run` bullet above). With no `run.id` recorded it does nothing, for the reasons in that bullet.

What a Pool can and can't do:

- **No fairness.** There is no queue: whichever job looks first after a member frees takes it, so a job can wait its full `--wait-free` (300 s above, about every 15 s) while others claim, then fail with exit 5 with nothing started. The wait counts against `timeout-minutes`.
- **A killed job holds its member until the cap.** If the runner dies before the stop step, the Run bills and keeps that member busy until `--max-runtime`, so keep it just above `timeout-minutes` (25 minutes above, for a 20-minute job). `rce device list --pool` shows which members are free.
- **A start answered with a gateway error (502, 503 or 504), or not at all, may have made a Run.** `rce` skips that member and stops nothing there, since the Run on it may be another job's Claim; so does a job cancelled while its start awaits RCE's answer. If RCE did make a Run all the same, it bills and holds the member until its cap, as a killed job's does: another reason for a short `--max-runtime`.
- **RCE deletes a Snapshot unused for 180 days.** A member whose Dev Snapshot is gone is skipped with a warning, and `rce device list --pool` shows its Dev Snapshot as missing: run `rce device setup-dev` on it again and put the new Dev Snapshot's id in `RCE_POOL`.
- **A Pool runs in parallel only on a subscription.** The trial allows one Run at a time across the organisation, so a second job's Claim is refused (exit 4) while the first job's Run is on.
- **Each member needs a person's setup.** A new member needs `rce device setup-dev`, by a person at a terminal, then its RCE id and Dev Snapshot id in `RCE_POOL` and its Dev Password in `RCE_DEV_PASSWORDS`.
- **Static sharding needs no `--pool`.** With a fixed number of jobs, give job N Cloud Device N: the recipe above with `RCE_DEVICE` and `RCE_SNAPSHOT` taken from the matrix, and one `concurrency` group per Cloud Device (`rce-${{ matrix.device }}`). Nothing waits or claims, but a Cloud Device that is busy or broken fails its own job.

For a clean console on each pass, stop the Run and wait for it to shut down, then claim again:

```sh
rce device stop "$RCE_ID" --run "$RCE_RUN" --wait
rce device start --pool --wait-free 300 --max-runtime 1500 --json
```

The second Claim may land on another member, so take `id` and `run.id` from its output again, address the new `id` from then on (with its own Dev Password), and have the stop step stop the new Run.

## Claude Code settings

The plugin's `rce` skill teaches Claude the commands, the costs, and its rules: ask before create, retire, setup-dev, token set and Snapshot changes, and stop every Run it started. A plugin can't ship permission rules, so back those rules up by merging this into `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Bash(rce device list *)",
      "Bash(rce device show *)",
      "Bash(rce device status *)",
      "Bash(rce device resolve *)",
      "Bash(rce device start *)",
      "Bash(rce device stop *)",
      "Bash(rce usage *)",
      "Bash(rce console *)",
      "Bash(rce ecp *)",
      "Bash(rce key *)",
      "Bash(rce launch *)",
      "Bash(rce screenshot *)",
      "Bash(rce forward *)",
      "Bash(rce sideload *)",
      "Bash(rce snapshot list *)",
      "Bash(rce token status *)"
    ],
    "ask": [
      "Bash(rce device create *)",
      "Bash(rce device retire *)",
      "Bash(rce device setup-dev *)",
      "Bash(rce token set *)",
      "Bash(rce snapshot take *)",
      "Bash(rce snapshot use-as-dev *)",
      "Bash(rce selftest *)"
    ]
  }
}
```

- **Permissions**: the free and Run commands run without a prompt. Each allow rule names a full subcommand, so none covers a permanent one, and the `ask` rules always prompt for the permanent ones and for `selftest` (a billed Run): Claude Code checks `ask` before `allow`, so even a broad rule such as `Bash(rce *)` added later can't approve them. `device alias` and anything else unlisted prompt as usual. A trailing ` *` also matches the bare command (`rce usage`). <!-- glossary-ok: spec command name -->
- **Stop hook** (`hooks/rce-stop-hook`): the plugin registers it, so it needs nothing in your settings, and it runs the plugin's own `rce`, so it works without the CLI install. When Claude finishes a turn, it runs `rce device list --running --json` and, if any Cloud Device has a Run, shows a warning naming each one and how long it has billed (`RCE Run still billing: player (351) for 12 min. …`). It never blocks Claude. It stays silent when nothing is running, `rce` can't run, no token is configured, or RCE is unreachable, and gives up after 5 s.

## Docs

- [GLOSSARY.md](GLOSSARY.md): the words `rce` and these docs use
- [CHANGELOG.md](CHANGELOG.md): what changed in each release
- [SECURITY.md](SECURITY.md): reporting a vulnerability
- [Development](docs/development.md): the check, the lints and the tests
- [Command reference](docs/reference/commands.md): what each command does and its `--json` shape
- [Exit codes](docs/reference/exit-codes.md): each exit code and what it means
- [Environment](docs/reference/environment.md): the environment variables `rce` reads
