# Live RCE checks

Read before any command that talks to real RCE beyond a free read (`device list`, `device show`, `device status`, `device resolve`, `token status`, `usage`, `snapshot list`). A Run bills by the minute and RCE has no idle stop.

## Which Cloud Device

- **The agents' Cloud Device.** Agents start Runs only on the one Cloud Device the maintainer keeps for agents: the Device Name in `RCE_AGENT_DEVICE` (set in the maintainer's `.claude/settings.local.json`, gitignored). Every other Cloud Device is someone's own: agents start nothing on it.
- **None named, no Run.** If `RCE_AGENT_DEVICE` is unset, or `rce device list` doesn't show it, agents start nothing and ask.

## The standing OK

Start Runs on the agents' Cloud Device with `scripts/live-run <ticket or task> [--max-runtime N] -- <command…>`; it needs no OK in the conversation. The script keeps the rules itself: it waits its turn while `rce device list --running` isn't empty (gives up after 20 min), caps the Run at 600 s, sets `RCE_LOCK_OWNER`, starts once from the Dev Snapshot, runs `<command>` with `RCE_DEVICE` and `RCE_RUN` set, stops only its own Run however `<command>` ends, and prints the record. A refused start (exit 4) made no Run: run `scripts/live-run` again later.

These still need the maintainer's OK in this conversation, each time: `device create`, `device retire`, `setup-dev`, `snapshot take`, `snapshot use-as-dev`, `token set`, `selftest --live`, and any Run on another Cloud Device. A ticket's "Live:" line says what to check, not that it is approved.

`setup-dev`'s web-viewer steps (account link, Developer Settings, Control by mobile apps) are the maintainer's: the developer portal's View device opens outside an agent-driven browser tab.

## During

- **Token.** Use the one `rce` already reads (`~/roku-rce-config.json`, or `RCE_TOKEN` in the environment the maintainer gave you). Read no token from another repo or file.
- **Know your Run.** Several agents may share the agents' Cloud Device. Before each `rce` call in `<command>` that reaches the Run (`console`, `sideload`, `key`, `launch`, `screenshot`, `ecp`, `forward`), confirm `rce device status "$RCE_DEVICE" --json` still shows `run.id` `$RCE_RUN`.
- **Guard every step.** `<command>` continues only if the previous step succeeded.
- **Prompts.** `setup-dev`, `selftest --live` and other live scripts ask `[y/N]` on a terminal. Answer one the maintainer has approved through `scripts/tty-drive LOG FIFO -- <command>` and `echo y > FIFO`. Leave out `--yes` unless the maintainer asked for it.

## After

Record in the ticket's `## Comments`: the commands, the output (no token, Dev Password or WebRTC credentials), and `scripts/live-run`'s record (the Run id, its time and `rce usage` before and after).
