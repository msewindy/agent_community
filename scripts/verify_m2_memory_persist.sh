#!/usr/bin/env bash
# Verify M2 mock persist: write → simulate restart → search → panel file
set -euo pipefail

export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${HOME}/.local/bin:$PATH"
ROOT="${AGENT_COMMUNITY_ROOT:-/mnt/c/Users/Administrator/Desktop/agent_community}"
PY="${HOME}/.hermes/hermes-agent/venv/bin/python3"
export PYTHONPATH="${ROOT}"
export AGENT_COMMUNITY_ROOT="${ROOT}"

cd "${ROOT}"
STORE="${ROOT}/skills_data/memory_store.json"
MARKER="m2-persist-verify-$(date +%s)"

echo "==> config"
grep -A2 '^mock:' agent_platform/config/memory.yaml || true

echo "==> write"
"${PY}" agent_platform/memory/cli_memory.py write \
  "用户偏好：回复风格简短直接 (${MARKER})" \
  --category preference

echo "==> search (same process config)"
HITS=$("${PY}" agent_platform/memory/cli_memory.py search "${MARKER}")
echo "${HITS}" | head -20
if ! echo "${HITS}" | grep -q '"hits"'; then
  echo "FAIL: search output unexpected" >&2
  exit 1
fi
if echo "${HITS}" | grep -q '"hits": \[\]'; then
  echo "FAIL: no hits after write" >&2
  exit 1
fi

echo "==> simulate hermes restart (new Python process)"
HITS2=$("${PY}" -c "
from agent_platform.memory.service import MemoryService
svc = MemoryService()
r = svc.search('${MARKER}')
print(len(r.hits))
")
if [[ "${HITS2}" -lt 1 ]]; then
  echo "FAIL: restart simulation found 0 hits" >&2
  exit 1
fi
echo "OK   restart simulation hits=${HITS2}"

if [[ -f "${STORE}" ]]; then
  echo "OK   persist file ${STORE} ($(wc -c < "${STORE}") bytes)"
else
  echo "FAIL: missing ${STORE}" >&2
  exit 1
fi

echo ""
echo "verify_m2_memory_persist: PASS"
echo "Next in hermes chat:"
echo "  1) agent_memory_write (not built-in memory)"
echo "  2) exit and new hermes chat"
echo "  3) agent_memory_search for 简短"
