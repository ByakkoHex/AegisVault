#!/usr/bin/env bash
# build_all.sh — Buduje wszystkie komponenty AegisVault
#
# Użycie:
#   bash installer/build_all.sh [--skip-pyinstaller] [--extension-only]
#
# Opcje:
#   --skip-pyinstaller   Pomiń budowanie binarki (gdy dist/ już istnieje)
#   --extension-only     Buduj tylko rozszerzenie przeglądarkowe

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."

SKIP_PYINSTALLER=false
EXTENSION_ONLY=false

for arg in "$@"; do
    case $arg in
        --skip-pyinstaller) SKIP_PYINSTALLER=true ;;
        --extension-only)   EXTENSION_ONLY=true ;;
    esac
done

# ── Wykryj platformę ──────────────────────────────────────────
OS="$(uname -s)"
case "${OS}" in
    Darwin*) PLATFORM="macos" ;;
    Linux*)  PLATFORM="linux" ;;
    *)       PLATFORM="unknown" ;;
esac

echo "╔══════════════════════════════════════════════════╗"
echo "║       AegisVault — Build All Components          ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "Platforma: ${PLATFORM}"
echo "Katalog:   ${ROOT_DIR}"
echo ""

cd "${ROOT_DIR}"

# ── Krok 1: PyInstaller ───────────────────────────────────────
if [ "${EXTENSION_ONLY}" = false ] && [ "${SKIP_PYINSTALLER}" = false ]; then
    echo "━━━ [1/3] Budowanie aplikacji desktop (PyInstaller) ━━━"
    pip install -r requirements.txt --quiet
    pip install pyinstaller --quiet
    pyinstaller aegisvault.spec --noconfirm
    echo ""
else
    echo "[SKIP] Budowanie PyInstaller pominięte"
    echo ""
fi

# ── Krok 2: Instalator platformy ─────────────────────────────
if [ "${EXTENSION_ONLY}" = false ]; then
    echo "━━━ [2/3] Budowanie instalatora (${PLATFORM}) ━━━"
    case "${PLATFORM}" in
        macos)
            bash "${SCRIPT_DIR}/macos/build_dmg.sh"
            ;;
        linux)
            if command -v fakeroot &>/dev/null; then
                bash "${SCRIPT_DIR}/linux/build_deb.sh"
            else
                echo "[WARN] fakeroot niedostępny — pomijam .deb"
                echo "       Zainstaluj: sudo apt-get install fakeroot"
            fi
            ;;
        *)
            echo "[WARN] Budowanie instalatora dla '${PLATFORM}' nieobsługiwane w tym skrypcie"
            echo "       Dla Windows użyj: installer\\build_all.ps1"
            ;;
    esac
    echo ""
fi

# ── Krok 3: Rozszerzenie przeglądarkowe ──────────────────────
echo "━━━ [3/3] Pakowanie rozszerzenia przeglądarkowego ━━━"
bash "${SCRIPT_DIR}/extension/build_extension.sh"

# ── Podsumowanie ──────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║                  BUILD COMPLETE                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "Pliki w dist/:"
ls -lh "${ROOT_DIR}/dist/" 2>/dev/null || echo "(brak plików)"
