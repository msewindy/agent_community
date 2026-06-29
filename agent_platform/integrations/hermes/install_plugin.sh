#!/usr/bin/env bash
# Install agent-memverse + agent-wiki Hermes plugins into ~/.hermes/plugins/
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
HERMES_INTEGRATIONS="${REPO_ROOT}/agent_platform/integrations/hermes"

install_one() {
  local name="$1"
  local dir="${2:-${name//-/_}}"
  local src="${HERMES_INTEGRATIONS}/${dir}"
  local dest="${HERMES_HOME}/plugins/${name}"
  if [[ ! -d "${src}" ]]; then
    echo "  SKIP ${name}: missing ${src}" >&2
    return 0
  fi
  mkdir -p "${HERMES_HOME}/plugins"
  rm -rf "${dest}"
  ln -sfn "${src}" "${dest}"
  echo "${REPO_ROOT}" > "${src}/AGENT_COMMUNITY_ROOT"
  echo "  ${dest} -> ${src}"
}

echo "Repo: ${REPO_ROOT}"
echo "Plugins:"
install_one "agent-memverse"
install_one "agent-evolution"
install_one "agent-wiki"
install_one "agent-perception"
install_one "agent-proactive"
install_one "agent-tools"
install_one "agent-calibration"
install_one "agent-student"

echo ""
echo "Enable:"
echo "  hermes plugins enable agent-memverse"
echo "  hermes plugins enable agent-evolution"
echo "  hermes plugins enable agent-wiki"
echo "  hermes plugins enable agent-perception"
echo "  hermes plugins enable agent-proactive"
echo "  hermes plugins enable agent-tools"
echo "  hermes plugins enable agent-calibration"
echo "  hermes plugins enable agent-student"
echo "  hermes tools enable agent_memory"
echo "  hermes tools enable agent_evolution"
echo "  hermes tools enable agent_wiki"
echo "  hermes tools enable agent_perception"
echo "  hermes tools enable agent_proactive"
echo "  hermes tools enable agent_tools"
echo "  hermes tools enable agent_calibration"
echo "  hermes tools enable agent_behavior"
echo "  hermes tools enable agent_student"
echo ""
echo "Student Jarvis env (optional):"
echo "  export STUDENT_JARVIS_STUDENT_ID=demo-stu-01"
echo "  export STUDENT_JARVIS_DATA_ROOT=${REPO_ROOT}/student_data"
echo ""
echo "Memory tools: agent_memory_write, agent_memory_search, agent_memory_delete"
echo "Wiki tools:   wiki_ingest, wiki_query, wiki_precipitate_evaluate"
echo "Perception:   agent_perception_describe, agent_perception_policy"
echo "Proactive:    agent_proactive_evaluate, agent_proactive_feedback, ..."
echo "Tools (M6):   agent_tool_invoke, agent_tool_approve_draft, ..."
echo "Calib (M7):   agent_calibrate_output, agent_handle_correction, agent_behavior_*"
echo "Recall:       agent_combined_recall  (toolset: agent_recall)"
echo "Student:      student_context_get, gap_map_query, attempt_submit, push_queue_peek, student_answer_gate"
