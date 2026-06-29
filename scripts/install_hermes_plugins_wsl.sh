#!/usr/bin/env bash
# Install agent_community Hermes plugins in WSL (~/.hermes/plugins)
set -euo pipefail

ROOT="${AGENT_COMMUNITY_ROOT:-/mnt/c/Users/Administrator/Desktop/agent_community}"
HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
PLUGINS_DIR="${HERMES_HOME}/plugins"
SRC_BASE="${ROOT}/agent_platform/integrations/hermes"

mkdir -p "${PLUGINS_DIR}"

install_one() {
  local name="$1"
  local dir="${name//-/_}"
  local src="${SRC_BASE}/${dir}"
  local dest="${PLUGINS_DIR}/${name}"
  if [[ ! -d "${src}" ]]; then
    echo "SKIP ${name} — missing ${src}" >&2
    return 0
  fi
  rm -rf "${dest}"
  ln -sfn "${src}" "${dest}"
  printf '%s' "${ROOT}" > "${src}/AGENT_COMMUNITY_ROOT"
  echo "  ${dest} -> ${src}"
}

TEXT_PLUGINS=(
  agent-memverse
  agent-evolution
  agent-wiki
  agent-proactive
  agent-tools
  agent-calibration
)

for name in "${TEXT_PLUGINS[@]}" agent-perception; do
  install_one "${name}"
done

echo ""
echo "Text plugins installed (symlinks under ${PLUGINS_DIR})."
echo "Enable all text plugins:"
echo "  bash scripts/enable_hermes_text_plugins.sh"
echo ""
echo "Or manually:"
echo "  hermes plugins enable agent-memverse agent-evolution agent-wiki \\"
echo "    agent-proactive agent-tools agent-calibration"
echo ""
echo "Full text regression:"
echo "  bash scripts/run_wsl_text_full_acceptance.sh"
echo "  bash scripts/run_wsl_text_full_acceptance.sh --memverse"
