# build_all.ps1 — Buduje wszystkie komponenty AegisVault (Windows)
#
# Użycie:
#   .\installer\build_all.ps1
#   .\installer\build_all.ps1 -SkipPyInstaller
#   .\installer\build_all.ps1 -ExtensionOnly
#   .\installer\build_all.ps1 -AppVersion "1.2.0"

param(
    [switch]$SkipPyInstaller,
    [switch]$ExtensionOnly,
    [string]$AppVersion = ""
)

$ErrorActionPreference = "Stop"
$RootDir = Resolve-Path "$PSScriptRoot\.."
Set-Location $RootDir

# ── Odczytaj wersję ───────────────────────────────────────────
if (-not $AppVersion) {
    $AppVersion = (python -c "import sys; sys.path.insert(0,'.'); from version import APP_VERSION; print(APP_VERSION)" 2>$null)
    if (-not $AppVersion) { $AppVersion = "1.0.0" }
}

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║       AegisVault — Build All Components          ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "Wersja:  $AppVersion" -ForegroundColor Yellow
Write-Host "Katalog: $RootDir" -ForegroundColor Yellow
Write-Host ""

# ── Krok 1: PyInstaller ───────────────────────────────────────
if (-not $ExtensionOnly -and -not $SkipPyInstaller) {
    Write-Host "━━━ [1/3] Budowanie aplikacji desktop (PyInstaller) ━━━" -ForegroundColor Cyan
    pip install -r requirements.txt -q
    pip install pyinstaller -q
    pyinstaller aegisvault.spec --noconfirm
    Write-Host ""
} else {
    Write-Host "[SKIP] PyInstaller pominięty`n" -ForegroundColor DarkGray
}

# ── Krok 2: Inno Setup Installer ─────────────────────────────
if (-not $ExtensionOnly) {
    Write-Host "━━━ [2/3] Budowanie instalatora Windows (Inno Setup) ━━━" -ForegroundColor Cyan

    # Szukaj iscc.exe w typowych lokalizacjach
    $isccCmd = Get-Command iscc -ErrorAction SilentlyContinue
    $isccFromPath = if ($isccCmd) { $isccCmd.Source } else { $null }
    $InnoPaths = @(
        "C:\Program Files (x86)\Inno Setup 6\iscc.exe",
        "C:\Program Files\Inno Setup 6\iscc.exe",
        $isccFromPath
    ) | Where-Object { $_ -and (Test-Path $_) }

    if ($InnoPaths.Count -eq 0) {
        Write-Host "[WARN] Inno Setup nie znaleziony — pomijam instalator .exe" -ForegroundColor Yellow
        Write-Host "       Pobierz: https://jrsoftware.org/isinfo.php" -ForegroundColor Yellow
    } else {
        $IsccExe = $InnoPaths[0]
        Write-Host "iscc.exe: $IsccExe"
        & $IsccExe /DAppVersion=$AppVersion "installer\windows\aegisvault.iss"
        Write-Host ""
    }
}

# ── Krok 3: Rozszerzenie przeglądarkowe ──────────────────────
Write-Host "━━━ [3/3] Pakowanie rozszerzenia przeglądarkowego ━━━" -ForegroundColor Cyan
& powershell -ExecutionPolicy Bypass -File "installer\extension\build_extension.ps1" -RootDir $RootDir

# ── Podsumowanie ──────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║                  BUILD COMPLETE                  ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "Pliki w dist\:" -ForegroundColor Yellow
Get-ChildItem "dist\" -ErrorAction SilentlyContinue | Format-Table Name, Length -AutoSize
