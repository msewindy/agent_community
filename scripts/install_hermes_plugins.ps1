# Install agent_community Hermes plugins (Windows junction/symlink)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$HermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA "hermes" }
$PluginsDir = Join-Path $HermesHome "plugins"
$SrcBase = Join-Path $Root "agent_platform\integrations\hermes"

New-Item -ItemType Directory -Force -Path $PluginsDir | Out-Null

$plugins = @(
    "agent-memverse",
    "agent-evolution"
)

foreach ($name in $plugins) {
    $dir = $name -replace "-", "_"
    $src = Join-Path $SrcBase $dir
    if (-not (Test-Path $src)) {
        Write-Host "SKIP $name — missing $src" -ForegroundColor Yellow
        continue
    }
    $dest = Join-Path $PluginsDir $name
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue }
    New-Item -ItemType Junction -Path $dest -Target $src | Out-Null
    Set-Content -Path (Join-Path $src "AGENT_COMMUNITY_ROOT") -Value $Root -NoNewline
    Write-Host "  $dest -> $src"
}

Write-Host ""
Write-Host "Enable in Hermes config (~/.hermes/config.yaml or %LOCALAPPDATA%\hermes\config.yaml):"
Write-Host "  plugins.enabled: [agent-memverse, agent-evolution]"
Write-Host "  tools.enabled: [agent_memory, agent_evolution]"
Write-Host ""
Write-Host "CLI:"
Write-Host "  hermes plugins enable agent-memverse"
Write-Host "  hermes plugins enable agent-evolution"
Write-Host "  hermes tools enable agent_memory"
Write-Host "  hermes tools enable agent_evolution"
