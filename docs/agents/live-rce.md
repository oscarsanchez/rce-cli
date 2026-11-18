# Live RCE checks

Read before any command that talks to real RCE beyond a free read (`device list`, `device show`, `device status`, `device resolve`, `token status`, `usage`, `snapshot list`). A Run bills by the minute and RCE has no idle stop.

## Which Cloud Device

- **The agents' Cloud Device.** Agents start Runs only on the one Cloud Device the maintainer keeps for agents, named by its Device Name in `CLAUDE.local.md` at the repo root (personal, gitignored). Every other Cloud Device is someone's own: agents start nothing on it.
- **None named, no Run.** If `CLAUDE.local.md` names no agents' Cloud Device, or `rce device list` doesn't show it, agents start nothing and ask.

## The standing OK

A Run on the agents' Cloud Device needs no OK in the conversation when it keeps every rule below: one Run at a time, `rce device list --running` empty first, `--max-runtime 600` or less, `RCE_LOCK_OWNER` set, every step guarded, stop in a finally path, and the record on the ticket.

These still need the maintainer's OK in this conversation, each time: `device create`, `device retire`, `setup-dev`, `snapshot take`, `snapshot use-as-dev`, `token set`, `selftest --live`, and any Run on another Cloud Device. A ticket's "Live:" line says what to check, not that it is approved.

`setup-dev`'s web-viewer steps (account link, Developer Settings, Control by mobile apps) are the maintainer's: the developer portal's View device opens outside an agent-driven browser tab.

## Before

- **Token.** Use the one `rce` already reads (`~/roku-rce-config.json`, or `RCE_TOKEN` in the environment the maintainer gave you). Read no token from another repo or file.
- **Nothing running.** `rce device list --running` is empty first: wait your turn (Sharing the agents' Cloud Device).

## During

- **One Run at a time.** Set `RCE_LOCK_OWNER=<ticket or task>` so the device lock names you.
- **Cap it.** Pass `--max-runtime 600` or less (the smallest cap that fits) as a backstop.
- **Guard every step.** A script continues only if the previous step succeeded. A failed start must never lead to a second start.
- **Stop in a finally path** (a shell `trap ... EXIT`), then confirm `rce device list --running` is empty.
- **Prompts.** `setup-dev`, `selftest --live` and other live scripts ask `[y/N]` on a terminal. Answer one the maintainer has approved through `scripts/tty-drive LOG FIFO -- <command>` and `echo y > FIFO`. Leave out `--yes` unless the maintainer asked for it.

## Sharing the agents' Cloud Device

Several agents may work on it at once, and the trial runs one Run at a time across the whole org.

- **Wait your turn.** Before each start, while `rce device list --running` isn't empty, re-check every 60 s; after 20 min, report it and start nothing.
- **Know your Run.** Note your Run id (`run.id` from `rce device start --json`). Before each `rce` call that reaches a Run (`console`, `sideload`, `key`, `launch`, `screenshot`, `ecp`, `forward`), confirm `rce device status <device> --json` still shows that id.
- **Stop only yours.** The trap stops the Cloud Device only while its Run is still your id.
- **A refused start (exit 4) made no Run.** Another start won: stop nothing, and wait your turn before the next start.

## After

Record in the ticket's `## Comments`: the commands, the output (no token, Dev Password or WebRTC credentials), the Run ids and the device-minutes (`rce usage` before and after).
