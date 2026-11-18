# Live RCE checks

Read before any command that talks to real RCE beyond a free read (`device list`, `device show`, `device status`, `device resolve`, `token status`, `usage`, `snapshot list`). A Run bills by the minute and RCE has no idle stop.

## Before

- **The user's OK.** Starting a Run, `selftest --live`, `setup-dev` and any other script that starts a Run need the user's explicit OK in this conversation. A ticket's "Live:" line says what to check, not that it is approved.
- **Token.** Use the one `rce` already reads (`~/roku-rce-config.json`, or `RCE_TOKEN` in the environment the user gave you). Read no token from another repo or file.
- **Device.** Only the Cloud Device the maintainer keeps for live checks (Device Name `player`). Every other Cloud Device stays off. `device create` and `device retire` are the user's.
- **Nothing running.** `rce device list --running` is empty first; if not, report it and start nothing.

## During

- **One Run at a time.** Set `RCE_LOCK_OWNER=<ticket or task>` so the device lock names you.
- **Cap it.** Pass `--max-runtime 600` (or the smallest cap that fits) as a backstop.
- **Guard every step.** A script continues only if the previous step succeeded. A failed start must never lead to a second start.
- **Stop in a finally path** (a shell `trap ... EXIT`), then confirm `rce device list --running` is empty.
- **Prompts.** `setup-dev`, `selftest --live` and other live scripts ask `[y/N]` on a terminal. Answer one the user has approved through `scripts/tty-drive LOG FIFO -- <command>` and `echo y > FIFO`. Leave out `--yes` unless the user asked for it.

## After

Record in the ticket's `## Comments`: the commands, the output (no token, Dev Password or WebRTC credentials), the Run ids and the device-minutes (`rce usage` before and after).
