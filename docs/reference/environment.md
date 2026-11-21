# Environment

| Variable | Use |
|---|---|
| `RCE_TOKEN`, `RK_RCE_TOKEN` | Override the stored token (see [Token](commands.md#token)). |
| `ROKU_RCE_CONFIG_PATH` | rk's config file, where `rce` reads the token and `rce token set` writes it. Default `~/roku-rce-config.json`. |
| `RCE_API_URL` | Core API base URL. Default `https://api.rce.roku.com/api/v1`. Tests point it at the fake RCE. Where the token may go: see [Token](commands.md#token). |
| `RCE_POOL` | The Pool, for `device list --pool` and `device start --pool`: a JSON object from each member's RCE id to its Dev Snapshot id, e.g. `{"375": 2001, "376": 2002}`. Keys are RCE ids (all digits), never Device Names, since a runner has none. |
| `RCE_POOL_LOOK_SECONDS` | Test-only: the seconds between `--wait-free` looks (default 15, plus up to a third more at random), so the tests run fast. Not for pipelines. |
| `RCE_LOCK_OWNER` | A name recorded in the device lock, so a blocked caller sees who holds it (e.g. an agent's name). |
| `RCE_DEV_PASSWORD` | The Dev Password for every command that signs in to the installer (sideload, screenshot, selftest), for whichever Cloud Device it addresses; it wins over a stored one. For pipelines: set a CI secret from `rce device show <device> --dev-password` (see [Pipelines](../../README.md#pipelines-cicd)). `rce` drops any trailing CR and LF characters (`\r`, `\n`) from it, which a secret set from a pipe, a file or a paste can keep; any other whitespace is part of the Dev Password. `setup-dev` ignores it and stores its own. |
