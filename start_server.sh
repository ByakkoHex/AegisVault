#!/usr/bin/env bash
# start_server.sh — AegisVault Sync Server (macOS / Linux)
# Uruchomienie: bash start_server.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo " ========================================="
echo "   AegisVault — Serwer Synchronizacji"
echo "   http://localhost:8000"
echo "   Dokumentacja: http://localhost:8000/docs"
echo " ========================================="
echo ""

# Sprawdź Python
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[BŁĄD] python3 nie jest zainstalowany lub nie jest w PATH${NC}"
    exit 1
fi

# Sprawdź plik serwera
if [ ! -f "server/main.py" ]; then
    echo -e "${RED}[BŁĄD] Nie znaleziono server/main.py${NC}"
    echo "Upewnij się że uruchamiasz skrypt z głównego folderu projektu."
    exit 1
fi

# Zainstaluj zależności jeśli brak uvicorn
if ! python3 -c "import uvicorn" &>/dev/null; then
    echo "[INFO] Instaluję brakujące zależności..."
    pip3 install -r requirements-server.txt
    echo ""
fi

echo -e "${GREEN}[OK] Uruchamiam serwer... (Ctrl+C aby zatrzymać)${NC}"
echo ""

python3 -m uvicorn server.main:app --reload --port 8000
