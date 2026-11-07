<#
  Builds the Class of '09 PS5 app folder (eboot.bin + sce_sys + sce_module + assets).

  The real build runs inside WSL2 through kit/build_class09.sh, which uses the
  ps5-homebrew-starter pipeline (signed eboot, clean-room libc.prx). A raw
  ps5-payload-sdk ELF is no longer produced: directory-style app folders are
  what ShadowMountPlus launches.

  Usage:
    powershell -ExecutionPolicy Bypass -File build_ps5.ps1
    powershell -ExecutionPolicy Bypass -File build_ps5.ps1 -NoCopy

  Output:
    ps5-homebrew\kit\dist\PPSA09010\            built app folder
    ps5-homebrew\kit\dist\PPSA09010.zip         built app ZIP
    ps5-homebrew\dist\PPSA09010\                copied deliverable (unless -NoCopy)
    ps5-homebrew\dist\ClassOf09-PS5-PPSA09010.zip
#>
param(
    [switch]$NoCopy
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Fail([string]$Message) {
    Write-Host "build_ps5: $Message" -ForegroundColor Red
    exit 1
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    Fail "WSL was not found. Install WSL2 with a Linux distribution first."
}

# Run the kit build through WSL. The script itself re-executes from a
# space-free symlink when the project path contains spaces.
$wslScript = (wsl.exe wslpath -a ("{0}/kit/build_class09.sh" -f $here)).Trim()
if (-not $wslScript) { Fail "could not resolve the kit path in WSL." }

wsl.exe bash -lc "bash '$wslScript'"
if ($LASTEXITCODE -ne 0) { Fail "the WSL build failed (exit $LASTEXITCODE)." }

$built = Join-Path $here "kit\dist\PPSA09010"
$builtZip = Join-Path $here "kit\dist\PPSA09010.zip"
if (-not (Test-Path $built)) { Fail "the build did not produce $built." }
if (-not (Test-Path $builtZip)) { Fail "the build did not produce $builtZip." }

if (-not $NoCopy) {
    $dest = Join-Path $here "dist"
    New-Item -ItemType Directory $dest -Force | Out-Null
    Remove-Item (Join-Path $dest "PPSA09010") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $dest "ClassOf09-PS5-PPSA09010.zip") -Force -ErrorAction SilentlyContinue
    Move-Item $built $dest
    Move-Item $builtZip (Join-Path $dest "ClassOf09-PS5-PPSA09010.zip")
    Write-Host "Deliverable: $(Join-Path $dest 'PPSA09010')"
}

$files = Get-ChildItem (Join-Path $here "dist\PPSA09010") -Recurse -File -ErrorAction SilentlyContinue
if ($files) {
    Write-Host ("App folder: {0} files, {1:N0} bytes" -f $files.Count, ($files | Measure-Object Length -Sum).Sum)
}
