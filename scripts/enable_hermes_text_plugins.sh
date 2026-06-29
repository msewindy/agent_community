#!/usr/bin/env bash
# Enable all text-interaction Hermes plugins (skip agent-perception for text-only)
set -euo pipefail

export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${HOME}/.local/bin:$PATH"

if ! command -v hermes >/dev/null 2>&1; then
  echo "hermes not in PATH; add ~/.hermes/hermes-agent/venv/bin" >&2
  exit 1
fi

for p in agent-memverse agent-evolution agent-wiki agent-proactive agent-tools agent-calibration; do
  echo "==> hermes plugins enable ${p}"
  hermes plugins enable "${p}" || echo "WARN: enable ${p} failed (may already be enabled)" >&2
done

echo ""
echo "Text plugins enabled. Perception (agent-perception) skipped — enable manually if needed."
echo "Start chat: hermes chat"
