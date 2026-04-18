#!/bin/bash
# Usuwa flagę kwarantanny systemu macOS — wymagane dla aplikacji dystrybuowanych
# poza App Store (ad-hoc signed). Uruchom raz po przeciągnięciu AegisVault
# do folderu Aplikacje.

APP="/Applications/AegisVault.app"

# Fallback: app obok skryptu (np. jeszcze w DMG)
if [ ! -d "$APP" ]; then
    APP="$(dirname "$0")/AegisVault.app"
fi

if [ ! -d "$APP" ]; then
    echo "❌  Nie znaleziono AegisVault.app."
    echo "    Najpierw przeciągnij AegisVault do folderu Aplikacje,"
    echo "    a potem uruchom ten skrypt ponownie."
    read -n1 -r -p $'\nNaciśnij dowolny klawisz, aby zamknąć...' _
    exit 1
fi

echo "🔓  Usuwam blokadę Gatekeepera z: $APP"
xattr -dr com.apple.quarantine "$APP" 2>/dev/null

echo ""
echo "✅  Gotowe! Możesz teraz uruchomić AegisVault normalnie."
echo "    Kliknij dwukrotnie ikonę w folderze Aplikacje."
echo ""
read -n1 -r -p "Naciśnij dowolny klawisz, aby zamknąć..." _
