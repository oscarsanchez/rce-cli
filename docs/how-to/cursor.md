# Cursor

Cursor's agent runs the terminal install's `rce`, so do [that install](../../README.md#terminal-clone-and-installsh) first. The plugin's `rce` is not on Cursor's PATH.

Signed in to Cursor, its agent also loads skills from installed Claude Code plugins, so with the plugin installed it already has the `rce` skill: add nothing, or Cursor loads it twice. Without the plugin, or if Cursor doesn't list `rce` among its skills, link the skill from your clone:

```sh
mkdir -p ~/.cursor/skills
ln -sfn "$PWD/skills/rce" ~/.cursor/skills/rce    # from the rce-cli clone
```

Cursor doesn't run the plugin's Stop hook, so nothing warns you when its agent finishes with a Run still billing. Check with `rce device list --running`.
