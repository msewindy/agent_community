#!/usr/bin/env bash
set -euo pipefail
SNIP="$(cd "$(dirname "$0")" && pwd)/wsl_bashrc_snippet.sh"
BRC="$HOME/.bashrc"
TMP="$(mktemp)"
awk '
  /^# agent_community \(WSL2\)/ { skip=1; next }
  skip && /^export PATH=.*hermes-agent/ { skip=0; next }
  skip { next }
  { print }
' "$BRC" > "$TMP"
cat "$SNIP" >> "$TMP"
mv "$TMP" "$BRC"
echo "Updated $BRC"
