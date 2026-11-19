# Fresh-install check

Proves a new user's two installs (terminal and Claude Code plugin), and Cursor on top of them, work from GitHub at a tag, on this machine, with the maintainer's own install, token, Device Names and keychain left exactly as they were. Free: it starts no Run. Recorded first on `classic-rsg-sample` ticket 06.

Every command below runs with the **sandbox env** unless it says otherwise. Secrets travel only inside one command (a pipe or a variable set in that command), never in argv, output or a file outside the sandbox.

## 1. Sandbox

**Public first.** In the maintainer's own environment (gh's login lives there), check both repos a new user installs from:

```sh
gh repo view oscarsanchez/rce-cli --json visibility -q .visibility
gh repo view oscarsanchez/rce-cli-example-classic-rsg --json visibility -q .visibility
```

Both print `PUBLIC` before anything is installed. Any other answer: stop, install nothing, and report which repo printed what. A new user can't reach a private repo, so an install through the maintainer's login proves nothing.

`FI=<scratchpad>/fresh-install`, `REAL=$HOME` (the maintainer's). Write `$FI/env.sh` and `source` it in every later command:

```sh
export HOME=$FI/home XDG_CONFIG_HOME=$FI/home/.config CLAUDE_CONFIG_DIR=$FI/home/.claude
export PATH=$FI/home/.local/bin:$FI/tools:/opt/homebrew/bin:/usr/bin:/bin
unset RCE_TOKEN RK_RCE_TOKEN ROKU_RCE_CONFIG_PATH
export GIT_CONFIG_NOSYSTEM=1 GH_CONFIG_DIR=$FI/home/.config/gh GIT_TERMINAL_PROMPT=0
export AGENT_CLI_CREDENTIAL_STORE=file   # cursor-agent keeps its login under $HOME, not in the keychain
```

- `$FI/tools` holds links to `uv`, `uvx` and `claude` only (and `cursor-agent` from step 6), so the maintainer's `~/.local/bin/rce` is off `PATH`.
- `$FI/home/.gitconfig` clears every git credential helper (the system `osxkeychain` helper would try to store credentials under the fake `HOME` and pop a macOS keychain dialog):

  ```ini
  [credential]
      helper =
  ```

Done when `command -v rce` finds nothing.

## 2. Baseline

Record a checksum (`shasum -a 256`, first 16) and mtime of each of the maintainer's files, without their contents, into `$FI/before.txt`: `$REAL/roku-rce-config.json`, `$REAL/.config/roku-rce/devices.toml`, a listing of `$REAL/.config/roku-rce/locks/`, `$REAL/.claude/settings.json`, `$REAL/.claude/plugins/{installed_plugins,known_marketplaces,blocklist}.json`, a listing of `$REAL/.claude/plugins/marketplaces/`, the `$REAL/.local/bin/rce` link target and mtime, `$REAL/.gitconfig`, `$REAL/.config/gh/{hosts,config}.yml`, `$REAL/.cursor/{cli-config,mcp}.json`, a listing of `$REAL/.cursor/skills/`.

## 3. No GitHub login

A new user installs from public repos with no GitHub login, and so does the sandbox: `GH_CONFIG_DIR` is empty, git has no credential helper, and `GIT_TERMINAL_PROMPT=0` makes a clone that wants a login fail instead of asking. Steps 4 and 5 run git and `claude plugin` exactly as the README shows. A login failure there means a repo is private: stop and report, as in step 1.

## 4. Terminal install

```sh
git clone --branch <tag> https://github.com/oscarsanchez/rce-cli.git $FI/home/rce-cli
cd $FI/home/rce-cli && ./install.sh
cd / && rce --version && rce token status    # exit 2: no token yet
jq -r .token $REAL/roku-rce-config.json | rce token set
rce token status && rce device list          # no Device Names: the fresh devices.toml is empty
```

Done when `rce --version` prints the tag's version and both `token status` and `device list` exit 0.

## 5. Plugin install

Run the README's two marketplace commands, then `claude plugin list` shows `rce-cli` enabled at the tag's version.

**The headless run is the maintainer's.** It needs the maintainer's Claude login, which lives in the macOS keychain: the fake `HOME` can't reach it, and the permission layer refuses an agent's keychain read. Write `$FI/claude-run.sh`, with `$FI` and `$REAL` spelled out as absolute paths:

```sh
. $FI/env.sh
export PATH=$FI/tools:/opt/homebrew/bin:/usr/bin:/bin   # no $FI/home/.local/bin: only the plugin can supply rce
CLAUDE_CODE_OAUTH_TOKEN=$(HOME=$REAL security find-generic-password -s 'Claude Code-credentials' -w | jq -r .claudeAiOauth.accessToken) \
  claude -p 'List your skills. Then run `command -v rce` and `rce --version` and show their output verbatim.' \
  --allowedTools 'Bash(command -v rce)' 'Bash(rce --version)' \
  --output-format stream-json --verbose --debug=hooks --debug-file $FI/claude-debug.log \
  > $FI/claude-stream.jsonl
```

Hand the maintainer the one line `sh <absolute $FI>/claude-run.sh` (it runs from any shell and leaves theirs untouched) and the list below. Keep `$FI` until they report it ran, then check the list yourself against `$FI/claude-stream.jsonl` and `$FI/claude-debug.log`.

Done when:

- the stream's `init` event lists `rce-cli:rce` under `skills` and `rce-cli` under `plugins`, at `$FI/home/.claude/plugins/cache/rce-cli/rce-cli/<version>`;
- `command -v rce` resolves inside that plugin folder and `rce --version` prints the tag's version;
- `$FI/claude-debug.log` shows the Stop hook `rce-stop-hook` (plugin `rce-cli@rce-cli`) finished with status 0.

## 6. Cursor

Checks the README's Cursor section. Install Cursor's CLI in the sandbox from its install script (read it first; it writes only under `$HOME`) and link `cursor-agent` into `$FI/tools`. Have the maintainer log it in with `cursor-agent login` under the sandbox env (interactive; `AGENT_CLI_CREDENTIAL_STORE=file` keeps it out of the keychain). In `$FI/home/.config/cursor/cli-config.json`, set `permissions.allow` to `["Shell(command)", "Shell(rce)"]`, and move `$FI/home/roku-rce-config.json` aside during each run so no `rce` call can reach RCE. From an empty `$FI/ws`:

```sh
cursor-agent -p --trust --output-format stream-json 'List every skill available to you whose name or description mentions "rce" or "Roku", with the exact file path it was loaded from. Then run `command -v rce` and `rce --version` and show their output verbatim.'
```

Done when:

- with the plugin installed and no link, the skill is named `rce` (Cursor names it after its folder, so tags before the move to `skills/rce/`, `v0.1.0` included, show `skill`) and its path is inside `$FI/home/.claude/plugins/cache/rce-cli/`; with the link added too, it is listed twice (the README's reason not to link); with the link alone, once;
- `command -v rce` is `$FI/home/.local/bin/rce` and `rce --version` prints the tag's version; with `$FI/home/.local/bin` off `PATH`, `command -v rce` exits 1 (the plugin's `rce` is not on Cursor's PATH).

Seen at `v0.1.0`: Cursor's CLI did not run the plugin's Stop hook (a test hook in the sandbox plugin cache that writes a marker never ran), so the README says Cursor has no running-Run warning.

## 7. Clean up

Once the maintainer has run step 5's script and step 6's login, re-take the baseline into `$FI/after.txt`; `diff before.txt after.txt` is empty and the keychain has as many `Claude Code-credentials` items as before (count them with the real `HOME`: the keychain search list follows `HOME`). Run `cursor-agent logout` under the sandbox env. Record the commands and output (no token) on the ticket, then delete `$FI`, which holds a copy of the RCE token.
