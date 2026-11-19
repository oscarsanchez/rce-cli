---
name: rce
description: Use for Roku Cloud Emulator (RCE) and Cloud Device work through the `rce` CLI - starting and stopping Runs, sideloading, console, ECP, keys, screenshots, forwarding debugger ports, Snapshots, usage and cost.
---

# rce: Roku Cloud Emulator from the terminal

`rce` drives RCE from any directory. Every flag: `rce <command> --help`. Every `--json` shape and the full behaviour of each command: [README.md](README.md).

## Money and permanence

A Run bills **$0.20 per hour**, by the minute, from the moment the start is requested. RCE has **no idle stop**: a Run bills until it is stopped or reaches its cap (default 60 min; RCE ends it a few minutes after the cap and bills until then). On the trial only **one Run** may exist at a time across the whole org, out of 600 free minutes (`rce usage`).

1. **Ask first** before `device create`, `device retire`, `device setup-dev`, `token set`, `snapshot take`, `snapshot use-as-dev` and `selftest --live`. A Cloud Device is permanent and counts against the org quota for good; the others change saved device state or the shared token, and `selftest --live` starts a billed Run and replaces the dev app.
2. **`--yes` only on the user's explicit OK** for that exact command. Without a terminal these commands refuse (exit 2; `setup-dev` exits 4) rather than prompt, so the usual path is to ask the user to run them in their own terminal. `setup-dev` (it pauses for the user's own steps) and `token set` (it reads the token from a hidden prompt) need a person at a terminal anyway: hand those to the user, and never handle the token yourself.
3. **Stop every Run you started** before you finish, failed task included: `rce device stop <device>`, then `rce device list --running` must not show it. A Run you didn't start is the user's: report it, leave it running, and never stop it to make room for yours.
4. **From a script**, run `rce device start` inside the `try` whose `finally` stops the Run, and on Ctrl-C wait for `rce` to exit: it stops a Run its `start` was waiting on. Killing it first (Python's `subprocess.run` does, 0.25 s after Ctrl-C) cuts that stop short and leaves the Run billing. Then confirm with `rce device status <device>`.

## Lifecycle

- **Cloud Device**: a virtual Roku player (`stb`) or TV (`tv`) on RCE. Permanent; RCE can't delete it, so `retire` renames it and drops its Device Name.
- **Device Name**: the local name for a Cloud Device. Every command takes a Device Name or a raw RCE id; `rce device list` shows both, `rce device resolve <name>` prints the id.
- **Run**: one start-to-stop period, with its own address. `rce device start <device>` waits until it takes input (about 80 s) and prints the cost and auto-stop time; `--max-runtime S` sets a shorter cap.
- **Snapshot**: saved state a Run starts from. RCE keeps `base` (factory) and `live` (saved at every stop).
- **Dev Snapshot**: the Snapshot `start` uses by default, taken after `setup-dev` turned on developer mode with a generated Dev Password and enabled "Control by mobile apps". `start` warns when a Cloud Device has none. Without it, only `key` works; `ecp`, `launch`, `sideload`, `screenshot`, `console` and `forward` need it.

To watch a Run live, open the Cloud Device in the RCE web console.

## Commands

Free (no Run, no cost): `device list [--running]`, `device show`, `device status` (elapsed time and cost during a Run), `device resolve`, `usage`, `snapshot list`, `token status`.

Runs: `device start`, `device stop [--wait]`. Both hold a per-Cloud-Device lock; exit 4 "locked" means another caller is starting or stopping it, so wait (`--wait-lock`) rather than fight it.

Pool (the project sets `RCE_POOL`): `device list --pool` shows which members are free; `device start --pool` claims a Free Cloud Device and prints its `id` and `run.id`; stop it with `device stop <id> --run <run id>`, which stops only that Run.

On a running Cloud Device:

| Command | Use |
|---|---|
| `sideload <device> <file>` | Install a zip or RSG `.bin`; reports `installed`, `identical` or the installer's failure (exit 4). |
| `launch <device> [--param K=V]…` | Launch the sideloaded dev app with launch params. |
| `key <device> <key>… [--delay MS]` | Remote keys (`Home`, `Select`, `Up`, `Back`, `Lit_a`, …). |
| `ecp <device> <path> [--method POST]` | Any ECP command; `query/active-app`, `query/device-info` give JSON with `--json`. |
| `console <device> --until REGEX --timeout S --strip-ansi` | BrightScript console; exits 0 on the first match, 5 on timeout. |
| `screenshot <device> -o FILE` | JPEG of the foreground dev app only. |
| `forward <device> <port> [--local N]` | Local TCP port bridged to a device port, for the console, the SceneGraph inspector and the debuggers in Debuggers. |

Ask-first (rule 1): `device create <name> --type tv|stb`, `device retire`, `device setup-dev`, `token set`, `snapshot take <device> --label NAME`, `snapshot use-as-dev <device> <id>`, `selftest --live [--device NAME]` (proves `rce` end to end on a Cloud Device). <!-- glossary-ok: spec flag name -->

`--json` prints JSON on stdout; errors go to stderr as `rce: <message>`.

## Exit codes

| Code | Meaning | Usual next move |
|---|---|---|
| 0 | OK | |
| 1 | RCE unreachable or a 5xx; also a `device start` refused after RCE accepted it (a Run was made) | Retry later; tell the user. |
| 2 | Usage: bad arguments, no token, confirmation declined or impossible without a terminal | Fix the call, or hand it to the user. |
| 3 | Not found: Cloud Device, Device Name, Snapshot, ECP command or app | `rce device list`, `rce snapshot list`. |
| 4 | Refused: not running, already running, trial Run limit or trial used up, locked, rejected token, dev mode or "Control by mobile apps" missing, wrong or missing Dev Password (`setup-dev` stores one; pipelines set `RCE_DEV_PASSWORD`), failed install, no dev app in the foreground | Read the message: it names the cause and often the command that fixes it. |
| 5 | Timeout: Run or Snapshot not ready, or `console --until` saw no match | |
| 130 | Interrupted; a Run `start` asked for or was waiting on is stopped first | |

## Verify on the device

Claim success only from evidence the Cloud Device gave you:

1. **Console**: start `rce console <device> --until '<marker line>' --timeout 120 --strip-ansi` in the background *before* `sideload` or `launch`, so it catches every line of this launch. A new connection first replays earlier lines, so the marker must be unique to this launch (a fresh tag, e.g. from `launch --param`). Exit 0 is the evidence; exit 5 means the line never came.
2. **ECP state**: `rce ecp <device> query/active-app --json` shows which app is in the foreground; `query/device-info --json` shows `developer-enabled` and `ecp-setting-mode`; `query/app-ui` gives the SceneGraph tree as XML, with `focused="true"` on the focused nodes.
3. **Screenshot**: `rce screenshot <device> -o /tmp/shot.jpg`, then Read the JPEG to look at it. It fails (exit 4) unless the dev app is in the foreground. During playback it shows the video frame.

## Debuggers

`rce forward <device> <port>` makes `127.0.0.1:<port>` reach the device port. Through it work the BrightScript console on 8085 (with `nc`), the BrightScript console's debugger (it runs in the console, on 8085 too), the SceneGraph inspector on 8080, and the TypeScript debugger on 9999. `forward` runs until interrupted, so start it in the background and stop it when done. The console takes one client at a time: while `rce console` is attached, `nc` on 8085 gets "Console connection is already in use." and is hung up, so stop `rce console` first. Ports 80 and 8060 are HTTP: use `sideload` and `ecp` for those.

The VS Code BrightScript debugger (extension 3.0+, roku-debug 0.24+) reaches a Cloud Device through its own RCE support, not through `forward`: start the Run with `rce device start`, then set `"device": {"id": <RCE id from rce device list>}` in `launch.json`. The extension takes its RCE token from its Cloud Emulator account or `ROKU_RCE_TOKEN`, not from `rce`.
