# Command reference

What each command does and the JSON its `--json` prints. Every flag: `rce <command> --help`. Exit codes: [exit-codes.md](exit-codes.md). Environment variables: [environment.md](environment.md).

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
| `rce --version` | Print the version, e.g. `rce 0.2.2`. Needs no token, config or network. |
| `rce token set [--json]` | Store the RCE token in rk's file from a hidden prompt or stdin. `--json` prints `{"path": "<rk's file>"}`. |
| `rce token status [--json]` | The token's owner, organisation, expiry, and trial minutes left. |
| `rce device list [--running] [--pool] [--json]` | Your Cloud Devices: id, Device Name, RCE name, type, status, and the active Run if there is one. `--running` shows only Cloud Devices with a Run (pending or running). `--pool` shows only the Pool's members, in `RCE_POOL` order, each with its Dev Snapshot's state (ready, not ready or missing: RCE deletes a Snapshot unused for 180 days), and "<free> of <members> free", a Free Cloud Device being one with no Run, pending or running. It sends only reads, one device list and one Snapshot read per member. A malformed `RCE_POOL` exits 2, as does a Retired Cloud Device in it; an RCE id RCE doesn't know exits 3. See [`device list --json`](#device-list---json). |
| `rce device show <device> [--dev-password] [--json]` | One Cloud Device in detail. `--dev-password` also prints its stored Dev Password on stderr, bare and alone (never on stdout or in `--json`), so a CI secret can be set from it (see [Pipelines](../how-to/pipelines.md)); with none stored it exits 4. |
| `rce device alias <device> <name> [--force] [--json]` | Give a Cloud Device a Device Name. A Cloud Device has one Device Name, so naming it again renames it. A name that already names another Cloud Device exits 2 unless `--force` moves it. A Device Name can't be all digits. <!-- glossary-ok: spec command name --> |
| `rce device resolve <name> [--json]` | Print a Device Name's RCE id. Reads only the per-user config, so it needs no token or network. See [`device resolve --json`](#device-resolve---json). |
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

### `device alias` and `create --json` <!-- glossary-ok: spec command name -->

```json
{"id": 351, "device_name": "player", "type": "stb"}
```

`device create --json` prints the same shape for the new Cloud Device.

### `device retire --json`

```json
{"id": 351, "name": "retired/Personal RCE Player"}
```

`name` is the Cloud Device's new name on RCE.

### `device resolve --json`

```json
{"id": 351, "type": "stb"}
```

### `device delete`

Not possible: RCE can't delete Cloud Devices. Exits 2 and points to `retire`.

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

### `snapshot list` and `take --json`

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

## `console`

`rce console <device>` opens the Run's BrightScript console (device port 8085) through RCE's WebSocket TCP bridge and prints each line as it arrives, until interrupted. It only reads: the bridge takes binary frames only, and `console` sends none. Bytes are reassembled across frames before they are split into lines, so a line is never matched in halves.

- `--until REGEX` exits 0 after printing the first line the regex matches (Python `re.search`). Lines before it are printed too.
- `--timeout S` exits 5 after S seconds without a match (or, without `--until`, after S seconds of streaming). The default is no timeout.
- `--strip-ansi` removes ANSI colour codes before printing and matching.
- `--json` prints one JSON object per line: `{"line": "...", "matched": false}`, with `matched` true on the line that ended `--until`.

With dev mode off, RCE's gateway refuses the bridge (502/503 `upstream connect error`): `console` says "console unavailable: is dev mode on?" and exits 4. It exits 4 when the Cloud Device isn't running, or when its Run ends while streaming.

```sh
rce console player --until 'app ready' --timeout 120 --strip-ansi
```

## `forward`

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

## `selftest`

The offline tests are the pytest suite (see [Development](../development.md)); `rce selftest` without `--live` says so and exits 2.

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
