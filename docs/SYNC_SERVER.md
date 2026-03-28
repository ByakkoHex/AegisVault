# Dokumentacja serwera synchronizacji — AegisVault

## Przegląd

Serwer synchronizacji to opcjonalny komponent FastAPI umożliwiający synchronizację zaszyfrowanych haseł między wieloma urządzeniami. Serwer **nigdy nie deszyfruje** danych — przechowuje wyłącznie zaszyfrowane blob-y wygenerowane przez klienta.

---

## Uruchomienie

### Windows

```batch
start_server.bat
```

### macOS / Linux

```bash
bash start_server.sh
```

### Ręcznie

```bash
pip install -r requirements-server.txt
python3 -m uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
```

| Adres | Opis |
|-------|------|
| `http://localhost:8000` | Serwer API |
| `http://localhost:8000/docs` | Dokumentacja Swagger UI |
| `http://localhost:8000/redoc` | Dokumentacja ReDoc |

---

## Konfiguracja

### `server/auth.py` — klucz JWT

```python
SECRET_KEY = "zmien-mnie-na-losowy-string-w-produkcji-32-znaki!"
```

**Przed wdrożeniem produkcyjnym zmień na losowy string:**

```python
import secrets
print(secrets.token_hex(32))
# Wynik: 64-znakowy hex string
```

### Port i adres

```bash
# Inny port:
python3 -m uvicorn server.main:app --port 8001

# Dostęp z sieci lokalnej:
python3 -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

---

## Endpointy API

### `POST /register`

Rejestruje nowe konto na serwerze synchronizacji.

**Request body:**
```json
{
  "username": "jan",
  "password": "haslo_serwera"
}
```

**Odpowiedź 200:**
```json
{
  "message": "Zarejestrowano pomyślnie"
}
```

**Odpowiedź 400:**
```json
{
  "detail": "Nazwa użytkownika zbyt krótka (min. 3 znaki)"
}
```

**Walidacja:**
- Username: min. 3 znaki
- Password: min. 8 znaków
- Username musi być unikalny

---

### `POST /login`

Loguje użytkownika i zwraca token JWT.

**Request body:**
```json
{
  "username": "jan",
  "password": "haslo_serwera"
}
```

**Odpowiedź 200:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

Token jest ważny **30 dni**.

---

### `GET /health`

Sprawdzenie dostępności serwera.

**Odpowiedź 200:**
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

### `POST /sync/push`

Wysyła zaszyfrowane hasła na serwer. Wymaga tokenu JWT.

**Nagłówek:**
```
Authorization: Bearer <token>
```

**Request body:**
```json
{
  "entries": [
    {
      "client_id": "jan-1",
      "title": "GitHub",
      "encrypted_blob": "gAAAAABh...",
      "category": "Praca"
    }
  ]
}
```

| Pole | Opis |
|------|------|
| `client_id` | Unikalny identyfikator wpisu: `username-entry_id` |
| `title` | Tytuł (plaintext — tylko do wyświetlenia w UI) |
| `encrypted_blob` | Base64 JSON zaszyfrowany przez Fernet klienta |
| `category` | Kategoria (plaintext) |

**Odpowiedź 200:**
```json
{
  "created": 3,
  "updated": 1
}
```

Jeśli `client_id` już istnieje — wpis jest aktualizowany. Jeśli nie — tworzony nowy.

---

### `GET /sync/pull`

Pobiera zaszyfrowane hasła z serwera. Wymaga tokenu JWT.

**Parametry query (opcjonalne):**
```
?since=2025-01-01T00:00:00   # delta sync — tylko zmiany po tej dacie
```

**Odpowiedź 200:**
```json
{
  "entries": [
    {
      "client_id": "jan-1",
      "title": "GitHub",
      "encrypted_blob": "gAAAAABh...",
      "category": "Praca",
      "updated_at": "2025-06-01T15:30:00"
    }
  ]
}
```

Zwraca tylko wpisy z `deleted=0` (aktywne).

---

### `POST /sync/delete`

Oznacza wpisy jako usunięte (soft delete). Wymaga tokenu JWT.

**Request body:**
```json
{
  "client_ids": ["jan-1", "jan-5"]
}
```

**Odpowiedź 200:**
```json
{
  "deleted": 2
}
```

Wpisy nie są fizycznie usuwane — flaga `deleted` zmieniana na `1`.

---

## Model danych serwera

```sql
-- server_users
CREATE TABLE server_users (
    id           INTEGER PRIMARY KEY,
    username     VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,    -- bcrypt
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- server_passwords
CREATE TABLE server_passwords (
    id             INTEGER PRIMARY KEY,
    username       VARCHAR NOT NULL,   -- właściciel (string, nie FK)
    client_id      VARCHAR NOT NULL,   -- username-entryid (unikalny per user)
    title          VARCHAR,            -- plaintext (do UI)
    encrypted_blob TEXT,               -- zaszyfrowany przez klienta
    category       VARCHAR,            -- plaintext
    updated_at     DATETIME,
    deleted        INTEGER DEFAULT 0   -- soft delete: 0=aktywny, 1=usunięty
);
```

---

## Autentykacja JWT

```
POST /login → JWT token (HS256, 30 dni)
               ↓
Authorization: Bearer <token> w każdym żądaniu /sync/*
               ↓
decode_token(token) → username
               ↓
Filtrowanie danych: WHERE username = decoded_username
```

Izolacja danych między użytkownikami jest egzekwowana na poziomie każdego endpointu.

---

## Przepływ synchronizacji

### Push (klient → serwer)

```
1. Klient odczytuje wszystkie lokalne hasła (z bazy aegisvault.db)
2. Dla każdego wpisu: odszyfruj → ponownie zaszyfruj tym samym kluczem
   (lub wyślij istniejący blob — ten sam klucz = ten sam wynik po Fernet.encrypt)
3. Wyślij POST /sync/push z listą wpisów
4. Serwer: upsert na client_id
```

W praktyce klient wysyła `encrypted_password` z bazy bezpośrednio jako `encrypted_blob`.

### Pull (serwer → klient)

```
1. Klient wysyła GET /sync/pull (opcjonalnie z ?since=...)
2. Serwer zwraca aktywne wpisy użytkownika
3. Klient importuje: pomija wpisy których tytuł już istnieje lokalnie
4. Nowe wpisy dodawane do aegisvault.db
```

### Deduplicacja przy pull

Klient pomija wpisy, których **tytuł** już istnieje w lokalnej bazie. Brak automatycznego merge'owania konfliktów — ostatni pull wygrywa dla nowych wpisów.

---

## Wdrożenie produkcyjne

### Minimalny deployment (VPS)

```bash
# 1. Skopiuj folder server/ + requirements-server.txt na serwer
# 2. Zainstaluj zależności
pip install -r requirements-server.txt

# 3. Zmień SECRET_KEY w server/auth.py

# 4. Uruchom (np. przez systemd lub screen)
python3 -m uvicorn server.main:app --host 0.0.0.0 --port 8000

# 5. (Zalecane) Nginx jako reverse proxy z certyfikatem SSL
```

### Przykładowa konfiguracja Nginx

```nginx
server {
    listen 443 ssl;
    server_name sync.aegisvault.example.com;

    ssl_certificate     /etc/letsencrypt/live/sync.aegisvault.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/sync.aegisvault.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Systemd service

```ini
[Unit]
Description=AegisVault Sync Server
After=network.target

[Service]
User=aegisvault
WorkingDirectory=/opt/aegisvault
ExecStart=/usr/bin/python3 -m uvicorn server.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## Ograniczenia obecnej wersji

| Ograniczenie | Uwagi |
|--------------|-------|
| SQLite jako baza | Wystarczające dla małej liczby użytkowników; dla produkcji rozważyć PostgreSQL |
| Brak rate limitingu | Nie ma ochrony przed brute-force na /login |
| Brak HTTPS | Wymagany reverse proxy (Nginx + Let's Encrypt) |
| Brak usuwania kont | Brak endpointu do usunięcia konta serwerowego |
| Soft-delete bez TTL | Usunięte wpisy pozostają w bazie na zawsze |
