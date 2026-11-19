# rce

`rce` is a command-line client for Roku® Cloud Emulator (RCE), and a Claude Code plugin whose skill teaches Claude to use it. It's for Roku app developers who want to start and stop Cloud Devices, sideload, read the console, press keys and take screenshots from a terminal, a script, a pipeline or an agent. It works from any directory and any Roku project, and needs only [uv](https://docs.astral.sh/uv/) (no Node). Vocabulary: [GLOSSARY.md](GLOSSARY.md).

`rce-cli` is a client for Roku® Cloud Emulator, not affiliated with or endorsed by Roku, Inc. ROKU is a trademark and/or registered trademark of Roku, Inc. in the United States and other countries.

Issues are welcome on GitHub Issues; pull requests aren't accepted yet. To report a security problem, see [SECURITY.md](SECURITY.md). Licence: [MIT](LICENSE).

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

### Moving from the old install

The old `install.sh` also linked the skill into `~/.claude/skills/rce`, and the old settings block added the Stop hook to `~/.claude/settings.json`. When you switch to the plugin, remove both, or Claude loads the skill twice and warns twice:

1. `rm ~/.claude/skills/rce` (removes only the link; the checkout stays).
2. In `~/.claude/settings.json`, delete the `Stop` hook entry whose command ends in `hooks/rce-stop-hook`. Keep the `permissions` block.

If you keep the CLI install too, pull and run `./install.sh` again: `rce` moved to `bin/rce`.

## Getting started

```sh
pbpaste | rce token set               # or `rce token set` and paste at the hidden prompt
rce token status                      # who the token belongs to, expiry, trial minutes left
rce device list                       # your Cloud Devices and their RCE ids
rce device create player --type stb   # only if you have none: permanent, counts against the org quota
rce device alias 351 player           # or give one you already have a Device Name (glossary-ok)
rce device setup-dev player           # once per Cloud Device: developer mode and a Dev Snapshot
```

`setup-dev` runs in your terminal and pauses for the steps only you can do (linking your Roku account in the RCE web console, accepting the developer licence); see [Dev setup](#dev-setup). After it, every Run starts dev-ready. A typical day:

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

A Run costs $0.20 per hour, billed by the minute from the moment the start is requested, and RCE has no idle stop: it bills until you stop it or it reaches its cap (60 minutes by default). The trial gives 600 free minutes and allows one Run at a time across the organisation. Creating a Cloud Device is permanent: it counts against the organisation's quota for good. `rce device status` shows a Run's elapsed cost, and `rce usage` the minutes used. Details: [Runs](#runs).

## Token

`rce` shares its RCE token with `rk`. It uses the first of:

1. `RCE_TOKEN`
2. `RK_RCE_TOKEN`
3. the `token` key in rk's config file, `~/roku-rce-config.json` (mode 0600), as written by `rk device set-rce-token` or `rce token set`. `ROKU_RCE_CONFIG_PATH` moves that file, as it does for rk.

With no token it exits 2 and names every place it looked. `rce` never prints the token.

`rce` sends the token only to `https` (and `wss`) on `rce.roku.com` or a subdomain of it, at the default port, as rk does, or to the Core API's own origin (`RCE_API_URL`'s scheme, host and port). That covers every request that carries it: the Core API, each Run's Instance API, its port proxy (ECP, the installer) and its WebSockets (`console`, `forward`). A Run address the Core API gives anywhere else exits 1, "refusing to send the RCE token to <host>", with nothing sent (`forward` before it listens). A Run address without a scheme is read as `https`.

`rce token set` stores a token in rk's file, so `rce` and `rk` keep sharing it. It reads the token from a hidden prompt, or from stdin when piped (`pbpaste | rce token set`), never from an argument. It keeps any other keys rk stores in the file, creates the file if it is missing, and leaves it at mode 0600.

`rce token status` shows who the token belongs to (from the Core API, beside the owner id decoded locally from the token), when it expires (decoded locally from the token), and the trial minutes left. It warns on stderr when the token expires within 14 days, and exits 4 when the token has expired or RCE rejects it.

## Commands

| Command | What it does |
|---|---|
| `rce --version` | Print the version, e.g. `rce 0.2.0`. Needs no token, config or network. |
| `rce token set [--json]` | Store the RCE token in rk's file from a hidden prompt or stdin. `--json` prints `{"path": "<rk's file>"}`. |
| `rce token status [--json]` | The token's owner, organisation, expiry, and trial minutes left. |
| `rce device list [--running] [--pool] [--json]` | Your Cloud Devices: id, Device Name, RCE name, type, status, and the active Run if there is one. `--running` shows only Cloud Devices with a Run (pending or running). `--pool` shows only the Pool's members, in `RCE_POOL` order, each with its Dev Snapshot's state (ready, not ready or missing: RCE deletes a Snapshot unused for 180 days), and "<free> of <members> free", a Free Cloud Device being one with no Run, pending or running. It sends only reads, one device list and one Snapshot read per member. A malformed `RCE_POOL` exits 2, as does a Retired Cloud Device in it; an RCE id RCE doesn't know exits 3. See [`device list --json`](#device-list---json). |
| `rce device show <device> [--dev-password] [--json]` | One Cloud Device in detail. `--dev-password` also prints its stored Dev Password on stderr, bare and alone (never on stdout or in `--json`), so a CI secret can be set from it (see [Pipelines](#pipelines-cicd)); with none stored it exits 4. |
| `rce device alias <device> <name> [--force] [--json]` | Give a Cloud Device a Device Name. A Cloud Device has one Device Name, so naming it again renames it. A name that already names another Cloud Device exits 2 unless `--force` moves it. A Device Name can't be all digits. <!-- glossary-ok: spec command name --> |
| `rce device resolve <name> [--json]` | Print a Device Name's RCE id (`--json`: `{"id": 351, "type": "stb"}`). Reads only the per-user config, so it needs no token or network. |
| `rce device create <name> --type tv\|stb [--yes] [--json]` | Create a Cloud Device named `<name>` on RCE and give it that Device Name. It asks first, showing the Cloud Devices used out of the org's maximum, because a Cloud Device is permanent and can't be deleted. `--yes` skips the prompt; without a terminal and without `--yes` it refuses (exit 2). Prints the new id. |
| `rce device retire <device> [--yes] [--json]` | Retire a Cloud Device: rename it on RCE with a `retired/` prefix and drop its Device Name. It asks first unless `--yes` (no terminal means no, exit 2). Refuses a Cloud Device with a Run, pending or running (exit 4): stop it first. One already retired (its RCE name starts with `retired/`) exits 2 and is left as it is. |
| `rce device delete` | Not possible: RCE can't delete Cloud Devices. Exits 2 and points to `retire`. |
| `rce device start <device> [--snapshot ID] [--firmware ID] [--max-runtime S] [--no-wait] [--timeout S] [--wait-lock] [--json]` | Start a Run and wait until it takes input. See [Runs](#runs). |
| `rce device start --pool [--wait-free S] [--firmware ID] [--max-runtime S] [--no-wait] [--timeout S] [--json]` | Claim a Free Cloud Device of the Pool (`RCE_POOL`) by starting it, then go on as `device start` does, with the same output plus "Claimed Cloud Device <id> (Run <run id>)". With none free it exits 4 at once; `--wait-free S` looks again about every 15 s, for up to S seconds, then exits 5 with nothing started. No queue and no fairness. See [Claiming from a Pool](#claiming-from-a-pool). |
| `rce device stop <device> [--run ID] [--wait] [--timeout S] [--wait-lock] [--json]` | End the Run and say what it cost. `--run` stops it only while Run `ID` is the current one: with another Run or none it exits 4, "Run ID already ended; nothing stopped", and sends no stop. `--wait` waits until the Cloud Device has shut down (default timeout 120 s). Exits 4 if it isn't running. |
| `rce device status <device> [--json]` | The Cloud Device's state and, during a Run, its start time, cap, auto-stop time, elapsed time and elapsed cost. |
| `rce usage [--json]` | Trial minutes used and left, or, once subscribed, the minutes billed this month. |
| `rce key <device> <key>… [--delay MS] [--json]` | Press remote keys in order on a running Cloud Device. See [Using a running Cloud Device](#using-a-running-cloud-device). |
| `rce ecp <device> <path> [--method GET\|POST] [--json]` | Send any ECP command (`query/device-info`, `query/active-app`, `keypress/Home`, …) and print the device's answer. |
| `rce launch <device> [--param KEY=VALUE]… [--json]` | Launch the sideloaded dev app with launch params. |
| `rce sideload <device> <file> [--json]` | Install a zip or an RSG package (`.bin`) on a running Cloud Device and report the installer's real outcome. See [Sideload and screenshot](#sideload-and-screenshot). |
| `rce screenshot <device> -o FILE [--json]` | Save a screenshot (JPEG) of the foreground dev app to FILE. |
| `rce device setup-dev <device> [--restart] [--keep-running] [--show-password] [--yes] [--wait-lock] [--json]` | Take a fresh Cloud Device to a Dev Snapshot: developer mode with a generated Dev Password, "Control by mobile apps" enabled. It pauses where you must act and resumes where it stopped. See [Dev setup](#dev-setup). |
| `rce snapshot list <device> [--json]` | The Cloud Device's Snapshots: id, name, created date, ready, base, live, and which is its Dev Snapshot. |
| `rce snapshot take <device> --label NAME [--timeout S] [--yes] [--json]` | Take a Snapshot named NAME (3 to 255 characters) and wait until RCE has saved it (default timeout 600 s, then exit 5). It asks first unless `--yes` (no terminal means no, exit 2). At the Cloud Device's Snapshot limit it exits 4; `rce` doesn't delete Snapshots. With the Cloud Device off, RCE saves its latest state. See [Snapshots](#snapshots). <!-- glossary-ok: spec flag name --> |
| `rce snapshot use-as-dev <device> <id> [--yes] [--json]` | Make a ready Snapshot the Cloud Device's Dev Snapshot, which `device start` then uses by default. It asks first unless `--yes` (no terminal means no, exit 2). Exits 3 for a Snapshot the Cloud Device doesn't have, or a Cloud Device without a Device Name; 4 for a Snapshot that isn't ready. |
| `rce console <device> [--until REGEX] [--timeout S] [--strip-ansi] [--json]` | Stream the running Cloud Device's BrightScript console. See [Console](#console). |
| `rce forward <device> <port> [--local N] [--json]` | Forward a running Cloud Device's TCP port to `127.0.0.1`, for the BrightScript console and its debugger (with `nc`), the SceneGraph inspector and the TypeScript debugger. See [Forward](#forward). |

`<device>` is a Device Name or a raw RCE id, in every command that takes a Cloud Device.

Human-readable output by default; `--json` prints JSON on stdout for scripts. Errors go to stderr as `rce: <message>`.

### Device Names

Device Names live in one per-user config file shared by every project: `$XDG_CONFIG_HOME/roku-rce/devices.toml`, or `~/.config/roku-rce/devices.toml` when `XDG_CONFIG_HOME` is unset. `rce` creates it on first write, with mode 0600. Each Device Name is a table holding its Cloud Device's RCE id and type; anything else `rce` stores about that Cloud Device goes in the same table:

```toml
[devices.player]
id = 351
type = "stb"
dev_snapshot_id = 1001   # set by `rce snapshot use-as-dev` or `rce device setup-dev`
dev_password = "..."     # the installer's rokudev password, generated by `rce device setup-dev`

[devices.player.setup_dev]  # how far `rce device setup-dev` got, so a rerun resumes
done = ["account_link", "dev_mode"]
```

Projects resolve a Device Name with `rce device resolve <name>` rather than reading the file.

### `token status --json`

```json
{
  "source": "/Users/you/roku-rce-config.json",
  "owner": {"id": "6f1c2a52-...", "username": "dev@example.com", "full_name": "Dee Veloper", "email": "dev@example.com"},
  "token_owner_id": "6f1c2a52-...",
  "organisation": "Example Org",
  "expires_at": "2026-12-31T00:00:00Z",
  "days_left": 44,
  "plan_status": "trial",
  "trial_minutes_left": 555
}
```

`source` is `$RCE_TOKEN`, `$RK_RCE_TOKEN` or the path of rk's file. `owner` is the Core API's answer; `token_owner_id` is the token's own `sub` claim, decoded locally (`null` when the token carries none), and normally equals `owner.id`. `expires_at` and `days_left` are `null` when the token carries no expiry. `plan_status` is RCE's `trial` or `exhausted`; `trial_minutes_left` is `null` when the trial ended because of a subscription.

### `device list --json`

A list of:

```json
{
  "id": 351,
  "device_name": "player",
  "name": "Personal RCE Player",
  "type": "stb",
  "status": "running",
  "run": {
    "id": 9000,
    "created_at": "2026-11-16T21:00:00Z",
    "started_at": "2026-11-16T21:00:05Z",
    "running_at": "2026-11-16T21:01:11Z",
    "max_runtime": 3600,
    "snapshot_id": 998,
    "snapshot_name": "Live snapshot",
    "firmware_version_id": "395"
  }
}
```

`device_name` is the Cloud Device's Device Name, or `null` without one. `name` is its name on RCE. `type` is RCE's device type (`tv` or `stb`). `status` is `shutdown`, `pending` or `running`. `run` is `null` without an active Run. `run.created_at` is when the start was requested, which is when billing starts. RCE's WebRTC credentials for the Run are never included.

With `--pool`, each object also has its Dev Snapshot from `RCE_POOL` and its state: `"dev_snapshot": {"id": 2001, "status": "ready"}`, where `status` is `ready`, `not_ready` (RCE is still saving it) or `missing` (RCE no longer has it: take a new one with `rce device setup-dev` and put its id in `RCE_POOL`).

### `device show --json`

The `device list` object plus:

```json
{
  "created_at": "2026-11-11T17:02:11.123456Z",
  "serial_number": "XY0000000351",
  "last_snapshot_id": 997,
  "last_snapshot_name": "Initial snapshot"
}
```

### `device alias --json` <!-- glossary-ok: spec command name -->

```json
{"id": 351, "device_name": "player", "type": "stb"}
```

`device create --json` prints the same shape for the new Cloud Device.

### `device retire --json`

```json
{"id": 351, "name": "retired/Personal RCE Player"}
```

`name` is the Cloud Device's new name on RCE.

## Runs

A Run is billed by the minute from the moment the start is requested, and RCE has no idle stop, so every Run has a cap.

`rce device start` defaults to:

- a 3600 s cap (`--max-runtime`); RCE ends the Run on its own schedule a few minutes after the cap, and bills until then;
- the latest firmware RCE offers for the device type (`--firmware`, an id from RCE's firmware list);
- the Cloud Device's Dev Snapshot when one is recorded (`dev_snapshot_id` in its Device Name's table), else its latest live state (the Snapshot RCE marks `live`, saved at every stop), with a warning (`--snapshot`).

It refuses (exit 4) a Cloud Device that is already running. It then waits until the Run is `running` and takes remote input (about 80 s on RCE), and exits 5 after `--timeout` seconds (default 300). `--no-wait` doesn't wait for `running`: it returns as soon as RCE has given the Run an id (RCE answers the start before it shows the Run, so `rce` reads the Cloud Device until it does), and prints the same report. If no Run appears within `--timeout`, that is a failed wait like any other: `rce` stops the Run and exits 5. If the wait times out, fails or is interrupted, `rce` stops the Run so it doesn't keep billing. A failed wait never exits 4, even for a rejected token or a rate limit: RCE accepted the start, so this call made a Run. So does Ctrl-C before RCE answers the start, `--no-wait` or not; if that stop fails because the Cloud Device has no Run, it says the start didn't happen. A start request that gets no answer (it times out or loses its connection) exits 5 or 1, and one answered with a gateway error (502, 503 or 504) exits 1. Either way RCE may have made a Run, so `rce` never retries the start: it looks at the Cloud Device, stops any Run it finds there (or stops one anyway when it can't look), and says whether the start happened. It prints the hourly cost and the time the Run auto-stops.

When RCE refuses a start, `rce` says why in plain words and exits 4: the trial's one-Run limit (naming the Cloud Device that is running; `rce` never stops it for you), a used-up trial, a Snapshot that isn't ready, or a cap over the trial time left or over the organisation's maximum (its `max_project_runtime`, which the message names).

Cost is RCE's price, $0.00333333 per device-minute (AWS Marketplace), times the minutes since the start was requested.

Each Run has its own address, which `rce` always takes from the Core API's answer for that Run, never from a fixed host. Commands that need a Run exit 4 and say so when the Cloud Device isn't running.

### Claiming from a Pool

`rce device start --pool` lets parallel jobs each get a Cloud Device without assigning them. It reads the Pool from `RCE_POOL`, looks at the Cloud Devices once (one device list), shuffles the Free Cloud Devices among the members (those with no Run, pending or running), and starts each in turn from its own Dev Snapshot in `RCE_POOL`, with your `--firmware` and `--max-runtime`, until RCE accepts one. That accepted start is the Claim: RCE refuses a start on a Cloud Device that already has a Run, so two callers never claim the same one. There is no queue and no fairness. Each member is tried at most once per look.

- **Skipped, then the next member tried:** RCE's 409 "already running or locked" (another job claimed it after the look), a Snapshot that isn't ready (with a warning naming the Cloud Device), a member whose device lock another local `rce` holds, a start answered with a gateway error (502, 503 or 504) or with no answer at all, and a member whose Dev Snapshot RCE no longer has (both with a warning naming the Cloud Device). After a gateway error or no answer `rce` neither looks at that member nor stops anything there, since a Run on it may be another job's Claim; if RCE did make a Run all the same, it bills until its cap and keeps that member busy, so keep `--max-runtime` short.
- **Ctrl-C before RCE answers a start** exits 130 and stops nothing, for the same reason, with a warning that RCE may have made a Run that bills until its cap. Ctrl-C after the Claim still stops its Run.
- **The Claim stops at once, exit 4, nothing started:** a rejected token (401), a used-up trial, the trial's one-Run limit, or a cap over the trial time left or over the organisation's maximum, in the same plain words as `device start`, after one start request.
- **No member claimed:** exit 4, "no Free Cloud Device in the Pool (N members, none free)".
- **`--wait-free S`:** instead of exit 4, look again about every 15 s, plus a random 0 to 5 s so callers waiting together don't all look at once, and try the Free Cloud Devices again, until one is claimed or S seconds have passed since the call began; then exit 5 with nothing started. Each look says "<free> of <members> free, waiting…" on stderr; `--json` stdout is unchanged. A refusal that stops the Claim ends the wait at once with exit 4, and Ctrl-C while waiting exits 130 with nothing started. There is no queue and no fairness: whichever caller looks first after a member frees takes it, so a caller can wait its full S seconds while others claim.
- **After the Claim** it is `device start`: it waits unless `--no-wait`, and stops the Run if the wait fails, times out or is interrupted (exit 1, 5 or 130, never 4). It never tries a second member after RCE accepted a start, so one call makes at most one Run. `--json` prints what `device start --json` does, so `id` and `run.id` say what was claimed, with `--no-wait` too.
- **Exit 2 before anything is sent:** `--pool` with a `<device>`, `--snapshot` or `--wait-lock`, `device start` with neither a `<device>` nor `--pool`, `--wait-free` without `--pool` or with S not above 0, and a malformed `RCE_POOL`. After the look, a Retired Cloud Device in `RCE_POOL` exits 2 and an RCE id RCE doesn't know exits 3, before any start.

### Device lock

`device start` and `device stop` hold a lock on the Cloud Device while they run, so two callers (people, scripts or agents) never start or stop the same Cloud Device at once. The lock is a file under the per-user config directory, `roku-rce/locks/<id>.lock`, which records the owner: pid, command, the `RCE_LOCK_OWNER` value if set, and since when. A second start or stop on a locked Cloud Device fails at once with exit 4 naming the owner, or waits for it with `--wait-lock`. The OS releases the lock when its owner exits, so a lock left by a process that died is reclaimed by the next caller.

### `device start`, `stop` and `status --json`

The `device list` object plus:

```json
{
  "hourly_cost_usd": 0.2,
  "auto_stop_at": "2026-11-16T22:00:00Z",
  "elapsed_s": 754,
  "elapsed_cost_usd": 0.0419
}
```

`auto_stop_at`, `elapsed_s` and `elapsed_cost_usd` are `null` without a Run. For `stop`, `run` and the costs describe the Run that was stopped, and `status` is the Cloud Device's state after the stop request (`shutdown` with `--wait`).

### `usage --json`

```json
{
  "plan_status": "trial",
  "trial": {"mins_used": 45, "mins_limit": 600, "mins_left": 555},
  "billed": null
}
```

`plan_status` is RCE's `trial` or `exhausted`. Once subscribed, `trial` is `null` and `billed` is `{"start", "end", "minutes", "cost_usd"}` for this month so far.

## Using a running Cloud Device

These commands need a Run: they exit 4 when the Cloud Device isn't running (or is still starting). Each reaches the Run at the address the Core API gives for it.

- **`key`** uses the Run's Instance API input endpoint, which works before developer mode or ECP is set up. It first waits (up to 60 s) until the Run takes input, then presses each key in order, `--delay` milliseconds apart (default 0). Keys are RCE's names (Home, Select, Up, Down, Left, Right, Back, Play, Rev, Fwd, InstantReplay, Info, Search, Enter, Backspace, …) or `Lit_<character>` for a character, URL-encoded for you (`Lit_€`). A key the device reports it didn't take exits 4, and the keys after it are not sent.
- **`ecp`** sends an ECP command to port 8060 through the Run's HTTP port proxy and prints the device's answer (XML). The path may carry a query string, which passes through. Default method GET; ECP's commands that act (`keypress/…`, `launch/…`) need `--method POST`.
- **`launch`** POSTs ECP `launch/dev` with each `--param` as a URL-encoded query parameter.

ECP needs the Cloud Device's **Control by mobile apps** setting (Settings > System > Advanced system settings > Control by mobile apps > Network access) set to Permissive or Enabled. Its default, Limited, answers only `query/device-info` and `query/active-app`, and many commands also need developer mode. ECP's 403 exits 4 with that explanation and points to `rce device setup-dev <device>`. The device's own 404 (no such command, or no such app; `launch` with no dev app installed) exits 3.

### `key --json`

```json
{"id": 351, "device_name": "player", "keys": ["Home", "Down"]}
```

### `ecp --json`

For `query/device-info`, an object of every field the device reports, with `true`/`false` as booleans:

```json
{"model-name": "Roku Native", "software-version": "16.0.4", "developer-enabled": false, "ecp-setting-mode": "limited", "...": "..."}
```

For `query/active-app`, each element as `{"name": <text>, ...attributes}`; on the Home screen the app has only a name:

```json
{"app": {"name": "My Dev App", "id": "dev", "type": "appl", "version": "1.0.0"}}
```

Any other path gives the raw answer: `{"path": "<path as given>", "body": "<device's answer>"}`.

### `launch --json`

```json
{"id": 351, "device_name": "player", "params": {"contentId": "abc", "mediaType": "movie"}}
```

### Sideload and screenshot

Both use the device's dev web server (the installer, port 80) through the Run's HTTP port proxy. It signs in with Digest as `rokudev` and the Cloud Device's own Dev Password, taken from `RCE_DEV_PASSWORD` when it is set (for pipelines; it wins over a stored one and works for a Cloud Device addressed by id with no Device Name), else from `dev_password` in its Device Name's table in the per-user config (`rce device setup-dev` stores it). With neither they exit 4 and point to both `setup-dev` (after giving the Cloud Device a Device Name, if it has none) and `RCE_DEV_PASSWORD`. No command takes the Dev Password as a flag, so it never shows in process lists or CI logs. On port 80 the `Authorization` header carries the Digest, so the RCE token goes in `X-Authorization` and never reaches the device. `rce` prints the Dev Password only when you ask, on stderr: `rce device show <device> --dev-password` and `rce device setup-dev --show-password`.

The installer's own 401 (a Digest challenge) says "wrong or missing Dev Password for <device>" and exits 4. A 401 from RCE itself is a rejected token, as elsewhere.

- **`sideload`** posts the file as a multipart form (`mysubmit=Install`, `archive=<file>`) to `plugin_install`. The installer answers its page, 200 or (for a failed install) 400, so `rce` reads the page: installed and identical (the same package is already installed) exit 0; a failure exits 4 with the installer's reason, e.g. `Install Failure: Unzip failed. Invalid or corrupt zip archive.  Unloading.`
- **`screenshot`** asks `plugin_inspect` for a screenshot (`mysubmit=Screenshot`) and downloads the JPEG its page links to (`pkgs/dev.jpg`). The installer takes one only while a sideloaded dev app is in the foreground. `rce` retries for about 2 s, then says "no dev app in the foreground" and exits 4. A file it can't write exits 2.

#### `sideload --json`

```json
{"id": 351, "device_name": "player", "file": "build/app.zip", "outcome": "installed"}
```

`outcome` is `installed` or `identical`; a failure exits 4 with no JSON.

#### `screenshot --json`

```json
{"id": 351, "device_name": "player", "path": "/abs/path/shot.jpg", "bytes": 48213}
```

## Snapshots

A Snapshot is saved Cloud Device state that a Run starts from. RCE gives every Cloud Device a `base` Snapshot (its factory state) and a `live` one (its state, saved at every stop). The Dev Snapshot is the one `rce device start` uses by default: the Cloud Device's state after developer mode and the Dev Password are set. It is recorded as `dev_snapshot_id` with the Device Name in the per-user config, so it needs a Device Name. RCE deletes a Snapshot unused for 180 days, so a Dev Snapshot left unused that long is gone: take a new one with `rce device setup-dev`.

`snapshot take` and `snapshot use-as-dev` change saved device state, so they ask first; only `--yes` skips the prompt.

### `snapshot list --json`

A list of:

```json
{
  "id": 1001,
  "name": "dev-ready",
  "created_at": "2026-11-16T21:30:00Z",
  "ready": true,
  "base": false,
  "live": false,
  "dev_snapshot": true
}
```

`ready` is false while RCE is still saving it; a Run can't start from it until then. `dev_snapshot` marks the Dev Snapshot.

`snapshot take --json` prints the same object for the new Snapshot, once ready.

### `snapshot use-as-dev --json`

```json
{"id": 351, "device_name": "player", "dev_snapshot_id": 1001}
```

## Dev setup

`rce device setup-dev <device>` takes a fresh Cloud Device (it needs a Device Name) to a Dev Snapshot. It changes saved device state and starts a billed Run, so it asks first, showing the hourly cost; only `--yes` skips the question. Without a terminal and without `--yes` it starts nothing and exits 4, saying it needs a person at a terminal. The steps:

1. **Start** a Run from the Cloud Device's latest (`live`) state, capped at 60 minutes. A Run that is already going is used instead.
2. **Account link** (you): guided setup in the RCE web viewer, and activating the Cloud Device with your Roku account. Roku emails an activation link that you must open within 30 minutes.
3. **Developer mode**: `rce` generates a 16-character Dev Password and stores it with the Device Name (mode 0600), opens Developer Settings with RCE's developer-settings shortcut, and asks you to enable the installer and accept the licence in the viewer. When the password keyboard shows, `rce` types the password with remote keys; you select "Set password and reboot".
4. **Control by mobile apps** (you): Settings > System > Advanced system settings > Control by mobile apps > Network access, set to Permissive. Its choices are Enabled, Permissive, Disabled and Limited (the default); Enabled works too.
5. **Verify** with the Cloud Device's own `query/device-info`: not in guided setup, `developer-enabled` true, `ecp-setting-mode` not `limited` or `disabled`. A failure exits 4 and takes no Snapshot; the steps that failed are marked not done, so a rerun redoes them.
6. **Snapshot**: take one named `dev-ready` and wait until RCE has saved it.
7. **Dev Snapshot**: record it, so `rce device start` uses it.
8. **Stop** the Run it started. A Run that was already going when `setup-dev` began keeps going, with a warning that it is still billing.

Each step you do yourself prints exact instructions on stderr and waits for Enter, then checks `query/device-info` and asks again until the Cloud Device shows it done. A step the Cloud Device already shows done (say, it was linked earlier) is skipped. Without a terminal (and with `--yes`), `setup-dev` refuses at the first step that needs a person, saying so (exit 4).

Progress is recorded with the Device Name after each step. After Ctrl-C (exit 130) or a failure, `setup-dev` stops the Run it started, and a rerun resumes after the last completed step; it never generates a second Dev Password for the same Cloud Device. `--restart` starts over from step 1 (keeping the Dev Password, which the Cloud Device may already have); steps the Cloud Device shows done are still skipped. Once all steps are done, a rerun without `--restart` changes nothing.

- `--keep-running` leaves the Run going at the end, or after a failure or Ctrl-C.
- `--show-password` prints the Dev Password once on stderr, for you to type it yourself (rce then doesn't type it) or keep it. Apart from `rce device show <device> --dev-password`, the Dev Password appears in no other output, including `--json`.
- If developer mode is already on with a password `rce` didn't set (say, from the viewer's Dev Mode button), step 3 first asks you to select "Disable installer and restart", then enables it again with the generated password.

The Developer Settings screens can't be driven blind with keys, so a person navigates them; `rce` only opens them and types the password.

### `device setup-dev --json`

```json
{"id": 351, "device_name": "player", "dev_snapshot_id": 1001, "stopped_run": true}
```

`stopped_run` is whether `setup-dev` stopped a Run at step 8.

## Console

`rce console <device>` opens the Run's BrightScript console (device port 8085) through RCE's WebSocket TCP bridge and prints each line as it arrives, until interrupted. It only reads: the bridge takes binary frames only, and `console` sends none. Bytes are reassembled across frames before they are split into lines, so a line is never matched in halves.

- `--until REGEX` exits 0 after printing the first line the regex matches (Python `re.search`). Lines before it are printed too.
- `--timeout S` exits 5 after S seconds without a match (or, without `--until`, after S seconds of streaming). The default is no timeout.
- `--strip-ansi` removes ANSI colour codes before printing and matching.
- `--json` prints one JSON object per line: `{"line": "...", "matched": false}`, with `matched` true on the line that ended `--until`.

With dev mode off, RCE's gateway refuses the bridge (502/503 `upstream connect error`): `console` says "console unavailable: is dev mode on?" and exits 4. It exits 4 when the Cloud Device isn't running, or when its Run ends while streaming.

```sh
rce console player --until 'app ready' --timeout 120 --strip-ansi
```

## Forward

`rce forward <device> <port>` listens on `127.0.0.1:<port>` (or `--local N`) and bridges each TCP connection to the Run's WebSocket bridge for that device port, in both directions, as binary frames. Each connection gets its own bridge, several at once. It prints the address it listens on (`--json`: `{"id": 351, "device_name": "player", "port": 8085, "local": 8085}`) and keeps running until interrupted (exit 130).

| Port | What listens on the Cloud Device |
|---|---|
| 8080 | SceneGraph debug server (the SceneGraph inspector) |
| 8081, 8082 | BrightScript debugger: control and I/O |
| 8085 | BrightScript console |
| 8087 | Screensaver debug |
| 9999 | TypeScript debugger |

Ports 80 and 8060 are HTTP only on RCE, so `forward` refuses them (exit 2) and names the command to use (`sideload`, `ecp`); so is any port not in the table. A local port already in use exits 2: pick another with `--local`.

When RCE refuses a connection's bridge (502/503: nothing listens on that port, e.g. dev mode off), `forward` warns, hangs up that connection and keeps listening. When the Run ends, whether or not a connection is open, it says so and exits 4. It exits 4 at once when the Cloud Device isn't running.

```sh
rce forward player 8085 &
nc 127.0.0.1 8085
```

## Selftest

The offline tests are the pytest suite (see Development); `rce selftest` without `--live` says so and exits 2.

`rce selftest --live [--device NAME]` tests `rce` end to end on a real Cloud Device: the one named by `--device`, or the only Device Name in the per-user config. It needs a Dev Password (the one `rce device setup-dev` stores, or `RCE_DEV_PASSWORD`), and checks for it before spending anything. It shows the projected minutes and cost (about 5 min, at RCE's rate) and the Run's cap (10 min), then asks; `--yes` skips the question, and without a terminal it starts nothing (exit 2). It holds the device lock throughout (`--wait-lock` waits for it).

It reports `ok` or `FAIL` for each step, in order:

1. `start`: a Run from the Dev Snapshot, waiting until it takes input;
2. `device-info`: ECP `query/device-info`;
3. `sideload`: a tiny test app, generated at runtime, that shows a screen and prints a marker line unique to this selftest every second;
4. `launch`: the test app;
5. `console`: reads the console until the marker shows (60 s at most);
6. `screenshot`: of the test app;
7. `forward`: forwards the console port to a local port and reads the marker through a local TCP connection (60 s at most);
8. `stop`: ends the Run and waits for it to shut down, reporting its minutes and cost.

The first failing step ends the selftest; it then still stops the Run, and exits with that step's code. Ctrl-C stops the Run too (exit 130). A Cloud Device that is already running fails `start` and is left running: `rce` stops only the Run it started. `--json` prints `{"id": 351, "device_name": "player", "passed": true, "steps": [{"step": "start", "ok": true, "detail": "..."}, ...]}` at the end, also when a step fails.

The test app becomes the Cloud Device's dev app, replacing any other.

## Pipelines (CI/CD)

A pipeline can run your app on a Cloud Device: start a Run from the Dev Snapshot, sideload, wait for a console line, and always stop.

Dev setup is done once, by a person, from a terminal: `rce device setup-dev` pauses for steps only a person can do (see [Dev setup](#dev-setup)), so a pipeline can't do it. After it, put what the pipeline needs into its settings:

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
          curl -fsSL -o "$RUNNER_TEMP/bin/rce" https://raw.githubusercontent.com/oscarsanchez/rce-cli/v0.2.0/bin/rce
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

Pin `rce` to a release tag (`v0.2.0` above) and change the tag to upgrade. Replace `app ready` with a line your app prints when it is ready. Keep `shell: bash`: without it GitHub runs each step with `bash -e`, which has no `pipefail`, so the start step's `| tee` would hide a refused start's exit 4.

- **One Cloud Device per pipeline.** The `concurrency` group serialises this pipeline's jobs on its Cloud Device. The device lock can't do it: it only coordinates `rce` processes on one machine, and each job runs on its own runner. Give the pipeline its own Cloud Device and don't use it yourself: a start of yours is refused while the job's Run is on, and the job's start is refused while yours is.
- **The stop step stops only a Run this job may have started.** It runs once the start step has run (its `outcome` is `success`, `failure` or `cancelled`), even after a failed later step or a cancelled job, since `if: always()` keeps it. It skips when the start step never ran (an earlier step failed, or the job was cancelled first: its `outcome` is `skipped`), and when the start was refused: `rce device start` exits 4 only when RCE refused the start, or the Cloud Device was already running or locked, so that call made no Run; the Run on the Cloud Device, if any, is someone else's. The start step records that (`refused=true`). Any other way the start can fail may have made a Run, so the stop step runs then (see `--run` below for what it stops); a start step that is cancelled or killed records nothing.
- **`--run` keeps the stop to this job's Run.** The start step records the started Run's id (`run`), and the stop step passes it with `--run`: if the Cloud Device's current Run has another id, or there is none, `rce device stop --run` exits 4 with "Run <id> already ended; nothing stopped" and sends no stop. So when this job's Run reaches its cap and someone else then starts one, this job doesn't stop theirs. A start that fails after RCE accepted it records no id, and then the stop step does nothing, on purpose: `rce device start` stops the Run it made once, and if that stop fails it says how to stop it; `--max-runtime` bounds whatever is left; and a stop without `--run` would reopen the race `--run` closes, stopping a Run someone else started since. `--run` leaves a small race: `rce` reads the Cloud Device, then stops it, and RCE's stop takes no Run id, so a start by someone else between the two is stopped.
- **Only the newest waiting job runs.** GitHub keeps at most one running and one pending job per `concurrency` group: a newer push cancels the older pending job, while the running job finishes. Adding `cancel-in-progress: true` to the group also cancels the running job; its stop step still runs once its start step has run, since `if: always()` covers a cancelled job.
- **One Run at a time.** The trial allows one Run at a time across the organisation, so while a job's Run is going any other start, from another pipeline or from you at a terminal, is refused (exit 4).
- **A killed job bills until the cap.** If the runner dies before the stop step runs, the Run bills until its cap: 60 minutes by default, or `--max-runtime` (25 minutes above, a little over the job's `timeout-minutes`). `rce device list --running` shows a Run left on.

### Parallel jobs on a Pool

Jobs that run at the same time each claim a Free Cloud Device from a Pool (see [Claiming from a Pool](#claiming-from-a-pool)), so there is no `concurrency` group. A person sets up each member once, from a terminal, with `rce device setup-dev` (see [Dev setup](#dev-setup)). Then, in GitHub, under your organisation's Settings > Secrets and variables > Actions, add the variable `RCE_POOL` (each member's RCE id to its Dev Snapshot id, e.g. `{"375": 2001, "376": 2002}`, from `rce snapshot list <member>`) and the secrets `RCE_TOKEN` and `RCE_DEV_PASSWORDS`, a JSON object from each member's RCE id to its Dev Password, e.g. `{"375": "<its Dev Password>", "376": "<its Dev Password>"}`.

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
          curl -fsSL -o "$RUNNER_TEMP/bin/rce" https://raw.githubusercontent.com/oscarsanchez/rce-cli/v0.2.0/bin/rce
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

## Exit codes

| Code | Meaning |
|---|---|
| 0 | OK |
| 1 | Other error: RCE unreachable or a server error (5xx); also a `device start` refused after RCE accepted it (a rejected token or rate limit while waiting for the Run), since that call made a Run |
| 2 | Usage: bad arguments (including a port `forward` can't bridge, or a local port in use), no token configured, an unreadable per-user config, a Device Name already in use, a confirmation declined (or impossible without a terminal), or retiring a Cloud Device that is already retired; a malformed `RCE_POOL`, or a Retired Cloud Device in it; `device start --pool` with a `<device>`, `--snapshot` or `--wait-lock`, or `device start` with neither a `<device>` nor `--pool`; `--wait-free` without `--pool`, or with S not above 0 |
| 3 | Not found: device, Device Name or Snapshot (RCE's 404, or a 403 with no message, which means "not yours"); an ECP command or app the device doesn't have; an `RCE_POOL` member RCE doesn't know |
| 4 | Refused, and for `device start` (with or without `--pool`) always "this call made no Run": rejected token (401), trial limit or trial used up, already running, no Free Cloud Device in the Pool (without `--wait-free`; with it, those refusals end the wait at once), not running, Cloud Device locked by another `rce`, quota, Snapshot limit, Snapshot not ready, rate limit that persists, and other 4xx; also retiring a Cloud Device that has a Run, a console that is unavailable (dev mode off), ECP refused by "Control by mobile apps" (403), a key the device didn't take, a Run that ends under `console` or `forward`, a `device stop --run` whose Run already ended, a wrong or missing Dev Password, a failed install, a screenshot with no dev app in the foreground, a `setup-dev` with no terminal to ask at (before it starts anything, or at a step that needs a person), and a `setup-dev` that fails its verification |
| 5 | Timeout: RCE didn't answer, a Run or Snapshot wasn't ready (or a Run shut down) in time, `console --until` saw no match in time, or `device start --pool --wait-free S` claimed nothing in S seconds (nothing started; no fairness, so a caller may wait it out while others claim) |
| 130 | Interrupted (Ctrl-C). A Run that `device start` asked for or was waiting on, or that `device setup-dev` started, is stopped first. |

A gateway rate limit (429 marked `local_rate_limited`) is retried with backoff for any request; other 429s are retried only on reads. A passing gateway error (502, 503 or 504) on a Core API read, such as `device list`, `device status` or the waits inside `device start`, is retried the same way; one that persists exits 1. Writes are never retried on a 5xx, so one command never makes two Runs. Requests to a device's own ports (the installer, ECP) are never retried: the device's answer passes through as is, so it can't prove the request didn't reach the device.

## Environment

| Variable | Use |
|---|---|
| `RCE_TOKEN`, `RK_RCE_TOKEN` | Override the stored token (see above). |
| `ROKU_RCE_CONFIG_PATH` | rk's config file, where `rce` reads the token and `rce token set` writes it. Default `~/roku-rce-config.json`. |
| `RCE_API_URL` | Core API base URL. Default `https://api.rce.roku.com/api/v1`. Tests point it at the fake RCE. Where the token may go: see [Token](#token). |
| `RCE_POOL` | The Pool, for `device list --pool` and `device start --pool`: a JSON object from each member's RCE id to its Dev Snapshot id, e.g. `{"375": 2001, "376": 2002}`. Keys are RCE ids (all digits), never Device Names, since a runner has none. |
| `RCE_POOL_LOOK_SECONDS` | Test-only: the seconds between `--wait-free` looks (default 15, plus up to a third more at random), so the tests run fast. Not for pipelines. |
| `RCE_LOCK_OWNER` | A name recorded in the device lock, so a blocked caller sees who holds it (e.g. an agent's name). |
| `RCE_DEV_PASSWORD` | The Dev Password for every command that signs in to the installer (sideload, screenshot, selftest), for whichever Cloud Device it addresses; it wins over a stored one. For pipelines: set a CI secret from `rce device show <device> --dev-password` (see [Pipelines](#pipelines-cicd)). `rce` drops any trailing CR and LF characters (`\r`, `\n`) from it, which a secret set from a pipe, a file or a paste can keep; any other whitespace is part of the Dev Password. `setup-dev` ignores it and stores its own. |

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

## Development

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

### Tests (Seam A)

Tests run the real `rce` as a subprocess against a fake RCE and assert only on what a user sees: stdout, the exit code, files left behind and the requests the fake received.

- `tests/fake_rce.py`: the fake RCE, a local HTTP server serving the Core API under `/api/v1` and each Run's Instance API, including the WebSocket TCP bridges. Its answers are built from real RCE answers recorded in `tests/fixtures/recorded/` (its README lists what the fake still invents); re-record them with `scripts/record-live` (`--run` starts one billed Run). Add a route by appending to `FakeRCE.routes`; force an error or rate limit with `fail_next(...)`; inspect traffic with `requests` / `requests_to(...)`. `address_origin` puts a Run's address on another host, scheme or port (or none); with `rce.proxy_through(fake)` the fake is `rce`'s HTTP(S) proxy, so whatever `rce` sends toward any other host lands in `proxied` instead of leaving the machine. Script a bridge with `bridge(port)`: the frames it sends each client, `echo`, and the bytes it `received`; `dev_mode = False` makes bridges answer 503. The installer (port 80) checks `X-Authorization` and the Digest for `dev_password`, installs into `installed_archive` (the same bytes again are "identical"), answers installs with the recorded Install pages (a failure is a 400, served for the next install after a test sets `next_install_fails`), takes screenshots only while `active_app` is the dev app, and records each multipart form in `forms`. Launching the dev app sends each later console client (port 8085) the lines its BrightScript `print`s as string literals (`console_output`), as if it ran.
- `tests/conftest.py`: the `rce` fixture runs `rce` with a temp `HOME` and `XDG_CONFIG_HOME`, `RCE_API_URL` pointing at the fake, and the token stored in rk's config file.
