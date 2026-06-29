# M2 memory acceptance on Windows
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "agent_platform\memory\accept_m2_us.py"))) {
    $Root = "c:\Users\Administrator\Desktop\agent_community"
}
Set-Location $Root
$env:PYTHONPATH = $Root
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

Write-Host "==> pip install memory deps"
python -m pip install -r agent_platform/requirements-memory.txt -q

Write-Host "==> pytest (memory subset)"
Set-Location agent_platform
python -m pytest `
    tests/test_audit.py `
    tests/test_adapter_memverse.py `
    tests/test_adapter_mock.py `
    tests/test_contracts.py `
    tests/test_envelope.py `
    tests/test_gate.py `
    tests/test_memory_service_mock.py `
    tests/test_memory_panel.py `
    tests/test_mock_persist.py `
    tests/test_hermes_tools.py `
    -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location $Root
Write-Host "==> accept_m2_us"
python agent_platform/memory/accept_m2_us.py
exit $LASTEXITCODE
