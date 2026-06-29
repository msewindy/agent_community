#!/usr/bin/env bash
# Run M2 + C7 acceptance entirely in WSL2
set -euo pipefail

export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${HOME}/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ROOT="${AGENT_COMMUNITY_ROOT:-/mnt/c/Users/Administrator/Desktop/agent_community}"
PY="${HOME}/.hermes/hermes-agent/venv/bin/python3"
export PYTHONPATH="${ROOT}"
export HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
export AGENT_COMMUNITY_ROOT="${ROOT}"

cd "${ROOT}"

if ! "${PY}" -m pip --version >/dev/null 2>&1; then
  echo "==> bootstrapping pip in Hermes venv"
  "${PY}" -m ensurepip --upgrade
fi

echo "==> pip install memory deps"
"${PY}" -m pip install -r agent_platform/requirements-memory.txt -q

echo "==> accept_m2_us"
"${PY}" agent_platform/memory/accept_m2_us.py "$@"

echo "==> accept_hermes_evolution_phase2"
"${PY}" agent_platform/evolution/accept_hermes_evolution_phase2.py

echo "==> accept_c7_phase3"
"${PY}" agent_platform/evolution/accept_c7_phase3.py

echo "==> accept_c7_phase4"
"${PY}" agent_platform/evolution/accept_c7_phase4.py

echo "==> smoke_hermes_evolution_hooks"
"${PY}" agent_platform/integrations/hermes/smoke_hermes_evolution_hooks.py

echo ""
echo "All WSL acceptance checks passed."
