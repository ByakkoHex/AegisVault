#!/usr/bin/env bash
# uninstall.sh — Odinstalowuje AegisVault z macOS
#
# Użycie:
#   bash installer/macos/uninstall.sh
#   bash installer/macos/uninstall.sh --keep-data   # zachowaj bazę haseł

set -euo pipefail

APP_NAME="AegisVault"
KEEP_DATA=false

for arg in "$@"; do
    case $arg in
        --keep-data) KEEP_DATA=true ;;
    esac
done

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}=== AegisVault — Deinstalacja ===${NC}"
echo ""

# ── 1. Zamknij aplikację jeśli działa ─────────────────────────
if pgrep -x "AegisVault" &>/dev/null; then
    echo "Zamykanie AegisVault..."
    pkill -x "AegisVault" || true
    sleep 1
fi

# ── 2. Usuń .app (Applications lub ~/Applications) ────────────
REMOVED_APP=false
for app_path in "/Applications/${APP_NAME}.app" "${HOME}/Applications/${APP_NAME}.app"; do
    if [ -d "${app_path}" ]; then
        rm -rf "${app_path}"
        echo -e "${GREEN}[OK]${NC} Usunięto ${app_path}"
        REMOVED_APP=true
    fi
done
if [ "${REMOVED_APP}" = false ]; then
    echo -e "${YELLOW}[INFO]${NC} Aplikacja nie znaleziona w /Applications ani ~/Applications"
fi

# ── 3. Usuń native messaging hosty ze wszystkich przeglądarek ─
NATIVE_HOST_DIRS=(
    "${HOME}/Library/Application Support/Google/Chrome/NativeMessagingHosts"
    "${HOME}/Library/Application Support/Chromium/NativeMessagingHosts"
    "${HOME}/Library/Application Support/Microsoft Edge/NativeMessagingHosts"
    "${HOME}/Library/Application Support/Firefox/NativeMessagingHosts"
    "/Library/Application Support/Mozilla/NativeMessagingHosts"
)
for dir in "${NATIVE_HOST_DIRS[@]}"; do
    manifest="${dir}/com.aegisvault.host.json"
    if [ -f "${manifest}" ]; then
        rm -f "${manifest}"
        echo -e "${GREEN}[OK]${NC} Usunięto: ${manifest}"
    fi
done

# ── 4. Usuń wpis autostart (Login Items) ──────────────────────
osascript -e \
    "tell application \"System Events\" to delete (every login item whose name is \"${APP_NAME}\")" \
    2>/dev/null || true

# ── 5. Usuń LaunchAgent (jeśli był dodany) ────────────────────
LAUNCH_AGENT="${HOME}/Library/LaunchAgents/pl.aegisvault.app.plist"
if [ -f "${LAUNCH_AGENT}" ]; then
    launchctl unload "${LAUNCH_AGENT}" 2>/dev/null || true
    rm -f "${LAUNCH_AGENT}"
    echo -e "${GREEN}[OK]${NC} Usunięto LaunchAgent"
fi

# ── 6. Dane użytkownika ────────────────────────────────────────
USER_DATA_DIR="${HOME}/Library/Application Support/${APP_NAME}"
if [ -d "${USER_DATA_DIR}" ]; then
    if [ "${KEEP_DATA}" = true ]; then
        echo -e "${YELLOW}[INFO]${NC} Dane zachowane (--keep-data): ${USER_DATA_DIR}"
    else
        echo ""
        read -rp "Czy usunąć dane aplikacji (baza haseł, ustawienia)? [t/N] " answer
        if [[ "${answer}" =~ ^[TtYy]$ ]]; then
            rm -rf "${USER_DATA_DIR}"
            echo -e "${GREEN}[OK]${NC} Usunięto dane: ${USER_DATA_DIR}"
        else
            echo -e "${YELLOW}[INFO]${NC} Dane zachowane: ${USER_DATA_DIR}"
        fi
    fi
fi

echo ""
echo -e "${GREEN}✅ AegisVault odinstalowany.${NC}"
