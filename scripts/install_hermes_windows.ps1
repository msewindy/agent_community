# Install Hermes Agent on Windows (wraps upstream install.ps1)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$InstallScript = Join-Path $Root "research_repos\hermes-agent\scripts\install.ps1"

if (-not (Test-Path $InstallScript)) {
    Write-Error "Missing $InstallScript — ensure research_repos/hermes-agent is present."
}

Write-Host "==> Running Hermes install.ps1 -SkipSetup"
& $InstallScript -SkipSetup

Write-Host ""
Write-Host "==> Installing agent_community plugins"
& (Join-Path $Root "scripts\install_hermes_plugins.ps1")

Write-Host ""
Write-Host "Next: configure DeepSeek API in %LOCALAPPDATA%\hermes\.env"
Write-Host "See docs/M0-hermes-setup-windows.md"
