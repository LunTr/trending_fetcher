$ErrorActionPreference = "Stop"

function Remove-SafeDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$AllowedRoot
    )

    $rootFull = [System.IO.Path]::GetFullPath($AllowedRoot).TrimEnd('\')
    $pathFull = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $rootPrefix = "$rootFull\"

    if ($pathFull.Length -le $rootFull.Length -or
        -not $pathFull.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to delete outside allowed root: $pathFull"
    }

    if (Test-Path -LiteralPath $pathFull) {
        Remove-Item -LiteralPath $pathFull -Recurse -Force
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopDir = Resolve-Path (Join-Path $scriptDir "..")
$tempRoot = [System.IO.Path]::GetTempPath()
$cacheRoot = Join-Path $tempRoot "trending_fetcher_tauri_target"

Remove-SafeDirectory -Path $cacheRoot -AllowedRoot $tempRoot
New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null

$env:CARGO_TARGET_DIR = Join-Path $cacheRoot "target"
$exitCode = 1

Write-Host "CARGO_TARGET_DIR=$env:CARGO_TARGET_DIR"
Write-Host "The temporary Tauri cache will be deleted when this session exits."

try {
    Push-Location $desktopDir
    npm run tauri dev
    $exitCode = if ($LASTEXITCODE -ne $null) { $LASTEXITCODE } else { 0 }
}
finally {
    Pop-Location
    Write-Host "Cleaning temporary Tauri cache..."
    Remove-SafeDirectory -Path $cacheRoot -AllowedRoot $tempRoot
}

exit $exitCode
