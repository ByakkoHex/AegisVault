# post_install.ps1 — Rejestracja Native Messaging Host po instalacji
# Parametr: $args[0] = ścieżka instalacji (np. C:\Users\user\AppData\Local\Programs\AegisVault)

param(
    [string]$InstallDir = $PSScriptRoot
)

$ErrorActionPreference = "Continue"

Write-Host "=== AegisVault — Rejestracja integracji z przeglądarką ===" -ForegroundColor Cyan
Write-Host ""

# Znajdź Python
$PythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $PythonCmd = $cmd
            Write-Host "[OK] Znaleziono Python: $ver" -ForegroundColor Green
            break
        }
    } catch {}
}

if (-not $PythonCmd) {
    Write-Host "[BŁĄD] Python nie jest zainstalowany lub nie jest w PATH." -ForegroundColor Red
    Write-Host "        Zainstaluj Python 3.10+ ze strony python.org i uruchom ponownie." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Możesz zarejestrować integrację ręcznie później:" -ForegroundColor Yellow
    Write-Host "  python ""$InstallDir\native_host\install\install.py"""
    exit 1
}

# Uruchom instalator native host
$InstallerPath = Join-Path $InstallDir "native_host\install\install.py"

if (-not (Test-Path $InstallerPath)) {
    Write-Host "[BŁĄD] Nie znaleziono: $InstallerPath" -ForegroundColor Red
    exit 1
}

Write-Host "[...] Rejestruję native host w przeglądarkach..." -ForegroundColor Yellow
& $PythonCmd $InstallerPath

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[OK] Rejestracja zakończona pomyślnie!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Następne kroki:" -ForegroundColor Cyan
    Write-Host "  1. Załaduj rozszerzenie AegisVault w przeglądarce (tryb deweloperski)"
    Write-Host "  2. Skopiuj ID rozszerzenia z chrome://extensions"
    Write-Host "  3. Uruchom ponownie instalator z ID:"
    Write-Host "     python ""$InstallerPath"" --extension-id TWOJE_EXTENSION_ID"
} else {
    Write-Host "[BŁĄD] Rejestracja nie powiodła się." -ForegroundColor Red
}
