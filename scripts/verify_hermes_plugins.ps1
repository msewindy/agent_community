# Verify Hermes plugins load agent-memverse + agent-evolution
$ErrorActionPreference = "Stop"
$Root = "c:\Users\Administrator\Desktop\agent_community"
$env:HERMES_HOME = Join-Path $env:LOCALAPPDATA "hermes"
$env:AGENT_COMMUNITY_ROOT = $Root
$env:PYTHONPATH = $Root
$env:PYTHONIOENCODING = "utf-8"
$Py = Join-Path $env:HERMES_HOME "hermes-agent\venv\Scripts\python.exe"

Write-Host "==> Plugin discovery test"
$env:PYTHONUTF8 = "1"
& $Py -c @"
import os
os.environ['HERMES_HOME'] = r'$env:HERMES_HOME'
os.environ['AGENT_COMMUNITY_ROOT'] = r'$Root'
from hermes_cli.plugins import PluginManager
m = PluginManager()
m.discover_and_load(force=True)
hooks = getattr(m, '_hooks', {})
print('hooks:', sorted(hooks.keys()))
for name in ('pre_llm_call', 'post_llm_call'):
    if name in hooks:
        print(f'  {name}: {len(hooks[name])} callback(s)')
tools = [t.get('name') for t in getattr(m, '_tools', []) if isinstance(t, dict)]
print('tools sample:', [t for t in tools if t and 'evolution' in t or t and 'memory' in t][:10])
"@

Write-Host ""
Write-Host "==> US-3 reminder (manual, needs DeepSeek API in %LOCALAPPDATA%\hermes\.env)"
Write-Host "  1. hermes chat"
Write-Host "  2. Ask agent to agent_memory_write preference"
Write-Host "  3. Restart hermes chat and agent_memory_search"
Write-Host "See docs/M0-hermes-setup-windows.md section 4"
