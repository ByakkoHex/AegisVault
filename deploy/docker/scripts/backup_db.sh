#!/usr/bin/env bash
# backup_db.sh — Tworzenie kopii zapasowej bazy danych serwera
#
# Użycie:
#   bash backup_db.sh
#
# Automatyzacja (cron, co noc o 3:00):
#   0 3 * * * /opt/aegisvault/deploy/docker/scripts/backup_db.sh >> /var/log/aegisvault-backup.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${SCRIPT_DIR}/.."

# Katalog z danymi (ten sam co wolumin Docker)
DATA_DIR="${SCRIPT_DIR}/../../data"
BACKUP_DIR="${SCRIPT_DIR}/../../backups"
DB_FILE="${DATA_DIR}/server_data.db"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/server_data_${TIMESTAMP}.db"

# Utwórz katalog backupów jeśli nie istnieje
mkdir -p "${BACKUP_DIR}"

if [ ! -f "${DB_FILE}" ]; then
    echo "[$(date)] BŁĄD: Plik bazy danych nie istnieje: ${DB_FILE}"
    exit 1
fi

# Użyj sqlite3 .backup dla bezpiecznego kopiowania (unika korupcji przy aktywnych zapisach)
if command -v sqlite3 &>/dev/null; then
    sqlite3 "${DB_FILE}" ".backup ${BACKUP_FILE}"
else
    # Fallback: zatrzymaj kontener na chwilę i skopiuj
    docker compose -f "${COMPOSE_DIR}/docker-compose.yml" stop aegisvault-server
    cp "${DB_FILE}" "${BACKUP_FILE}"
    docker compose -f "${COMPOSE_DIR}/docker-compose.yml" start aegisvault-server
fi

echo "[$(date)] Backup: ${BACKUP_FILE} ($(du -sh "${BACKUP_FILE}" | cut -f1))"

# Usuń backupy starsze niż 30 dni
find "${BACKUP_DIR}" -name "server_data_*.db" -mtime +30 -delete
REMAINING=$(find "${BACKUP_DIR}" -name "server_data_*.db" | wc -l)
echo "[$(date)] Aktywne backupy: ${REMAINING}"
