#!/usr/bin/env bash
# One-shot family Alpha environment reset (WSL). Run from repo root.
set -euo pipefail

ROOT="${AGENT_COMMUNITY_ROOT:-/mnt/c/Users/Administrator/Desktop/agent_community}"
BACKUP="${HOME}/family-alpha-backup-$(date +%Y%m%d-%H%M)"
PY="${HOME}/.hermes/hermes-agent/venv/bin/python"

phase="${1:-all}"

do_backup() {
  mkdir -p "${BACKUP}"
  echo "==> Backup -> ${BACKUP}"
  cp -a "${ROOT}/student_data" "${BACKUP}/" 2>/dev/null || true
  cp -a "${ROOT}/wiki_data" "${BACKUP}/" 2>/dev/null || true
  cp "${ROOT}/agent_platform/learning/catalog/kp_catalog.json" "${BACKUP}/"
  cp "${ROOT}/agent_platform/learning/question_bank/questions.db" "${BACKUP}/" 2>/dev/null || true
  cp "${ROOT}/skills_data/memory_store.json" "${BACKUP}/" 2>/dev/null || true
  pkill -f "uvicorn agent_platform.api.student" 2>/dev/null || true
  sleep 1
  ls -la "${BACKUP}"
}

do_clean_l2() {
  echo "==> Clean L2 student_data"
  rm -rf "${ROOT}/student_data"
  mkdir -p "${ROOT}/student_data"
}

do_clean_l1_runtime() {
  echo "==> Clean L1 runtime (keep kp_catalog.json)"
  rm -f "${ROOT}/agent_platform/learning/question_bank/questions.db"
  rm -rf "${ROOT}/wiki_data"
  mkdir -p "${ROOT}/wiki_data/raw/kp"
  touch "${ROOT}/wiki_data/raw/.gitkeep"
}

do_clean_l0() {
  echo "==> Clean L0 runtime"
  mkdir -p "${ROOT}/skills_data"
  echo '{"records":[]}' > "${ROOT}/skills_data/memory_store.json"
  rm -f "${ROOT}/skills_data/experiences.jsonl" "${ROOT}/skills_data/curriculum_log.jsonl"
  for d in behavior_data calibration_data proactive_data tools_data perception_data; do
    rm -rf "${ROOT}/${d}"
    mkdir -p "${ROOT}/${d}"
  done
  rm -f "${ROOT}/_transcript_extract.txt" 2>/dev/null || true

  echo "==> Clean Hermes shell state"
  rm -f "${HOME}/.hermes/MEMORY.md" "${HOME}/.hermes/USER.md" "${HOME}/.hermes/USER.md.lock"
  rm -rf "${HOME}/.hermes/memories" "${HOME}/.hermes/sessions"
  rm -f "${HOME}/.hermes/state.db" "${HOME}/.hermes/state.db-shm" "${HOME}/.hermes/state.db-wal"
}

do_remount() {
  echo "==> Reinstall Hermes plugins"
  export AGENT_COMMUNITY_ROOT="${ROOT}"
  export PYTHONPATH="${ROOT}"
  export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${PATH}"
  bash "${ROOT}/agent_platform/integrations/hermes/install_plugin.sh"
  hermes doctor || true
}

do_init() {
  echo "==> Init single student g2-stu-01"
  export AGENT_COMMUNITY_ROOT="${ROOT}"
  export PYTHONPATH="${ROOT}"
  cd "${ROOT}"
  "${PY}" -m agent_platform.learning.cli_student init g2-stu-01 --from-defaults
  "${PY}" -m agent_platform.learning.cli_student onboard g2-stu-01 \
    --grade 三年级 --grade-level 3 --subject 数学
  "${PY}" -m agent_platform.learning.cli_student push rebuild g2-stu-01
  "${PY}" -c "from agent_platform.learning.bootstrap_family_alpha import ensure_family_alpha_content; print(ensure_family_alpha_content().to_dict())"
}

do_verify() {
  echo "==> Verify"
  export AGENT_COMMUNITY_ROOT="${ROOT}"
  export PYTHONPATH="${ROOT}"
  export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${PATH}"
  cd "${ROOT}"
  hermes doctor || true
  echo "--- student_data ---"
  find "${ROOT}/student_data" -maxdepth 2 -type f | head -20
  echo "--- kp_catalog units ---"
  "${PY}" -c "import json; d=json.load(open('agent_platform/learning/catalog/kp_catalog.json')); print([u['unit_id'] for u in d['units']])"
  echo "--- memory records ---"
  "${PY}" -c "import json; d=json.load(open('skills_data/memory_store.json')); print(len(d.get('records',[])))"
  echo "--- questions.db ---"
  ls -la agent_platform/learning/question_bank/questions.db 2>/dev/null || echo "(will be created on service start)"
  "${PY}" -m agent_platform.learning.cli_student show g2-stu-01
}

case "${phase}" in
  backup) do_backup ;;
  clean-l2) do_clean_l2 ;;
  clean-l1) do_clean_l1_runtime ;;
  clean-l0) do_clean_l0 ;;
  remount) do_remount ;;
  init) do_init ;;
  verify) do_verify ;;
  all)
    do_backup
    do_clean_l2
    do_clean_l1_runtime
    do_clean_l0
    do_remount
    do_init
    do_verify
    ;;
  *)
    echo "Usage: $0 [backup|clean-l2|clean-l1|clean-l0|remount|init|verify|all]" >&2
    exit 1
    ;;
esac

echo "==> Done (${phase})"
