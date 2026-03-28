# Wdrożenie serwera synchronizacji — AegisVault

## Przegląd

Serwer synchronizacji łączy aplikację desktop, wtyczkę przeglądarkową i przyszłą aplikację mobilną we wspólny ekosystem. Dane przechowywane na serwerze są **zawsze zaszyfrowane** — serwer nie ma dostępu do kluczy deszyfrowania.

```
AegisVault Desktop ──┐
AegisVault Wtyczka ──┤──▶ Serwer Sync (FastAPI) ──▶ server_data.db
AegisVault Mobile  ──┘         ↑
(planowane)               HTTPS + JWT
```

---

## Wymagania

| Komponent | Wymaganie |
|-----------|-----------|
| Docker | 24.0+ |
| Docker Compose | 2.0+ (plugin) |
| RAM | min. 256 MB |
| Miejsce | min. 500 MB |
| Port | 80, 443 (produkcja) lub 8000 (lokalne) |

**Opcjonalnie dla produkcji:**
- Domena (np. `sync.twojadomena.pl`)
- Certbot (dla Let's Encrypt)

---

## Konfiguracja środowiska

### 1. Przejdź do katalogu deploy

```bash
cd deploy/docker
```

### 2. Skopiuj i uzupełnij plik `.env`

```bash
cp .env.example .env
```

Otwórz `.env` i ustaw:

```bash
# Wygeneruj bezpieczny klucz (OBOWIĄZKOWE):
python3 -c "import secrets; print(secrets.token_hex(32))"

# Wklej wynik jako JWT_SECRET_KEY w pliku .env
JWT_SECRET_KEY=tu_wklej_wygenerowany_klucz
```

---

## Scenariusz A — Sieć lokalna (dom / biuro)

Najbardziej prosta konfiguracja. Serwer dostępny tylko w sieci lokalnej.

```bash
cd deploy/docker
docker compose up -d
```

**Wynik:** serwer działa pod `http://192.168.1.x:8000`

### Konfiguracja klientów

W aplikacji desktop → okno **Synchronizacja**:
```
Adres serwera: http://192.168.1.100:8000
```

Znajdź swoje IP:
```bash
# Linux/macOS
ip route get 1 | awk '{print $NF; exit}'
# lub
hostname -I | cut -d' ' -f1

# Windows
ipconfig | findstr "IPv4"
```

### Raspberry Pi (serwer domowy)

```bash
# Na Raspberry Pi:
sudo apt update && sudo apt install docker.io docker-compose-plugin -y
git clone https://github.com/twoj-nick/aegisvault.git
cd aegisvault/deploy/docker
cp .env.example .env
# Ustaw JWT_SECRET_KEY w .env
docker compose up -d

# Autostart po restarcie Pi:
sudo systemctl enable docker
```

---

## Scenariusz B — VPS z domeną i SSL (produkcja)

### Krok 1 — Kup i skonfiguruj VPS

Minimalne wymagania: 1 vCPU, 512 MB RAM, 10 GB SSD.
Poleceni dostawcy: Hetzner, DigitalOcean, OVH, Linode.

**Na serwerze** (Ubuntu 22.04+):

```bash
# Aktualizacja systemu
sudo apt update && sudo apt upgrade -y

# Instalacja Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Instalacja Certbot
sudo apt install certbot -y
```

### Krok 2 — Klonuj projekt

```bash
git clone https://github.com/twoj-nick/aegisvault.git /opt/aegisvault
cd /opt/aegisvault/deploy/docker
```

### Krok 3 — Konfiguracja DNS

W panelu domeny utwórz rekord A:
```
sync.twojadomena.pl → IP_SERWERA
```

Poczekaj na propagację DNS (kilka minut do godziny).

### Krok 4 — Uzupełnij `.env`

```bash
cp .env.example .env
nano .env
```

```env
JWT_SECRET_KEY=wygenerowany_losowy_klucz_64_znaki
DOMAIN=sync.twojadomena.pl
CERTBOT_EMAIL=admin@twojadomena.pl
```

### Krok 5 — Pobierz certyfikat SSL

```bash
bash scripts/init_ssl.sh
```

Skrypt:
1. Zatrzymuje nginx (jeśli działa)
2. Uruchamia `certbot certonly --standalone`
3. Restartuje wszystkie kontenery z SSL

### Krok 6 — Weryfikacja

```bash
curl https://sync.twojadomena.pl/health
# → {"status": "ok", "version": "1.0.0"}
```

### Konfiguracja klientów

```
Adres serwera: https://sync.twojadomena.pl
```

---

## Scenariusz C — Cloud (Render / Railway / Fly.io)

Platformy cloud zarządzają HTTPS i procesami automatycznie. Potrzebny tylko `Dockerfile`.

### Render.com (darmowy plan)

1. Utwórz konto na [render.com](https://render.com)
2. **New** → **Web Service** → połącz repozytorium GitHub
3. Ustaw:
   - **Build Command**: `pip install -r requirements-server.txt`
   - **Start Command**: `uvicorn server.main:app --host 0.0.0.0 --port $PORT`
   - **Dockerfile Path**: `deploy/docker/Dockerfile`
4. W **Environment Variables** dodaj:
   - `JWT_SECRET_KEY` = wygenerowany klucz
   - `DB_PATH` = ścieżka do persistent disk

5. Dodaj **Disk** (persistent storage): mount path `/data`

6. Adres serwera: `https://twoja-nazwa.onrender.com`

### Railway.app

```bash
# Zainstaluj Railway CLI
npm install -g @railway/cli
railway login
railway init
railway up
railway variables set JWT_SECRET_KEY=<klucz>
```

### Fly.io

```bash
# Zainstaluj flyctl
curl -L https://fly.io/install.sh | sh
fly launch --dockerfile deploy/docker/Dockerfile
fly secrets set JWT_SECRET_KEY=<klucz>
fly volumes create aegisvault_data --size 1
fly deploy
```

---

## Zarządzanie serwerem

### Sprawdzenie statusu

```bash
cd /opt/aegisvault/deploy/docker
docker compose ps
docker compose logs --tail=50 aegisvault-server
```

### Restart

```bash
docker compose restart
```

### Aktualizacja do nowej wersji

```bash
git pull origin main
docker compose build --no-cache
docker compose up -d
```

### Backup bazy danych

```bash
bash scripts/backup_db.sh
```

Automatyczny backup codziennie o 3:00 (dodaj do cron):

```bash
# Edytuj cron:
crontab -e

# Dodaj:
0 3 * * * /opt/aegisvault/deploy/docker/scripts/backup_db.sh >> /var/log/aegisvault-backup.log 2>&1
```

### Odnawianie certyfikatu SSL

Certbot odnawia certyfikaty automatycznie. Dodaj hook do restartu nginx:

```bash
echo "post_hook = docker restart aegisvault-nginx" | \
  sudo tee /etc/letsencrypt/renewal-hooks/deploy/restart-nginx.sh
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/restart-nginx.sh
```

---

## Monitorowanie

### Health check

```bash
# Sprawdź czy serwer odpowiada
curl -s https://sync.twojadomena.pl/health | python3 -m json.tool
```

### Logi

```bash
# Serwer
docker compose logs -f aegisvault-server

# Nginx (access + error)
docker compose logs -f nginx

# Filtruj błędy
docker compose logs aegisvault-server 2>&1 | grep -i error
```

### Wolumeny (dane)

```bash
# Sprawdź rozmiar bazy danych
docker run --rm -v aegisvault-data:/data alpine du -sh /data/
```

---

## Bezpieczeństwo serwera

### Firewall (UFW)

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (ACME challenge)
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### Automatyczne aktualizacje bezpieczeństwa

```bash
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure -plow unattended-upgrades
```

### Zmiana SECRET_KEY

Zmiana klucza JWT unieważnia **wszystkie istniejące tokeny** (użytkownicy będą musieli zalogować się ponownie na serwerze):

```bash
# Wygeneruj nowy klucz
python3 -c "import secrets; print(secrets.token_hex(32))"

# Zaktualizuj .env
nano .env   # zmień JWT_SECRET_KEY

# Restart serwera
docker compose restart aegisvault-server
```

---

## Zmienne środowiskowe — pełna lista

| Zmienna | Wymagana | Domyślna | Opis |
|---------|----------|---------|------|
| `JWT_SECRET_KEY` | **TAK** | — | Klucz podpisywania JWT (min. 32 znaki) |
| `DB_PATH` | Nie | `server_data.db` | Ścieżka do pliku SQLite |
| `UVICORN_WORKERS` | Nie | `2` | Liczba procesów uvicorn |
| `DOMAIN` | Prod | — | Domena (Nginx + SSL) |
| `CERTBOT_EMAIL` | Prod | — | Email Let's Encrypt |

---

## Rozwiązywanie problemów

### Serwer nie startuje

```bash
docker compose logs aegisvault-server
```

Częste przyczyny:
- `JWT_SECRET_KEY` nie ustawiony → sprawdź `.env`
- Port 8000 zajęty → `lsof -i :8000`

### Błąd SSL: certyfikat nie istnieje

```bash
ls /etc/letsencrypt/live/
# Jeśli puste — uruchom init_ssl.sh ponownie
bash scripts/init_ssl.sh
```

### Klient nie może się połączyć

```bash
# Sprawdź dostępność
curl -v https://sync.twojadomena.pl/health

# Sprawdź DNS
nslookup sync.twojadomena.pl

# Sprawdź firewall
sudo ufw status
```
