#!/usr/bin/env bash
set -euo pipefail
export AGENT_COMMUNITY_ROOT="${AGENT_COMMUNITY_ROOT:-/mnt/c/Users/Administrator/Desktop/agent_community}"
export PYTHONPATH="${AGENT_COMMUNITY_ROOT}"
export PATH="${HOME}/.hermes/hermes-agent/venv/bin:${HOME}/.local/bin:${PATH}"

# load API keys
if [[ -f "${HOME}/.hermes/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${HOME}/.hermes/.env"
  set +a
fi

echo "=== import student_tools ==="
python3 -c "from agent_platform.integrations.hermes.student_tools import register_student_hermes_tools; print('import ok')"

echo "=== deepseek API ping ==="
python3 <<'PY'
import os, urllib.request, json
key = os.environ.get("DEEPSEEK_API_KEY", "")
base = (os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
if not key:
    print("NO DEEPSEEK_API_KEY")
else:
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=json.dumps({
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 5,
        }).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("deepseek ok", r.status)
    except Exception as e:
        print("deepseek FAIL:", type(e).__name__, e)
PY

echo "=== hermes chat quick (60s) ==="
timeout 60 hermes chat -q "你好" -Q --provider deepseek --model deepseek-chat > /tmp/hermes_out.txt 2> /tmp/hermes_err.txt || echo "hermes exit=$?"
echo "--- stdout tail ---"
tail -5 /tmp/hermes_out.txt 2>/dev/null || true
echo "--- stderr tail ---"
tail -30 /tmp/hermes_err.txt 2>/dev/null || true

echo "=== HermesBridge.ask (90s) ==="
python3 <<'PY'
import os
os.chdir(os.path.expanduser("~"))
from agent_platform.voice.hermes_bridge import HermesBridge
b = HermesBridge(timeout_s=90.0, stable_after_s=3.0)
try:
    r = b.ask("三年级英语第一单元介绍一下")
    print("reply len:", len(r.text))
    print("session:", r.session_id)
    print("elapsed_ms:", r.elapsed_ms)
    print("preview:", r.text[:200])
except Exception as e:
    print("FAIL:", type(e).__name__, e)
PY
