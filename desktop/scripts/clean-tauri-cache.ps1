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
        Write-Host "Removed $pathFull"
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopDir = Resolve-Path (Join-Path $scriptDir "..")
$srcTauriDir = Resolve-Path (Join-Path $desktopDir "src-tauri")
$workspaceTarget = Join-Path $srcTauriDir "target"
$tempRoot = [System.IO.Path]::GetTempPath()
$ephemeralCache = Join-Path $tempRoot "trending_fetcher_tauri_target"

Remove-SafeDirectory -Path $workspaceTarget -AllowedRoot $srcTauriDir
Remove-SafeDirectory -Path $ephemeralCache -AllowedRoot $tempRoot
