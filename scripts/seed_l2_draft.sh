#!/usr/bin/env bash
# Create a pending L2 draft in tools_data/drafts for draft panel (:8766).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${HOME}/.hermes/node/bin:${HOME}/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PY="${HOME}/.hermes/hermes-agent/venv/bin/python3"
if [[ ! -x "${PY}" ]]; then
  PY="python3"
fi

export PYTHONPATH="${ROOT}"
export AGENT_COMMUNITY_ROOT="${ROOT}"

"${PY}" agent_platform/tools/seed_panel_draft.py --mock "$@"

echo
echo "Pending drafts (CLI):"
"${PY}" agent_platform/tools/cli_tools.py drafts
