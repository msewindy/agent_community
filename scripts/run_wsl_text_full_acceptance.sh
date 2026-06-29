#!/usr/bin/env bash
# Text-mode full regression (M2–M8 minus US-2 vision) + C7 + Hermes plugin smokes — WSL2 only
set -euo pipefail

export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${HOME}/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ROOT="${AGENT_COMMUNITY_ROOT:-/mnt/c/Users/Administrator/Desktop/agent_community}"
PY="${HOME}/.hermes/hermes-agent/venv/bin/python3"
export PYTHONPATH="${ROOT}"
export HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
export AGENT_COMMUNITY_ROOT="${ROOT}"

MEMVERSE=0
SKIP_PYTEST=0
for arg in "$@"; do
  case "$arg" in
    --memverse) MEMVERSE=1 ;;
    --skip-pytest) SKIP_PYTEST=1 ;;
  esac
done

cd "${ROOT}"

if ! "${PY}" -m pip --version >/dev/null 2>&1; then
  echo "==> bootstrapping pip in Hermes venv"
  "${PY}" -m ensurepip --upgrade
fi

echo "==> pip install memory deps"
"${PY}" -m pip install -r agent_platform/requirements-memory.txt -q

echo ""
echo "========== Phase A: M8 text integration (US-1,3–8 + engineering, skip US-2) =========="
"${PY}" agent_platform/integration/accept_m8_integration.py --skip-us2 --skip-hermes --skip-stdio

echo ""
echo "========== Phase B: M2 + C7 evolution (Phase 1–4) =========="
M2_ARGS=()
if [[ "${MEMVERSE}" -eq 1 ]]; then
  M2_ARGS+=(--memverse)
fi
"${PY}" agent_platform/memory/accept_m2_us.py "${M2_ARGS[@]}"
"${PY}" agent_platform/evolution/accept_hermes_evolution_phase2.py
"${PY}" agent_platform/evolution/accept_c7_phase3.py
"${PY}" agent_platform/evolution/accept_c7_phase4.py

echo ""
echo "========== Phase C: Hermes plugin smokes (text modules) =========="
for smoke in \
  smoke_hermes_tools.py \
  smoke_hermes_wiki_tools.py \
  smoke_hermes_proactive_tools.py \
  smoke_hermes_tools_mcp.py \
  smoke_hermes_calibration_tools.py \
  smoke_hermes_evolution_hooks.py; do
  echo "--- ${smoke} ---"
  "${PY}" "agent_platform/integrations/hermes/${smoke}"
done

if [[ "${SKIP_PYTEST}" -eq 0 ]]; then
  echo ""
  echo "========== Phase D: pytest (M8 + evolution) =========="
  "${PY}" -m pytest \
    agent_platform/tests/test_m8_accept.py \
    agent_platform/tests/test_evolution_phase4.py \
    -q
fi

echo ""
echo "All text-mode automated checks passed."
echo "Next: manual Hermes chat — see docs/功能测试验证方案.md Phase 4"
