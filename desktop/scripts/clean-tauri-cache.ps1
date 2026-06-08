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
        try {
            Remove-Item -LiteralPath $pathFull -Recurse -Force
            Write-Host "Removed $pathFull"
        }
        catch {
            Write-Warning "Skipped locked cache path: $pathFull ($($_.Exception.Message))"
        }
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopDir = Resolve-Path (Join-Path $scriptDir "..")
$repoRoot = Resolve-Path (Join-Path $desktopDir "..")
$srcTauriDir = Resolve-Path (Join-Path $desktopDir "src-tauri")
$workspaceTarget = Join-Path $srcTauriDir "target"
$tempRoot = [System.IO.Path]::GetTempPath()
$ephemeralCache = Join-Path $tempRoot "trending_fetcher_tauri_target"
$checkCache = Join-Path $tempRoot "trending_fetcher_cargo_check_target"
$localAppData = [Environment]::GetFolderPath("LocalApplicationData")
$persistentCacheRoot = Join-Path $localAppData "trending_fetcher\tauri-target"

Remove-SafeDirectory -Path $workspaceTarget -AllowedRoot $srcTauriDir
Remove-SafeDirectory -Path $persistentCacheRoot -AllowedRoot $localAppData
Remove-SafeDirectory -Path $ephemeralCache -AllowedRoot $tempRoot
Remove-SafeDirectory -Path $checkCache -AllowedRoot $tempRoot

Get-ChildItem -LiteralPath $repoRoot -Directory -Recurse -Force -Filter "__pycache__" |
    ForEach-Object {
        Remove-SafeDirectory -Path $_.FullName -AllowedRoot $repoRoot
    }
