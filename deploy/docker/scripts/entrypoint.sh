#!/usr/bin/env bash
# entrypoint.sh — uruchamia serwer AegisVault z walidacją konfiguracji

set -euo pipefail

# ── Walidacja JWT_SECRET_KEY ──────────────────────────────────
DEFAULT_KEY="zmien-mnie-na-losowy-string-w-produkcji-32-znaki!"

if [ -z "${JWT_SECRET_KEY:-}" ]; then
    echo "[ERROR] Zmienna JWT_SECRET_KEY nie jest ustawiona!"
    echo "        Wygeneruj klucz: python3 -c \"import secrets; print(secrets.token_hex(32))\""
    echo "        Następnie ustaw go w pliku .env lub jako zmienną środowiskową."
    exit 1
fi

if [ "${JWT_SECRET_KEY}" = "${DEFAULT_KEY}" ]; then
    echo "[WARN] JWT_SECRET_KEY ma wartość domyślną!"
    echo "       To jest niebezpieczne w środowisku produkcyjnym."
    echo "       Wygeneruj nowy klucz i zaktualizuj plik .env"
    # Nie przerywamy — pozwalamy uruchomić w trybie deweloperskim
fi

# ── Walidacja ścieżki bazy danych ────────────────────────────
DB_DIR=$(dirname "${DB_PATH:-/data/server_data.db}")
if [ ! -w "${DB_DIR}" ]; then
    echo "[ERROR] Katalog bazy danych '${DB_DIR}' nie jest zapisywalny!"
    echo "        Sprawdź montowanie wolumenu Docker."
    exit 1
fi

echo "[OK] Konfiguracja zweryfikowana."
echo "[OK] Baza danych: ${DB_PATH:-/data/server_data.db}"
echo "[OK] Uruchamiam AegisVault Sync Server..."
echo ""

# ── Start serwera ─────────────────────────────────────────────
WORKERS="${UVICORN_WORKERS:-2}"

exec python3 -m uvicorn server.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "${WORKERS}" \
    --no-access-log
