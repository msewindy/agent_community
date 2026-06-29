# MemVerse Docker on Windows (M2 D1)
# Usage: powershell -ExecutionPolicy Bypass -File scripts/run_memverse_docker.ps1 [-Build] [-Down]
param(
    [switch]$Build,
    [switch]$Down,
    [switch]$Accept
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Import-HermesEnv {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "hermes\.env"),
        (Join-Path $env:USERPROFILE ".hermes\.env")
    )
    foreach ($path in $candidates) {
        if (-not (Test-Path $path)) { continue }
        Get-Content $path | ForEach-Object {
            $line = $_.Trim()
            if (-not $line -or $line.StartsWith("#")) { return }
            $eq = $line.IndexOf("=")
            if ($eq -lt 1) { return }
            $name = $line.Substring(0, $eq).Trim()
            $value = $line.Substring($eq + 1).Trim().Trim('"').Trim("'")
            Set-Item -Path "Env:$name" -Value $value
        }
        break
    }
    if (-not $env:OPENAI_API_KEY -and $env:DEEPSEEK_API_KEY) {
        $env:OPENAI_API_KEY = $env:DEEPSEEK_API_KEY
    }
    if (-not $env:OPENAI_API_BASE) {
        $env:OPENAI_API_BASE = "https://api.deepseek.com/v1"
    }
    if (-not $env:OPENAI_MODEL) {
        $env:OPENAI_MODEL = "deepseek-chat"
    }
    if (-not $env:OPENAI_EMBEDDING_MODEL) {
        $env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
    }
    if (-not $env:OPENAI_API_KEY) {
        throw "Missing OPENAI_API_KEY / DEEPSEEK_API_KEY in %LOCALAPPDATA%\hermes\.env"
    }
}

function Test-DockerReady {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        throw "docker not found. Install Docker Desktop, then restart this shell."
    }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon not running. Start Docker Desktop and wait until it is ready."
    }
}

Import-HermesEnv
Test-DockerReady

$composeFile = Join-Path $Root "agent_platform\deploy\memverse\docker-compose.yml"
$memverseDir = Join-Path $Root "research_repos\MemVerse"

if ($Down) {
    Write-Host "==> Stopping MemVerse container"
    docker compose -f $composeFile down
    exit $LASTEXITCODE
}

if ($Build -or -not (docker image inspect memverse-local:amd64 2>$null)) {
    Write-Host "==> Building memverse-local:amd64 (first run may take several minutes)"
    docker build -t memverse-local:amd64 $memverseDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "==> Starting MemVerse (ports 8000, 5250)"
docker compose -f $composeFile up -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Waiting for http://127.0.0.1:8000 ..."
$deadline = (Get-Date).AddMinutes(3)
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/docs" -UseBasicParsing -TimeoutSec 5
        if ($r.StatusCode -eq 200) {
            Write-Host "MemVerse FastAPI is up."
            break
        }
    } catch {
        Start-Sleep -Seconds 3
    }
}

if ($Accept) {
    Write-Host "==> accept_m2_us --memverse"
    $env:PYTHONPATH = $Root
    python -m pip install -r (Join-Path $Root "agent_platform\requirements-memory.txt") -q
    python (Join-Path $Root "agent_platform\memory\accept_m2_us.py") --memverse
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Next: python agent_platform\memory\accept_m2_us.py --memverse"
Write-Host "Or:  powershell -File scripts\run_memverse_docker.ps1 -Accept"
