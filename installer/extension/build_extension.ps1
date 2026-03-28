# build_extension.ps1 — Pakuje rozszerzenie przeglądarkowe (Windows)
param(
    [string]$RootDir = (Resolve-Path "$PSScriptRoot\..\..")
)

$ExtDir  = Join-Path $RootDir "extension"
$DistDir = Join-Path $RootDir "dist"

# Odczytaj wersję
$Manifest = Get-Content (Join-Path $ExtDir "manifest.json") | ConvertFrom-Json
$Version  = $Manifest.version

Write-Host "=== Pakowanie rozszerzenia v$Version ===" -ForegroundColor Cyan

if (-not (Test-Path (Join-Path $ExtDir "lib\browser-polyfill.js"))) {
    Write-Host "[BŁĄD] Brak extension\lib\browser-polyfill.js" -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

# Chrome ZIP
$ChromeZip = Join-Path $DistDir "extension-chrome-$Version.zip"
Write-Host "[1/2] Chrome: $ChromeZip"

# Usuń stary plik jeśli istnieje
if (Test-Path $ChromeZip) { Remove-Item $ChromeZip }

# Pakuj zawartość folderu extension/ (bez plików .md)
Get-ChildItem -Path $ExtDir -Recurse |
    Where-Object { -not $_.PSIsContainer -and $_.Extension -ne ".md" -and $_.Name -ne ".DS_Store" } |
    ForEach-Object {
        $RelPath = $_.FullName.Substring($ExtDir.Length + 1)
        Compress-Archive -Path $_.FullName -DestinationPath $ChromeZip -Update
    }

# Firefox ZIP (identyczna zawartość)
$FirefoxZip = Join-Path $DistDir "extension-firefox-$Version.zip"
Copy-Item $ChromeZip $FirefoxZip -Force
Write-Host "[2/2] Firefox: $FirefoxZip"

Write-Host ""
Write-Host "✅ Rozszerzenie spakowane!" -ForegroundColor Green
Write-Host "   Chrome: $ChromeZip"
Write-Host "   Firefox: $FirefoxZip"
