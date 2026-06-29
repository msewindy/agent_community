# Reorganize repo to memory + evolution focus (run manually when ready)
# Usage: powershell -ExecutionPolicy Bypass -File scripts/reorganize_to_temp.ps1

$ErrorActionPreference = "Stop"
$Root = "c:\Users\Administrator\Desktop\agent_community"
Set-Location $Root

$Temp = Join-Path $Root "temp"
New-Item -ItemType Directory -Force -Path `
    "$Temp\research_repos", `
    "$Temp\data", `
    "$Temp\design_archive", `
    "$Temp\hermes_docs" | Out-Null

$keepRepos = @("MemVerse", "hermes-agent", "leaper-agent", "reflexion", "MemOS")
Get-ChildItem "$Root\research_repos" -Directory | Where-Object { $_.Name -notin $keepRepos } | ForEach-Object {
    Write-Host "Moving $($_.Name) -> temp/research_repos/"
    Move-Item $_.FullName "$Temp\research_repos\$($_.Name)"
}

@("perception_data", "calibration_data", "tools_data", "wiki_data") | ForEach-Object {
    $p = Join-Path $Root $_
    if (Test-Path $p) {
        Write-Host "Moving $_ -> temp/data/"
        Move-Item $p "$Temp\data\$_"
    }
}

Get-ChildItem $Root -File -Filter "*.pdf" -ErrorAction SilentlyContinue | ForEach-Object {
    Move-Item $_.FullName "$Temp\design_archive\"
}
Get-ChildItem $Root -File -Filter "Hermes-Agent*.md" -ErrorAction SilentlyContinue | ForEach-Object {
    Move-Item $_.FullName "$Temp\hermes_docs\"
}

Write-Host "Reorganization complete. Kept research_repos:"
Get-ChildItem "$Root\research_repos" -Directory | Select-Object -ExpandProperty Name
