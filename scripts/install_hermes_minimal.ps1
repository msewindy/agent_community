# Minimal Hermes install from local research_repos (when upstream install.ps1 fails)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$HermesHome = Join-Path $env:LOCALAPPDATA "hermes"
$AgentDir = Join-Path $HermesHome "hermes-agent"
$Repo = Join-Path $Root "research_repos\hermes-agent"

if (-not (Test-Path $Repo)) {
    Write-Error "Missing $Repo"
}

New-Item -ItemType Directory -Force -Path $HermesHome | Out-Null

if (-not (Test-Path $AgentDir)) {
    Write-Host "==> Copy hermes-agent to $AgentDir"
    Copy-Item -Path $Repo -Destination $AgentDir -Recurse -Force
} else {
    Write-Host "==> Using existing $AgentDir"
}

$Venv = Join-Path $AgentDir "venv"
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    Write-Host "==> Create venv"
    python -m venv $Venv
}

$Py = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"

Write-Host "==> pip install hermes-agent (editable)"
& $Pip install -e $AgentDir -q

$BinDir = Join-Path $HermesHome "bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$HermesExe = Join-Path $Venv "Scripts\hermes.exe"
if (Test-Path $HermesExe) {
    Copy-Item $HermesExe (Join-Path $BinDir "hermes.exe") -Force
    Write-Host "Hermes CLI: $BinDir\hermes.exe"
    Write-Host "Add to PATH: $BinDir"
} else {
    Write-Host "WARN: hermes.exe not found in venv — check pip install output"
}

Write-Host ""
& (Join-Path $Root "scripts\install_hermes_plugins.ps1")
