#!/usr/bin/env bash
set -uo pipefail
export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${HOME}/.local/bin:${PATH}"

for p in agent-memverse agent-evolution agent-wiki agent-proactive agent-tools agent-calibration agent-student; do
  echo "==> enable plugin ${p}"
  hermes plugins enable "${p}" || echo "WARN: plugin enable ${p} failed"
done

for t in agent_memory agent_evolution agent_wiki agent_proactive agent_tools agent_calibration agent_behavior agent_student agent_recall; do
  echo "==> enable toolset ${t}"
  hermes tools enable "${t}" || echo "WARN: toolset enable ${t} failed"
done

echo "==== plugin list ===="
hermes plugins list 2>&1 | head -n 80 || true
echo "==== verify ===="
bash /mnt/d/project/agent_community/scripts/verify_hermes_plugins_wsl.sh || true
