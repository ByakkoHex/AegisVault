param([string]$Version = "")

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$AppVersion = $Version
if (-not $AppVersion) {
    try {
        $vline = Select-String -Path "version.py" -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
        if ($vline) { $AppVersion = $vline.Matches[0].Groups[1].Value }
    } catch {}
}
if (-not $AppVersion) { $AppVersion = "1.0.0" }

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AegisVault Build  v$AppVersion" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/3] Installing dependencies + PyInstaller..." -ForegroundColor Cyan
Write-Host "      pip install -r requirements.txt..." -ForegroundColor DarkGray
pip install -r requirements.txt --quiet
$piCheck = python -c "import PyInstaller; print('ok')" 2>&1
if ($piCheck -ne "ok") {
    Write-Host "      Installing PyInstaller..." -ForegroundColor Yellow
    pip install pyinstaller --quiet
}
Write-Host "      OK" -ForegroundColor Green

Write-Host ""
Write-Host "[2/3] Bundling app (PyInstaller)..." -ForegroundColor Cyan
Write-Host "      This may take a few minutes..." -ForegroundColor DarkGray

python -m PyInstaller aegisvault.spec --noconfirm --log-level WARN

if (-not (Test-Path "dist\AegisVault\AegisVault.exe")) {
    Write-Host "[ERROR] dist\AegisVault\AegisVault.exe not found." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$distSize = "{0:N0} MB" -f ((Get-ChildItem "dist\AegisVault" -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Write-Host "      OK  ($distSize)" -ForegroundColor Green

Write-Host ""
Write-Host "[3/3] Building installer (Inno Setup)..." -ForegroundColor Cyan

# Szukaj iscc.exe: typowe sciezki + rejestr
$IsccExe = $null
$candidates = @(
    "C:\Program Files (x86)\Inno Setup 6\iscc.exe",
    "C:\Program Files\Inno Setup 6\iscc.exe",
    "C:\Program Files (x86)\Inno Setup 5\iscc.exe"
)
foreach ($c in $candidates) {
    if (Test-Path $c) { $IsccExe = $c; break }
}
if (-not $IsccExe) {
    try {
        $regPath = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1" -ErrorAction Stop
        $dir = $regPath.InstallLocation
        if (Test-Path "$dir\iscc.exe") { $IsccExe = "$dir\iscc.exe" }
    } catch {}
}
if (-not $IsccExe) {
    try {
        $IsccExe = (Get-Command iscc -ErrorAction Stop).Source
    } catch {}
}

if (-not $IsccExe) {
    Write-Host ""
    Write-Host "  Inno Setup not found. Options:" -ForegroundColor Yellow
    Write-Host "  1. Install from: https://jrsoftware.org/isinfo.php" -ForegroundColor Cyan
    Write-Host "  2. Or right-click installer\windows\aegisvault.iss -> Compile" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  App is ready in: dist\AegisVault\AegisVault.exe" -ForegroundColor Green
} else {
    Write-Host "  Using: $IsccExe" -ForegroundColor DarkGray
    & $IsccExe /DAppVersion=$AppVersion "installer\windows\aegisvault.iss"
    $setupFile = "dist\AegisVault-Setup-$AppVersion.exe"
    if (Test-Path $setupFile) {
        $setupSize = "{0:N0} MB" -f ((Get-Item $setupFile).Length / 1MB)
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Green
        Write-Host "  DONE!" -ForegroundColor Green
        Write-Host "  Installer: $setupFile  ($setupSize)" -ForegroundColor Green
        Write-Host "  Ready to share - no Python required." -ForegroundColor White
        Write-Host "========================================" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Inno Setup did not produce .exe" -ForegroundColor Red
    }
}

Write-Host ""
Read-Host "Press Enter to exit"