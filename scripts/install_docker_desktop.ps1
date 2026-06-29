# Install Docker Desktop on Windows (for MemVerse M2)
# Usage: powershell -ExecutionPolicy Bypass -File scripts/install_docker_desktop.ps1
#
# If winget/download fails (network), open in browser:
#   https://www.docker.com/products/docker-desktop/
# After install: start "Docker Desktop", wait until whale icon is steady, then:
#   powershell -File scripts\run_memverse_docker.ps1 -Build -Accept

$ErrorActionPreference = "Stop"

function Test-DockerInstalled {
    $paths = @(
        "C:\Program Files\Docker\Docker\resources\bin\docker.exe",
        "$env:ProgramFiles\Docker\Docker\resources\bin\docker.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$existing = Test-DockerInstalled
if ($existing) {
    Write-Host "Docker already installed at $existing"
    & $existing --version
    exit 0
}

Write-Host "==> Trying winget install Docker.DockerDesktop ..."
try {
    winget install -e --id Docker.DockerDesktop `
        --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Install finished. Start Docker Desktop from Start menu, then re-run run_memverse_docker.ps1"
        exit 0
    }
} catch {
    Write-Host "winget failed: $($_.Exception.Message)"
}

$installer = Join-Path $env:TEMP "DockerDesktopInstaller.exe"
Write-Host "==> Trying curl download to $installer ..."
curl.exe -L --retry 3 --retry-delay 5 -o $installer `
    "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $installer) -or (Get-Item $installer).Length -lt 1000000) {
    Write-Host ""
    Write-Host "Automatic download failed (network may block desktop.docker.com)." -ForegroundColor Yellow
    Write-Host "Manual steps:"
    Write-Host "  1. Download Docker Desktop Installer from https://www.docker.com/products/docker-desktop/"
    Write-Host "  2. Run installer, enable WSL2 backend if prompted"
    Write-Host "  3. Reboot if required, start Docker Desktop"
    Write-Host "  4. powershell -File scripts\run_memverse_docker.ps1 -Build -Accept"
    exit 1
}

Write-Host "==> Running installer (silent) ..."
Start-Process -FilePath $installer -ArgumentList "install", "--quiet", "--accept-license" -Wait
Write-Host "Done. Start Docker Desktop, wait until ready, then:"
Write-Host "  powershell -File scripts\run_memverse_docker.ps1 -Build -Accept"
