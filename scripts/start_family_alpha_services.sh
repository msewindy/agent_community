#!/usr/bin/env bash
# Start family Alpha 8770 + 8771 in background (WSL/Linux).
set -euo pipefail

ROOT="${AGENT_COMMUNITY_ROOT:-/mnt/c/Users/Administrator/Desktop/agent_community}"
PY="${HOME}/.hermes/hermes-agent/venv/bin/python"
export AGENT_COMMUNITY_ROOT="${ROOT}"
export PYTHONPATH="${ROOT}"
export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${PATH}"

cd "${ROOT}"

start_one() {
  local port="$1"
  local module="$2"
  local log="/tmp/jarvis-${port}.log"
  if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
    echo "Port ${port} already in use — skip"
    return 0
  fi
  nohup "${PY}" -m uvicorn "${module}" --host 0.0.0.0 --port "${port}" >"${log}" 2>&1 &
  echo "Started ${module} on :${port} (log: ${log})"
}

start_one 8771 agent_platform.api.student_chat:app
start_one 8770 agent_platform.api.student_panel:app

sleep 4
echo "--- listening ---"
ss -tlnp 2>/dev/null | grep -E '8770|8771' || true
echo "--- health 8770 ---"
curl -sf http://127.0.0.1:8770/health || echo "8770 not ready"
echo ""
echo "--- health 8771 ---"
curl -sf http://127.0.0.1:8771/health || echo "8771 not ready"
echo ""
