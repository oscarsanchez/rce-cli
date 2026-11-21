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

The plugin gives Claude the `rce` skill, the Stop hook, and `rce` on the PATH of Claude's Bash tool. It can't add permission rules; for those, see [Claude Code settings](docs/how-to/claude-code-settings.md).

The plugin's `rce` is on Claude's PATH only, not your terminal's. The steps you run yourself at a terminal (`rce token set`, `rce device setup-dev`) need the CLI install below too. With both installed, your own PATH comes first, so Claude also runs the CLI install's `rce`.

### Terminal: clone and `install.sh`

```sh
git clone https://github.com/oscarsanchez/rce-cli.git
cd rce-cli
./install.sh
```

This links `bin/rce` into `~/.local/bin` (put that on your PATH), so `git pull` updates it. It installs only the CLI and creates nothing under `~/.claude`. Run it again whenever you like; it only refreshes the link, and it refuses (changing nothing) when `~/.local/bin/rce` exists and is not a link.

### Pipelines

A pipeline downloads the single `bin/rce` script at a release tag, with no clone and no install: see [Pipelines (CI/CD)](docs/how-to/pipelines.md).

### Cursor

Cursor's agent runs the terminal install's `rce` and the plugin's skill. See [Cursor](docs/how-to/cursor.md).

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

## Docs

- [Command reference](docs/reference/commands.md): what each command does and its `--json` shape
- [Exit codes](docs/reference/exit-codes.md): each exit code, what it means and the usual next move
- [Environment](docs/reference/environment.md): the environment variables `rce` reads
- [Pipelines (CI/CD)](docs/how-to/pipelines.md): run `rce` in a pipeline, on one Cloud Device or a Pool
- [Cursor](docs/how-to/cursor.md): use `rce` and its skill from Cursor
- [Claude Code settings](docs/how-to/claude-code-settings.md): permission rules for the plugin, and its Stop hook
- [Development](docs/development.md): the check, the lints and the tests
- [GLOSSARY.md](GLOSSARY.md): the words `rce` and these docs use
- [CHANGELOG.md](CHANGELOG.md): what changed in each release
- [SECURITY.md](SECURITY.md): reporting a vulnerability
