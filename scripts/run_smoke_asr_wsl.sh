#!/usr/bin/env bash
set -euo pipefail
ROOT="/mnt/c/Users/Administrator/Desktop/agent_community"
export AGENT_COMMUNITY_ROOT="$ROOT"
export PYTHONPATH="$ROOT"
PY="${HOME}/.hermes/hermes-agent/venv/bin/python"
cd "$ROOT"
if [[ ! -f /tmp/asr_test_hello.wav ]]; then
  curl -sfL -o /tmp/asr_test_hello.wav \
    'https://dashscope.oss-cn-beijing.aliyuncs.com/samples/audio/paraformer/hello_world_female2.wav'
fi
exec "$PY" scripts/smoke_student_asr.py
