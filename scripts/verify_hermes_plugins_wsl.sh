#!/usr/bin/env bash
set -euo pipefail
export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${PATH}"
export PYTHONPATH="${AGENT_COMMUNITY_ROOT:-/mnt/c/Users/Administrator/Desktop/agent_community}"
export HERMES_HOME="${HOME}/.hermes"
python3 <<'PY'
import os
os.environ["HERMES_HOME"] = os.path.expanduser("~/.hermes")
from hermes_cli.plugins import PluginManager
m = PluginManager()
m.discover_and_load(force=True)
names = sorted(m._plugins.keys())
ok_m = "agent-memverse" in names
ok_e = "agent-evolution" in names
print("agent-memverse loaded:", ok_m)
print("agent-evolution loaded:", ok_e)
if not (ok_m and ok_e):
    raise SystemExit(1)
PY
