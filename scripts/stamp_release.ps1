<#
.SYNOPSIS
    Stamp PinhOS release metadata (version, build_id, UTC build_timestamp) atomically
    into version.json and synchronized source literals before tagging/deploying (Refs #25).
.EXAMPLE
    .\scripts\stamp_release.ps1 -Version "1.0.0-alpha.4.2"
    .\scripts\stamp_release.ps1 -Version "1.0.0-alpha.4.2" -BuildSeq 2 -CreateTag
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+([-.][A-Za-z0-9.]+)?$')]
    [string]$Version,
    [int]$BuildSeq = 0,
    [switch]$CreateTag,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ManifestPath = Join-Path $RepoRoot "version.json"

if (-not (Test-Path $ManifestPath)) {
    throw "version.json not found at $ManifestPath"
}

$nowUtc = (Get-Date).ToUniversalTime()
$dateStamp = $nowUtc.ToString("yyyyMMdd")
$isoUtc = $nowUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")

$rawJson = Get-Content $ManifestPath -Raw
$obj = $rawJson | ConvertFrom-Json
$oldVer = [string]$obj.version
$oldBuild = [string]$obj.build_id

if ($BuildSeq -le 0) {
    if ($oldBuild -match "^$dateStamp\.(\d+)$") {
        $BuildSeq = [int]$Matches[1] + 1
    } else {
        $BuildSeq = 1
    }
}
$newBuildId = "$dateStamp.$BuildSeq"

Write-Host "[stamp_release] $oldVer ($oldBuild) -> $Version ($newBuildId @ $isoUtc)" -ForegroundColor Cyan

# Update version.json preserving readable formatting
$updatedJson = $rawJson `
    -replace '("version"\s*:\s*")[^"]+(")', "`${1}$Version`${2}" `
    -replace '("build_id"\s*:\s*")[^"]+(")', "`${1}$newBuildId`${2}" `
    -replace '("build_timestamp"\s*:\s*")[^"]+(")', "`${1}$isoUtc`${2}"

# Files that carry fallback/display version strings
$SyncFiles = @(
    "core\config.py",
    "tests\selftest.py",
    "picocalc.ps1",
    "web\server.py",
    "web\static\index.html",
    "web\static\app.js"
)

if ($DryRun) {
    Write-Host "[stamp_release] DryRun enabled; no files modified." -ForegroundColor Yellow
    exit 0
}

[System.IO.File]::WriteAllText($ManifestPath, $updatedJson, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "  [OK] version.json" -ForegroundColor Green

$escapedOld = [regex]::Escape($oldVer)
foreach ($rel in $SyncFiles) {
    $fp = Join-Path $RepoRoot $rel
    if (-not (Test-Path $fp)) { continue }
    $txt = Get-Content $fp -Raw
    if ($txt -match $escapedOld) {
        $newTxt = $txt -replace $escapedOld, $Version
        [System.IO.File]::WriteAllText($fp, $newTxt, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host "  [OK] $rel" -ForegroundColor Green
    }
}

# Verify valid JSON
$check = (Get-Content $ManifestPath -Raw) | ConvertFrom-Json
if ($check.version -ne $Version -or $check.build_id -ne $newBuildId) {
    throw "Post-stamp verification failed for version.json"
}

if ($CreateTag) {
    $tagName = "v$Version"
    Write-Host "[stamp_release] Creating annotated git tag $tagName..." -ForegroundColor Cyan
    & git -C $RepoRoot tag -a $tagName -m "Release $tagName (build $newBuildId)"
    Write-Host "[stamp_release] Tag $tagName created. Deploy with '.\picocalc.ps1 upload_and_start -Force' before pushing." -ForegroundColor Green
}
