#!/usr/bin/env bash
# Links `bin/rce` from this checkout into ~/.local/bin. Safe to run again.
# Claude Code users get the skill and Stop hook from the rce-cli plugin, so this
# touches nothing under ~/.claude.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bin="$HOME/.local/bin"
link="$bin/rce"

if [[ -e "$link" && ! -L "$link" ]]; then
  echo "install: $link exists and is not a link; move it away first" >&2
  exit 1
fi

mkdir -p "$bin"
ln -sfn "$repo/bin/rce" "$link"
echo "linked $link -> $repo/bin/rce"

case ":$PATH:" in
  *":$bin:"*) ;;
  *) echo "note: $bin is not on PATH; add it to use \`rce\` from any directory" ;;
esac
