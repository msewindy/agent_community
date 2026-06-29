#!/usr/bin/env bash
set -euo pipefail

service docker start 2>/dev/null || true

ROOT="/mnt/c/Users/Administrator/Desktop/agent_community"
IMAGE="${MEMVERSE_IMAGE:-memverse-local:amd64}"

load_env() {
  local candidates=(
    "${HOME}/.hermes/.env"
    "/home/administrator/.hermes/.env"
    "/mnt/c/Users/Administrator/AppData/Local/hermes/.env"
  )
  for f in "${candidates[@]}"; do
    if [[ -f "${f}" ]]; then
      set -a
      # shellcheck disable=SC1090
      source "${f}"
      set +a
      export OPENAI_API_KEY="${OPENAI_API_KEY:-${DEEPSEEK_API_KEY:-}}"
      export OPENAI_API_BASE="${OPENAI_API_BASE:-https://api.deepseek.com/v1}"
      export OPENAI_MODEL="${OPENAI_MODEL:-deepseek-chat}"
      export OPENAI_EMBEDDING_MODEL="${OPENAI_EMBEDDING_MODEL:-text-embedding-3-small}"
      return 0
    fi
  done
  return 1
}

echo "==> docker build ${IMAGE}"
docker build -t "${IMAGE}" "${ROOT}/research_repos/MemVerse"

if [[ "${1:-}" == "--build-only" ]]; then
  echo "Build complete (--build-only)."
  exit 0
fi

if ! load_env; then
  echo "ERROR: no Hermes .env found." >&2
  echo "Create ~/.hermes/.env with OPENAI_API_KEY / OPENAI_API_BASE, then re-run." >&2
  exit 1
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "ERROR: OPENAI_API_KEY or DEEPSEEK_API_KEY missing in .env" >&2
  exit 1
fi

docker rm -f memverse 2>/dev/null || true

echo "==> docker run memverse"
docker run -d --name memverse \
  -p 8000:8000 -p 5250:5250 \
  -e OPENAI_API_KEY \
  -e OPENAI_API_BASE \
  -e OPENAI_MODEL \
  -e OPENAI_EMBEDDING_MODEL \
  "${IMAGE}"

echo "==> waiting for http://127.0.0.1:8000"
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:8000/docs" >/dev/null 2>&1; then
    echo "MemVerse FastAPI is up"
    docker ps --filter name=memverse
    exit 0
  fi
  sleep 5
done

echo "timeout waiting for MemVerse" >&2
docker logs memverse 2>&1 | tail -40
exit 1
