# Model bezpieczeństwa AegisVault

## Zasady projektowe

1. **Zero-knowledge** — serwer synchronizacji nigdy nie widzi odszyfrowanych danych.
2. **Klucz tylko w pamięci** — pochodny klucz AES nigdy nie jest zapisywany na dysk.
3. **Niezależne szyfrowanie** — każde hasło szyfrowane osobno; kompromitacja jednego wpisu nie ujawnia pozostałych.
4. **Obrona wielowarstwowa** — autentykacja (bcrypt) jest niezależna od szyfrowania (AES). Złamanie jednej warstwy nie kompromituje drugiej.

---

## Kryptografia

### Haszowanie hasła głównego

```
bcrypt(master_password, rounds=12) → master_password_hash
```

- Algorytm: bcrypt z kosztem 12 (≈250ms na typowym CPU — celowo wolny)
- Przechowywany: **wyłącznie hash**, nigdy plaintext
- Cel: weryfikacja tożsamości przy logowaniu

### Wyprowadzanie klucza szyfrowania

```
PBKDF2-HMAC-SHA256(
    password = master_password,
    salt     = user.salt,          ← 16 losowych bajtów, unikalne per user
    iterations = 480_000,          ← OWASP 2023 recommendation
    dklen    = 32                  ← 256 bitów
) → raw_key → Fernet(raw_key) → CryptoManager
```

- 480 000 iteracji ≈ kilka sekund na atakującym GPU — wyprowadzanie jest celowo kosztowne
- Salt jest unikalny dla każdego użytkownika — uniemożliwia ataki z precomputed tables
- Klucz istnieje **wyłącznie w RAM** przez czas trwania sesji

### Szyfrowanie wpisów

```
Fernet.encrypt(plaintext) →  [HMAC-SHA256 | IV | AES-256-CBC(plaintext)]
```

- Algorytm: AES-256-CBC z losowym IV per operację
- HMAC-SHA256 zapewnia integralność — modyfikacja zaszyfrowanego blob-a jest wykrywalna
- Każde hasło szyfrowane osobno własnym wywołaniem `encrypt()` z nowym IV

### Uwierzytelnianie dwuskładnikowe (2FA)

```
secret = pyotp.random_base32()                    ← generowane przy rejestracji
code   = TOTP(secret, digits=6, interval=30)      ← RFC 6238
verify(code, valid_window=1)                      ← akceptuje ±1 okres (±30s)
```

- Kompatybilny z Google Authenticator, Authy, 1Password, Bitwarden
- QR kod generowany w formacie `otpauth://totp/...`
- Brak replay protection poza naturalnym oknem czasowym TOTP (60s tolerancja)

---

## Gdzie co jest przechowywane

| Dane | Lokalizacja | Forma |
|------|-------------|-------|
| Hasło główne | **Nigdzie** (nigdy nie jest zapisywane) | — |
| Hash hasła głównego | `aegisvault.db` → tabela `users` | bcrypt hash |
| Salt użytkownika | `aegisvault.db` → tabela `users` | 16 bajtów plaintext |
| Secret TOTP | `aegisvault.db` → tabela `users` | Base32 plaintext |
| Zaszyfrowane hasła | `aegisvault.db` → tabela `passwords` | Fernet blob |
| Klucz AES (Fernet) | **Wyłącznie RAM** podczas sesji | In-memory |
| Token JWT (sync) | RAM aplikacji podczas sesji sync | In-memory |
| Dane na serwerze sync | `server_data.db` | Zaszyfrowane blob-y (serwer nie ma klucza) |

---

## Sesja i automatyczne blokowanie

### Aplikacja desktop

- **Auto-lock**: 5 minut braku aktywności → ponowne wymaganie hasła głównego
- Aktywność: każde kliknięcie lub naciśnięcie klawisza resetuje timer
- Po blokadzie: `CryptoManager` jest usuwany z pamięci — klucz AES znika

### Wtyczka przeglądarkowa

- Sesja przechowywana w `chrome.storage.session` (automatycznie czyszczona przy zamknięciu przeglądarki)
- **Sliding expiry**: każde żądanie uwierzytelnione przesuwa czas wygaśnięcia o 5 minut
- Klucz AES żyje w procesie Native Host (`host_session.py`) — nie w storage przeglądarki
- Chrome Alarms sprawdzają wygaśnięcie co minutę i aktualizują badge

### Schowek systemowy

- Skopiowane hasło jest **automatycznie usuwane ze schowka po 30 sekundach**
- Odliczanie widoczne w pasku statusu aplikacji desktop

---

## Bezpieczeństwo wtyczki przeglądarkowej

### Izolacja od strony internetowej

- Chip autofill renderowany w **closed Shadow DOM** — strona nie ma dostępu przez `element.shadowRoot`
- Content script działa w izolowanym kontekście JS — strona nie może wywołać funkcji rozszerzenia
- Odszyfrowane hasła nigdy nie trafiają do kontekstu JS strony — tylko bezpośrednio do pól formularza przez `HTMLInputElement.prototype.value setter`

### Przepływ hasła głównego

```
Pole tekstowe popup
      ↓  (jednorazowo, przy UNLOCK)
popup.js  →  chrome.runtime.sendMessage
      ↓
service_worker.js  →  port.postMessage (native messaging)
      ↓
aegisvault_host.py: CryptoManager(password, salt) → Fernet key
      ↓  (hasło główne eligible for GC)
Klucz AES w host_session._crypto (RAM procesu hosta)
```

Po wywołaniu `UNLOCK`, hasło główne:
- W `popup.js`: pole czyszczone (`input.value = ""`)
- W `service_worker.js`: nigdy nie przechowywane, tylko retransmitowane
- W procesie hosta: przekazane do `CryptoManager()`, po czym dostępne dla GC

### Native Messaging — izolacja

- Port native messaging jest per-extension (identyfikowany przez `allowed_origins` w manifeście hosta)
- Tylko rozszerzenie z konkretnym Extension ID może się połączyć z hostem
- Komunikacja przez pipe IPC (stdin/stdout) — niedostępna dla innych procesów użytkownika (standardowe uprawnienia OS)

### Lista uprawnień rozszerzenia (i uzasadnienie)

| Uprawnienie | Cel |
|-------------|-----|
| `nativeMessaging` | Połączenie z Python hostem |
| `activeTab` | Odczyt URL aktywnej karty (do dopasowania haseł) |
| `storage` | Przechowywanie stanu sesji (nie przechowuje haseł) |
| `scripting` | Fallback do wstrzykiwania content script |
| `alarms` | Sprawdzanie wygaśnięcia sesji w tle |
| `<all_urls>` | Content script musi działać na każdej stronie |

---

## Bezpieczeństwo serwera synchronizacji

- Serwer przechowuje zaszyfrowane blob-y — **nie posiada klucza deszyfrowania**
- Osobne konto na serwerze (login/hasło) — niezależne od hasła głównego
- JWT z 30-dniową ważnością (HS256)
- Soft-delete: usunięte wpisy pozostają w bazie z `deleted=1` — niewidoczne dla klienta

> **WAŻNE**: Klucz JWT w `server/auth.py` (`SECRET_KEY`) należy zmienić przed wdrożeniem produkcyjnym. Wartość domyślna to placeholder.

---

## Eksport / Backup

Format pliku `.aegis`:

```json
{
  "version": "1.0",
  "exported_at": "2025-01-01T00:00:00",
  "username": "user",
  "count": 42,
  "data": "<Base64(Fernet.encrypt(JSON_z_hasłami))>"
}
```

- Cały zbiór haseł zaszyfrowany kluczem AES użytkownika
- Bez znajomości hasła głównego plik jest bezużyteczny
- Plik można bezpiecznie przechowywać w chmurze lub wysłać e-mailem

---

## Znane ograniczenia

| Ograniczenie | Uzasadnienie |
|--------------|--------------|
| TOTP brak replay protection | Okno 60s jest akceptowalne w modelu zagrożeń |
| SQLite bez WAL (serwer) | Wystarczające dla małej liczby użytkowników |
| Jeden użytkownik per instancja (desktop) | Izolacja kont przez oddzielne profile OS |
| Secret TOTP w bazie plaintext | Wymagane do weryfikacji — chronione przez szyfrowanie pliku bazy (planowane) |
