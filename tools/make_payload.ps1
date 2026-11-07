<#
  Builds the exact folder tree you copy to the PS5.

  It never modifies or redistributes the game: it copies the files listed in
  build/assets_required.txt out of *your* game folder, plus the exported
  script.json and any video frame caches you have already extracted.

  Result (mirrors what the runtime expects at /data/class09):

    dist/class09/script.json
    dist/class09/game/<original relative paths>
    dist/class09/videos/<name>/frame_0000.jpg ...
    dist/class09/saves/                (empty, created at runtime)

  Usage:
    powershell -ExecutionPolicy Bypass -File tools\make_payload.ps1 `
        -Game "C:\Users\Admin\Desktop\Class of 09\Class of 09\game"
#>
param(
    [string]$Game = "C:\Users\Admin\Desktop\Class of 09\Class of 09\game",
    [string]$Out  = "",
    [switch]$SkipVideos
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
if (-not $Out) { $Out = Join-Path $root "dist\class09" }

$listPath = Join-Path $root "build\assets_required.txt"
if (-not (Test-Path $listPath)) {
    throw "Missing $listPath - run tools\export_script.py first."
}
if (-not (Test-Path $Game)) { throw "Game folder not found: $Game" }

$gameRoot = (Resolve-Path $Game).Path
$destGame = Join-Path $Out "game"
New-Item -ItemType Directory -Force -Path $destGame | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Out "saves") | Out-Null

$files = Get-Content $listPath | Where-Object { $_.Trim() -ne "" }
$copied = 0
$bytes = 0
$missing = @()

foreach ($rel in $files) {
    $rel = $rel.Trim().Replace('/','\')
    $src = Join-Path $gameRoot $rel
    if (-not (Test-Path -LiteralPath $src)) { $missing += $rel; continue }
    $dst = Join-Path $destGame $rel
    $dir = Split-Path -Parent $dst
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    Copy-Item -LiteralPath $src -Destination $dst -Force
    $copied++
    $bytes += (Get-Item -LiteralPath $src).Length
}

$script = Join-Path $root "build\script.json"
if (-not (Test-Path $script)) { throw "Missing $script" }
Copy-Item $script (Join-Path $Out "script.json") -Force

if (-not $SkipVideos) {
    $vids = Join-Path $root "build\videos"
    if (Test-Path $vids) {
        Copy-Item $vids (Join-Path $Out "videos") -Recurse -Force
    } else {
        Write-Warning "build\videos not found - intro/splash will be skipped on the console."
    }
}

$sdk = Join-Path $root "ClassOf09.elf"
if (Test-Path $sdk) { Copy-Item $sdk $Out -Force }

Write-Host ""
Write-Host ("Copied {0}/{1} files, {2:N1} MB" -f $copied, $files.Count, ($bytes/1MB))
if ($missing.Count) {
    Write-Warning ("Missing {0} file(s):" -f $missing.Count)
    $missing | ForEach-Object { Write-Warning "  $_" }
}
Write-Host ""
Write-Host "Package ready at: $Out"
Write-Host "Copy that folder to the console as /data/class09 (FTP, USB or the payload's file manager)."
