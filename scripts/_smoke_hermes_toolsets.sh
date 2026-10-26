#!/usr/bin/env bash
set -uo pipefail
export PATH="/usr/bin:/bin:${HOME}/.hermes/hermes-agent/venv/bin:${HOME}/.local/bin:${PATH}"
export AGENT_COMMUNITY_ROOT=/mnt/d/project/agent_community

hermes chat -q '用一句话跟我说你好' -Q --provider deepseek --model deepseek-v4-flash \
  >/tmp/hermes_smoke_out.log 2>/tmp/hermes_smoke_err.log

echo "==== stdout ===="
tail -n 30 /tmp/hermes_smoke_out.log
echo "==== Unknown toolsets / discovery ===="
grep -E 'Unknown toolsets|Plugin discovery|agent-student plugin' /tmp/hermes_smoke_err.log \
  /home/administrator/.hermes/logs/agent.log | tail -n 40
