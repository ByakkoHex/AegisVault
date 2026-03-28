FROM python:3.11-slim

# Bezpieczeństwo: uruchamiaj jako nieuprzywilejowany użytkownik
RUN addgroup --system aegisvault && adduser --system --ingroup aegisvault aegisvault

WORKDIR /app

# Zależności serwera
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

# Kopiuj kod serwera
COPY server/ ./server/

# Katalog na bazę danych (montowany jako wolumin)
RUN mkdir -p /data && chown aegisvault:aegisvault /data

# Skrypt startowy
COPY deploy/docker/scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER aegisvault

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
