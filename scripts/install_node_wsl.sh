#!/usr/bin/env bash
# Ensure Node/npx on PATH for MCP stdio (filesystem via npx).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE_DIR="${HOME}/.hermes/node"
LOCAL_BIN="${HOME}/.local/bin"
PY="${HOME}/.hermes/hermes-agent/venv/bin/python3"
HERMES="${HOME}/.hermes/hermes-agent/venv/bin/hermes"

export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${NODE_DIR}/bin:${LOCAL_BIN}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

echo "=== Node / npx for MCP stdio ==="

if [[ ! -x "${NODE_DIR}/bin/node" ]]; then
  echo "Node missing under ${NODE_DIR}; running hermes postinstall..."
  if [[ -x "${HERMES}" ]]; then
    "${HERMES}" postinstall
  else
    echo "ERROR: hermes not found; install Hermes Agent first." >&2
    exit 1
  fi
fi

mkdir -p "${LOCAL_BIN}"
for cmd in node npm npx corepack; do
  src="${NODE_DIR}/bin/${cmd}"
  dst="${LOCAL_BIN}/${cmd}"
  if [[ -e "${src}" ]] && [[ ! -e "${dst}" ]]; then
    ln -sf "${src}" "${dst}"
    echo "linked ${dst} -> ${src}"
  fi
done

echo
echo "node: $(command -v node) ($("${NODE_DIR}/bin/node" --version))"
echo "npx:  $(command -v npx) ($("${NODE_DIR}/bin/npx" --version))"

echo
echo "=== bashrc PATH (agent_community snippet) ==="
bash "${ROOT}/scripts/apply_wsl_bashrc.sh"

echo
echo "=== prefetch @modelcontextprotocol/server-filesystem ==="
export NPM_CONFIG_UPDATE_NOTIFIER=false
timeout 120 "${NODE_DIR}/bin/npx" -y @modelcontextprotocol/server-filesystem --help >/dev/null 2>&1 \
  || "${NODE_DIR}/bin/npx" -y @modelcontextprotocol/server-filesystem --version >/dev/null 2>&1 \
  || echo "(npx prefetch skipped — first panel approve may download package)"

echo
echo "=== verify npx + MCP prerequisites ==="
cd "${ROOT}"
export PYTHONPATH="${ROOT}"
export AGENT_COMMUNITY_ROOT="${ROOT}"
if [[ ! -x "${PY}" ]]; then
  echo "WARN: Hermes venv python missing; skip Python check"
  exit 0
fi
"${PY}" -m pip install -q -r agent_platform/requirements-tools.txt 2>/dev/null || true
"${PY}" - <<'PY'
import shutil
from agent_platform.tools._config import load_mcp_config
from agent_platform.tools.adapters.router import stdio_prerequisites_ok, mcp_sdk_available

if shutil.which("npx") is None:
    raise SystemExit("FAIL: npx not on PATH")
cfg = load_mcp_config()
fs = (cfg.get("servers") or {}).get("filesystem") or {}
ok, reason = stdio_prerequisites_ok(fs)
if not ok:
    raise SystemExit(f"FAIL: filesystem stdio prerequisites: {reason}")
if not mcp_sdk_available():
    raise SystemExit("FAIL: pip package mcp not installed (requirements-tools.txt)")
print("OK: npx on PATH, filesystem stdio prerequisites met, mcp SDK present")
PY

echo
echo "install_node_wsl: OK"
echo "Start draft panel with: bash scripts/run_draft_panel.sh"
