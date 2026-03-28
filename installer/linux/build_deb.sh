#!/usr/bin/env bash
# build_deb.sh — Tworzy pakiet .deb dla Debian/Ubuntu
#
# Wymagania:
#   - Ubuntu/Debian (dpkg-deb, fakeroot)
#   - Zbudowany dist/aegisvault (pyinstaller aegisvault.spec)
#
# Użycie:
#   bash installer/linux/build_deb.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/../.."
DIST_DIR="${ROOT_DIR}/dist"
TEMPLATE_DIR="${SCRIPT_DIR}/deb_template"

# ── Wersja ────────────────────────────────────────────────────
VERSION=$(python3 -c "import sys; sys.path.insert(0,'${ROOT_DIR}'); from version import APP_VERSION; print(APP_VERSION)" 2>/dev/null || echo "1.0.0")
ARCH="amd64"
PKG_NAME="aegisvault_${VERSION}_${ARCH}"

echo "=== Budowanie pakietu .deb: ${PKG_NAME} ==="

# ── Sprawdź binarkę ───────────────────────────────────────────
BINARY="${DIST_DIR}/aegisvault"
if [ ! -f "${BINARY}" ]; then
    echo "[BŁĄD] Nie znaleziono ${BINARY}"
    echo "        Uruchom: pyinstaller aegisvault.spec --noconfirm"
    exit 1
fi

# ── Utwórz strukturę pakietu ──────────────────────────────────
BUILD_DIR="${DIST_DIR}/deb_build/${PKG_NAME}"
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"
cp -r "${TEMPLATE_DIR}/." "${BUILD_DIR}/"

# ── Skopiuj pliki aplikacji ───────────────────────────────────
mkdir -p "${BUILD_DIR}/usr/bin"
mkdir -p "${BUILD_DIR}/usr/share/aegisvault"

cp "${BINARY}" "${BUILD_DIR}/usr/bin/aegisvault"
chmod 755 "${BUILD_DIR}/usr/bin/aegisvault"

# Skopiuj moduły Python potrzebne dla native host
for dir in native_host core database utils; do
    if [ -d "${ROOT_DIR}/${dir}" ]; then
        cp -r "${ROOT_DIR}/${dir}" "${BUILD_DIR}/usr/share/aegisvault/"
        # Usuń __pycache__
        find "${BUILD_DIR}/usr/share/aegisvault/${dir}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    fi
done

# ── Wypełnij wersję w pliku control ──────────────────────────
sed -i "s/VERSION_PLACEHOLDER/${VERSION}/" "${BUILD_DIR}/DEBIAN/control"

# ── Uprawnienia ───────────────────────────────────────────────
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"
chmod 755 "${BUILD_DIR}/DEBIAN/prerm"

# ── Buduj pakiet ──────────────────────────────────────────────
echo "[1/1] Budowanie pakietu .deb..."
fakeroot dpkg-deb --build "${BUILD_DIR}" "${DIST_DIR}/${PKG_NAME}.deb"

# ── Sprzątanie ────────────────────────────────────────────────
rm -rf "${DIST_DIR}/deb_build"

echo ""
echo "✅ Pakiet .deb gotowy: ${DIST_DIR}/${PKG_NAME}.deb"
echo "   Rozmiar: $(du -sh "${DIST_DIR}/${PKG_NAME}.deb" | cut -f1)"
echo ""
echo "Instalacja:"
echo "   sudo dpkg -i ${DIST_DIR}/${PKG_NAME}.deb"
echo "   sudo apt-get install -f   # napraw zależności jeśli potrzeba"
