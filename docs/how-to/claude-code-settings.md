# Claude Code settings

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
