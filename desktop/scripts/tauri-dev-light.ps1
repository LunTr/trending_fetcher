$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopDir = Resolve-Path (Join-Path $scriptDir "..")
$localAppData = [Environment]::GetFolderPath("LocalApplicationData")
$defaultCacheRoot = Join-Path $localAppData "trending_fetcher\tauri-target"
$cacheRoot = if ($env:TRENDING_FETCHER_CARGO_TARGET_DIR) {
    $env:TRENDING_FETCHER_CARGO_TARGET_DIR
}
else {
    Join-Path $defaultCacheRoot "target"
}

New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null

$env:CARGO_TARGET_DIR = $cacheRoot
$exitCode = 1

Write-Host "CARGO_TARGET_DIR=$env:CARGO_TARGET_DIR"
Write-Host "The Tauri cache is persistent. Run npm run tauri:clean to reclaim the space."

try {
    Push-Location $desktopDir
    npm.cmd run tauri dev
    $exitCode = if ($LASTEXITCODE -ne $null) { $LASTEXITCODE } else { 0 }
}
finally {
    Pop-Location
}

exit $exitCode
