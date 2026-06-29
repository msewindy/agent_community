#!/usr/bin/env bash
# WSL-only environment check for agent_community
set -euo pipefail

export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${HOME}/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

ROOT="${AGENT_COMMUNITY_ROOT:-/mnt/c/Users/Administrator/Desktop/agent_community}"

echo "=== WSL identity ==="
echo "user=$(whoami) home=${HOME}"

echo
echo "=== Hermes ==="
if command -v hermes >/dev/null 2>&1; then
  hermes --version
else
  echo "hermes not in PATH; searching..."
  find "${HOME}/.hermes" -maxdepth 4 -name hermes -type f 2>/dev/null | head -5 || true
fi

echo
echo "=== ~/.hermes ==="
ls -la "${HOME}/.hermes" | head -20
echo ".env: $([ -f "${HOME}/.hermes/.env" ] && echo present || echo missing)"

echo
echo "=== plugins ==="
if [[ -d "${HOME}/.hermes/plugins" ]]; then
  ls -la "${HOME}/.hermes/plugins"
else
  echo "no ${HOME}/.hermes/plugins"
fi

echo
echo "=== config enabled plugins/tools ==="
grep -A8 "^plugins:" "${HOME}/.hermes/config.yaml" 2>/dev/null | head -10 || true
grep -A8 "^tools:" "${HOME}/.hermes/config.yaml" 2>/dev/null | head -10 || true

echo
echo "=== Docker (user) ==="
if docker ps >/dev/null 2>&1; then
  docker ps -a --filter name=memverse
  docker images memverse-local:amd64 --format '{{.Repository}}:{{.Tag}} {{.Size}}' 2>/dev/null || true
else
  echo "docker not accessible for $(whoami)"
  sg docker -c "docker ps -a --filter name=memverse" 2>/dev/null || sudo docker ps -a --filter name=memverse 2>/dev/null || true
fi

echo
echo "=== Project ==="
echo "ROOT=${ROOT}"
test -f "${ROOT}/agent_platform/memory/accept_m2_us.py" && echo "accept_m2_us.py OK" || echo "accept_m2_us.py MISSING"

echo
echo "=== Python acceptance (quick import) ==="
export PYTHONPATH="${ROOT}"
if command -v python3 >/dev/null 2>&1; then
  python3 -c "import agent_platform.memory.service; print('memory import OK')" 2>&1 || true
fi
