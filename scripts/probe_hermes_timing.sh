#!/usr/bin/env bash
set -euo pipefail
export AGENT_COMMUNITY_ROOT="${AGENT_COMMUNITY_ROOT:-/mnt/c/Users/Administrator/Desktop/agent_community}"
export PYTHONPATH="${AGENT_COMMUNITY_ROOT}"
export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${HOME}/.local/bin:${PATH}"
if [[ -f "${HOME}/.hermes/.env" ]]; then set -a; source "${HOME}/.hermes/.env"; set +a; fi

python3 <<'PY'
import os, time
os.chdir(os.path.expanduser("~"))
from agent_platform.voice.hermes_bridge import HermesBridge

bridge = HermesBridge(timeout_s=120.0, stable_after_s=3.0)

cases = [
    ("simple", "你好"),
    ("english_unit", "我想开始学习三年级英语第一单元，你能给我总体介绍下这个单元的内容么"),
]
for label, p in cases:
    t0 = time.perf_counter()
    first = None
    for ev in bridge.stream_ask(p):
        if ev.text_delta and first is None:
            first = time.perf_counter() - t0
        if ev.done:
            total = time.perf_counter() - t0
            tail = total - (first or total)
            print(f"{label}: total={total:.1f}s first_byte={first or 0:.1f}s tail={tail:.1f}s bridge_ms={ev.elapsed_ms:.0f}")
            break
PY
