#!/usr/bin/env bash
# init_ssl.sh — Jednorazowe pobranie certyfikatu Let's Encrypt
# Uruchamiaj na serwerze (hoście), NIE wewnątrz kontenera.
#
# Wymagania:
#   - certbot zainstalowany na hoście: apt install certbot
#   - Zmienna DOMAIN i CERTBOT_EMAIL ustawione w .env lub przekazane jako argumenty
#   - Port 80 wolny (zatrzymaj nginx przed uruchomieniem)
#
# Użycie:
#   bash scripts/init_ssl.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"

# Wczytaj .env jeśli istnieje
if [ -f "${ENV_FILE}" ]; then
    set -a
    source "${ENV_FILE}"
    set +a
fi

DOMAIN="${DOMAIN:-}"
EMAIL="${CERTBOT_EMAIL:-}"

if [ -z "${DOMAIN}" ] || [ -z "${EMAIL}" ]; then
    echo "[BŁĄD] Ustaw DOMAIN i CERTBOT_EMAIL w pliku .env"
    echo "       Lub wywołaj: DOMAIN=sync.example.com CERTBOT_EMAIL=admin@example.com bash init_ssl.sh"
    exit 1
fi

echo "[1/3] Zatrzymuję nginx (jeśli działa)..."
docker compose -f "${SCRIPT_DIR}/../docker-compose.yml" \
               -f "${SCRIPT_DIR}/../docker-compose.prod.yml" \
               stop nginx 2>/dev/null || true

echo "[2/3] Pobieranie certyfikatu Let's Encrypt dla ${DOMAIN}..."
certbot certonly \
    --standalone \
    --non-interactive \
    --agree-tos \
    --email "${EMAIL}" \
    -d "${DOMAIN}"

echo "[3/3] Uruchamiam kontenery..."
docker compose -f "${SCRIPT_DIR}/../docker-compose.yml" \
               -f "${SCRIPT_DIR}/../docker-compose.prod.yml" \
               up -d

echo ""
echo "✅ Certyfikat SSL pobrany pomyślnie!"
echo "   Serwer dostępny pod: https://${DOMAIN}"
echo ""
echo "Certbot odnawia certyfikaty automatycznie. Dodaj do cron:"
echo "   0 3 * * * certbot renew --quiet && docker restart aegisvault-nginx"
