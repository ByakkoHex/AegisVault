#!/usr/bin/env bash
# build_dmg.sh — Tworzy instalator .dmg dla macOS
#
# Wymagania:
#   - macOS (hdiutil wbudowany w system)
#   - Zbudowany dist/AegisVault.app (pyinstaller aegisvault.spec)
#   - Opcjonalnie: create-dmg (npm install -g create-dmg) dla ładniejszego DMG
#
# Użycie:
#   bash installer/macos/build_dmg.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/../.."
DIST_DIR="${ROOT_DIR}/dist"

# ── Odczytaj wersję z manifestu rozszerzenia ──────────────────
VERSION=$(python3 -c "import sys; sys.path.insert(0,'${ROOT_DIR}'); from version import APP_VERSION; print(APP_VERSION)" 2>/dev/null || echo "1.0.0")
APP_NAME="AegisVault"
DMG_NAME="${APP_NAME}-${VERSION}.dmg"
VOLUME_NAME="${APP_NAME} ${VERSION}"

echo "=== Budowanie DMG: ${DMG_NAME} (v${VERSION}) ==="

# ── Sprawdź czy .app istnieje ─────────────────────────────────
APP_PATH="${DIST_DIR}/${APP_NAME}.app"
if [ ! -d "${APP_PATH}" ]; then
    echo "[BŁĄD] Nie znaleziono ${APP_PATH}"
    echo "        Uruchom najpierw: pyinstaller aegisvault.spec --noconfirm"
    exit 1
fi

# ── Staging ───────────────────────────────────────────────────
STAGING_DIR="${DIST_DIR}/dmg_staging"
rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}"

cp -R "${APP_PATH}" "${STAGING_DIR}/${APP_NAME}.app"
ln -s /Applications "${STAGING_DIR}/Applications"

# Dołącz README o native host
cat > "${STAGING_DIR}/README - Integracja z przeglądarką.txt" << 'EOF'
AegisVault — Integracja z przeglądarką (autouzupełnianie)
=========================================================

Aby włączyć autouzupełnianie haseł w przeglądarce:

1. Zainstaluj AegisVault.app do folderu Applications (przeciągnij)

2. Otwórz Terminal i uruchom:
   python3 ~/Applications/AegisVault.app/Contents/MacOS/native_host/install/install.py

   lub jeśli aplikacja jest w /Applications:
   python3 /Applications/AegisVault.app/Contents/MacOS/native_host/install/install.py

3. Załaduj rozszerzenie w Chrome:
   - Przejdź na chrome://extensions
   - Włącz "Tryb deweloperski"
   - "Załaduj rozpakowane" → wybierz folder extension/

4. Skopiuj ID rozszerzenia i uruchom instalator ponownie:
   python3 .../install.py --extension-id TWOJE_EXTENSION_ID

Wymagania: Python 3.10+ (https://python.org)
EOF

# ── Buduj DMG ─────────────────────────────────────────────────
TEMP_DMG="${DIST_DIR}/temp_${APP_NAME}.dmg"
FINAL_DMG="${DIST_DIR}/${DMG_NAME}"

# Preferuj create-dmg (ładniejszy wynik)
if command -v create-dmg &>/dev/null; then
    echo "[1/1] Budowanie z create-dmg..."
    create-dmg \
        --volname "${VOLUME_NAME}" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "${APP_NAME}.app" 150 185 \
        --hide-extension "${APP_NAME}.app" \
        --app-drop-link 450 185 \
        --no-internet-enable \
        "${FINAL_DMG}" \
        "${STAGING_DIR}"
else
    echo "[1/2] Budowanie tymczasowego DMG (hdiutil)..."
    STAGING_MB=$(du -sm "${STAGING_DIR}" | cut -f1)
    DMG_SIZE="$((STAGING_MB + 80))m"
    echo "    Rozmiar staging: ${STAGING_MB} MB → DMG: ${DMG_SIZE}"
    hdiutil create \
        -srcfolder "${STAGING_DIR}" \
        -volname "${VOLUME_NAME}" \
        -fs HFS+ \
        -fsargs "-c c=64,a=16,b=16" \
        -format UDRW \
        -size "${DMG_SIZE}" \
        "${TEMP_DMG}"

    echo "[2/2] Kompresja do finalnego DMG..."
    hdiutil convert "${TEMP_DMG}" \
        -format UDZO \
        -imagekey zlib-level=9 \
        -o "${FINAL_DMG}"

    rm -f "${TEMP_DMG}"
fi

# ── Sprzątanie ────────────────────────────────────────────────
rm -rf "${STAGING_DIR}"

echo ""
echo "✅ DMG gotowy: ${FINAL_DMG}"
echo "   Rozmiar: $(du -sh "${FINAL_DMG}" | cut -f1)"
