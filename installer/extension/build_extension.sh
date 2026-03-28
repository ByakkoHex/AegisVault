#!/usr/bin/env bash
# build_extension.sh — Pakuje rozszerzenie przeglądarkowe do ZIP
#
# Tworzy:
#   dist/extension-chrome-VERSION.zip   (Chrome Web Store)
#   dist/extension-firefox-VERSION.zip  (Firefox AMO / sideload)
#
# Użycie:
#   bash installer/extension/build_extension.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/../.."
EXT_DIR="${ROOT_DIR}/extension"
DIST_DIR="${ROOT_DIR}/dist"

# ── Wersja z manifestu ────────────────────────────────────────
VERSION=$(python3 -c "import json; print(json.load(open('${EXT_DIR}/manifest.json'))['version'])" 2>/dev/null || echo "1.0.0")

echo "=== Pakowanie rozszerzenia v${VERSION} ==="

# ── Walidacja ─────────────────────────────────────────────────
if [ ! -f "${EXT_DIR}/manifest.json" ]; then
    echo "[BŁĄD] Nie znaleziono extension/manifest.json"
    exit 1
fi

MV=$(python3 -c "import json; print(json.load(open('${EXT_DIR}/manifest.json'))['manifest_version'])")
if [ "${MV}" != "3" ]; then
    echo "[BŁĄD] Wymagany Manifest V3, znaleziono V${MV}"
    exit 1
fi

if [ ! -f "${EXT_DIR}/lib/browser-polyfill.js" ]; then
    echo "[BŁĄD] Brak extension/lib/browser-polyfill.js"
    echo "       Pobierz z: https://github.com/mozilla/webextension-polyfill/releases"
    exit 1
fi

mkdir -p "${DIST_DIR}"

# ── Chrome / Edge ZIP ─────────────────────────────────────────
CHROME_ZIP="${DIST_DIR}/extension-chrome-${VERSION}.zip"
echo "[1/2] Chrome: ${CHROME_ZIP}"

cd "${EXT_DIR}"
zip -r "${CHROME_ZIP}" . \
    --exclude "*.md" \
    --exclude ".DS_Store" \
    --exclude "**/__pycache__/*" \
    --exclude "*.py[co]"
cd "${ROOT_DIR}"

echo "      Rozmiar: $(du -sh "${CHROME_ZIP}" | cut -f1)"

# ── Firefox ZIP (identyczna zawartość, inny manifest jest już w pliku) ──
FIREFOX_ZIP="${DIST_DIR}/extension-firefox-${VERSION}.zip"
cp "${CHROME_ZIP}" "${FIREFOX_ZIP}"
echo "[2/2] Firefox: ${FIREFOX_ZIP}"
echo "      (identyczna zawartość — manifest ma gecko.id)"

echo ""
echo "✅ Rozszerzenie spakowane!"
echo ""
echo "Chrome Web Store:"
echo "  https://chrome.google.com/webstore/devconsole"
echo "  Prześlij: ${CHROME_ZIP}"
echo ""
echo "Firefox AMO:"
echo "  https://addons.mozilla.org/en-US/developers/"
echo "  Prześlij: ${FIREFOX_ZIP}"
echo ""
echo "Ręczna instalacja Chrome (tryb deweloperski):"
echo "  1. chrome://extensions → Włącz tryb deweloperski"
echo "  2. 'Załaduj rozpakowane' → wybierz folder extension/"
echo "  (Nie używaj ZIP — załaduj folder bezpośrednio)"
