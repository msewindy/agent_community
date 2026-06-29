#!/usr/bin/env bash
# Draft panel (:8766) with Node/npx on PATH for MCP stdio approve.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${HOME}/.hermes/node/bin:${HOME}/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export PYTHONPATH="${ROOT}"
export AGENT_COMMUNITY_ROOT="${ROOT}"

PY="${HOME}/.hermes/hermes-agent/venv/bin/python3"
if [[ ! -x "${PY}" ]]; then
  PY="python3"
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "npx not found — run: bash scripts/install_node_wsl.sh" >&2
  exit 1
fi

exec "${PY}" -m agent_platform.api.draft_panel "$@"
