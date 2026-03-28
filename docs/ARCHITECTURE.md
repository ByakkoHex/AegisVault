# Architektura systemu AegisVault

## Przegląd

AegisVault to wielokomponentowy system złożony z trzech niezależnych, ale współpracujących warstw:

```
┌─────────────────────────────────────────────────────────────┐
│                    WARSTWA KLIENCKA                         │
│                                                             │
│  ┌──────────────────────┐   ┌───────────────────────────┐  │
│  │  Aplikacja Desktop   │   │   Wtyczka Przeglądarkowa  │  │
│  │  (Python/CTk)        │   │   (WebExtension MV3)      │  │
│  └──────────┬───────────┘   └────────────┬──────────────┘  │
│             │                            │ Native Messaging │
│             │                ┌───────────▼──────────────┐  │
│             │                │  Native Host (Python)    │  │
│             │                └───────────┬──────────────┘  │
│             │                            │                  │
│             └────────────────┬───────────┘                  │
│                              │                              │
│                    ┌─────────▼─────────┐                   │
│                    │   aegisvault.db   │                   │
│                    │   (SQLite, lok.)  │                   │
│                    └─────────┬─────────┘                   │
└──────────────────────────────│──────────────────────────────┘
                               │ HTTPS (opcjonalne)
┌──────────────────────────────│──────────────────────────────┐
│              WARSTWA SERWEROWA                              │
│                              │                              │
│                    ┌─────────▼─────────┐                   │
│                    │  Serwer Sync      │                   │
│                    │  (FastAPI)        │                   │
│                    └─────────┬─────────┘                   │
│                              │                              │
│                    ┌─────────▼─────────┐                   │
│                    │  server_data.db   │                   │
│                    │  (SQLite, serwer) │                   │
│                    └───────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Komponenty

### 1. Aplikacja Desktop

Napisana w Pythonie z użyciem biblioteki `customtkinter`. Działa lokalnie — nie wymaga połączenia z internetem.

**Moduły:**

| Moduł | Odpowiedzialność |
|-------|-----------------|
| `main.py` | Punkt wejścia, inicjalizacja fontów i bazy |
| `gui/login_window.py` | Logowanie, rejestracja, weryfikacja 2FA |
| `gui/main_window.py` | Zarządzanie hasłami, kategorie, wyszukiwanie |
| `gui/security_analysis_window.py` | Audyt słabości, duplikatów, starych haseł |
| `gui/settings_window.py` | Zmiana hasła głównego, usuwanie konta |
| `gui/sync_window.py` | Konfiguracja i wykonanie synchronizacji |
| `core/crypto.py` | Cała logika kryptograficzna |
| `core/totp.py` | Generowanie/weryfikacja kodów TOTP |
| `database/models.py` | Definicje tabel SQLAlchemy |
| `database/db_manager.py` | Operacje CRUD na bazie danych |
| `utils/paths.py` | Cross-platform ścieżki danych aplikacji |
| `utils/font_manager.py` | Ładowanie czcionki Roboto (cross-platform) |
| `utils/password_strength.py` | Ocena siły haseł i entropia |
| `utils/sync_client.py` | Klient HTTP dla serwera synchronizacji |

### 2. Serwer Synchronizacji

Opcjonalny serwer FastAPI do synchronizacji zaszyfrowanych haseł między urządzeniami.

**Zasada działania:**
- Klient szyfruje hasła **przed** wysłaniem
- Serwer przechowuje wyłącznie zaszyfrowane blob-y — **nigdy nie widzi plaintext**
- Autentykacja przez JWT (HS256, ważność 30 dni)
- Soft-delete: usunięte wpisy oznaczane flagą `deleted=1` (nie kasowane fizycznie)

| Moduł | Odpowiedzialność |
|-------|-----------------|
| `server/main.py` | Endpointy FastAPI: /register, /login, /sync/push, /sync/pull, /sync/delete |
| `server/auth.py` | Tworzenie i weryfikacja tokenów JWT, bcrypt |
| `server/models.py` | Modele SQLAlchemy: ServerUser, ServerPassword |

### 3. Wtyczka Przeglądarkowa

WebExtension Manifest V3 działająca na Chrome, Firefox i Edge z jednego kodu.

**Przepływ komunikacji:**

```
Strona HTML (formularz logowania)
        ↕  DOM events
content_script.js
        ↕  chrome.runtime.sendMessage
service_worker.js (background)
        ↕  chrome.runtime.connectNative
native_host/aegisvault_host.py
        ↕  importuje bezpośrednio
core/crypto.py + database/db_manager.py
        ↕  odczytuje
aegisvault.db (ta sama baza co aplikacja desktop)
```

| Plik | Odpowiedzialność |
|------|-----------------|
| `extension/manifest.json` | Deklaracja uprawnień, content scripts, service worker |
| `extension/background/service_worker.js` | Zarządzanie połączeniem z hostem, stanem sesji, badge |
| `extension/content/content_script.js` | Wykrywanie formularzy, chip autofill (Shadow DOM) |
| `extension/popup/popup.js` | Interfejs użytkownika: logowanie, przeglądanie haseł |
| `native_host/aegisvault_host.py` | Pętla native messaging, dispatch wiadomości |
| `native_host/host_protocol.py` | Enkodowanie/dekodowanie 4-bajtowego protokołu |
| `native_host/host_session.py` | Sesja kryptograficzna w pamięci procesu |

---

## Przepływ danych — logowanie i szyfrowanie

```
Użytkownik wpisuje hasło główne
          │
          ▼
bcrypt.verify(hasło, hash_z_bazy)     ← weryfikacja tożsamości
          │
          ▼ (jeśli OK)
PBKDF2-HMAC-SHA256(hasło, salt, 480_000_iter)
          │
          ▼
Klucz AES-256 (Fernet)                ← klucz NIGDY nie trafia na dysk
          │
          ├─ encrypt(plaintext) → zaszyfrowany blob → do bazy
          └─ decrypt(blob)      → plaintext        → do UI/autofill
```

---

## Model danych (klient)

```
┌──────────────────────────────────────────────────────────┐
│  users                                                   │
│  ─────────────────────────────────────────────────────   │
│  id               INTEGER PRIMARY KEY                    │
│  username         VARCHAR(64) UNIQUE NOT NULL            │
│  master_password_hash  BLOB NOT NULL  (bcrypt, rounds=12)│
│  salt             BLOB NOT NULL       (16 bajtów losowych)│
│  totp_secret      VARCHAR(32)         (NULL = brak 2FA)  │
│  created_at       DATETIME                               │
└────────────────────────┬─────────────────────────────────┘
                         │ 1:N
┌────────────────────────▼─────────────────────────────────┐
│  passwords                                               │
│  ─────────────────────────────────────────────────────   │
│  id               INTEGER PRIMARY KEY                    │
│  user_id          INTEGER FK → users.id                  │
│  title            VARCHAR(128) NOT NULL                  │
│  username         VARCHAR(128)                           │
│  encrypted_password  BLOB NOT NULL   (Fernet/AES-256)    │
│  url              VARCHAR(256)                           │
│  notes            TEXT                                   │
│  category         VARCHAR(64)  (Social Media/Praca/...)  │
│  created_at       DATETIME                               │
│  updated_at       DATETIME                               │
└──────────────────────────────────────────────────────────┘
```

---

## Model danych (serwer)

```
┌──────────────────────────────────────────────────────────┐
│  server_users                                            │
│  username         VARCHAR UNIQUE                         │
│  password_hash    VARCHAR  (bcrypt, konto sync)          │
└────────────────────────┬─────────────────────────────────┘
                         │ 1:N (przez username string)
┌────────────────────────▼─────────────────────────────────┐
│  server_passwords                                        │
│  client_id        VARCHAR UNIQUE  (username-entryid)     │
│  title            VARCHAR                                │
│  encrypted_blob   TEXT  (Base64 JSON — serwer nie szyfruje)│
│  category         VARCHAR                               │
│  updated_at       DATETIME                               │
│  deleted          INTEGER  (0=aktywny, 1=usunięty)       │
└──────────────────────────────────────────────────────────┘
```

---

## Ścieżki danych na dysku

| System | Baza danych klienta |
|--------|---------------------|
| Windows | `%APPDATA%\AegisVault\aegisvault.db` |
| macOS | `~/Library/Application Support/AegisVault/aegisvault.db` |
| Linux | `~/.local/share/aegisvault/aegisvault.db` |

Serwer synchronizacji przechowuje bazę w katalogu roboczym: `server_data.db`.

---

## Zależności zewnętrzne

### Klient desktop

| Biblioteka | Wersja min | Zastosowanie |
|------------|-----------|--------------|
| customtkinter | 5.2.0 | GUI |
| cryptography | 41.0.0 | Fernet/AES-256, PBKDF2 |
| bcrypt | 4.1.0 | Haszowanie hasła głównego |
| pyotp | 2.9.0 | TOTP 2FA |
| qrcode + Pillow | 7.4 / 10.0 | Generowanie QR kodów |
| pyperclip | 1.8.2 | Schowek systemowy |
| httpx | 0.27.0 | Klient HTTP (sync) |
| SQLAlchemy | 2.0.0 | ORM, SQLite |
| requests | 2.31.0 | Pobieranie fontów |

### Serwer synchronizacji

| Biblioteka | Wersja min | Zastosowanie |
|------------|-----------|--------------|
| fastapi | 0.110.0 | Framework API |
| uvicorn | 0.29.0 | ASGI server |
| python-jose | 3.3.0 | JWT |
| bcrypt | 4.1.0 | Haszowanie haseł kont sync |
| SQLAlchemy | 2.0.0 | ORM |
