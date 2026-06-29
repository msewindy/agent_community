#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for f in "$ROOT"/scripts/*.sh; do
  sed -i 's/\r$//' "$f"
done
echo "Converted CRLF -> LF for scripts/*.sh"
