# Model bezpieczeństwa AegisVault

## Zasady projektowe

1. **Zero-knowledge** — serwer synchronizacji nigdy nie widzi odszyfrowanych danych.
2. **Klucz tylko w pamięci** — pochodny klucz AES nigdy nie jest zapisywany na dysk.
3. **Niezależne szyfrowanie** — każde hasło szyfrowane osobno; kompromitacja jednego wpisu nie ujawnia pozostałych.
4. **Obrona wielowarstwowa** — autentykacja (Argon2id) jest niezależna od szyfrowania (AES). Złamanie jednej warstwy nie kompromituje drugiej.
5. **Minimalna powierzchnia ataku** — sekrety 2FA zaszyfrowane niezależnie od masterhasła, schowek czyszczony automatycznie, ochrona przed zrzutami ekranu.

---

## Kryptografia

### Haszowanie hasła głównego

```
Argon2id(
    password   = master_password,
    salt       = random 32B,
    time_cost  = 3,
    memory_cost = 65536  (64 MB),
    parallelism = 4
) → master_password_hash
```

- Algorytm: **Argon2id** — zwycięzca Password Hashing Competition 2015, złoty standard OWASP 2023
- Odporny na ataki GPU i ASIC dzięki wymogowi pamięci RAM (64 MB per próba)
- Przechowywany: **wyłącznie hash**, nigdy plaintext
- Cel: weryfikacja tożsamości przy logowaniu

> Wcześniejsze wersje używały PBKDF2-HMAC-SHA256 + bcrypt. Istniejące konta są automatycznie migrowane do Argon2id przy pierwszym logowaniu po aktualizacji.

### Wyprowadzanie klucza szyfrowania

```
Argon2id(
    password    = master_password,
    salt        = user.salt,         ← 32 losowe bajty, unikalne per user
    time_cost   = 3,
    memory_cost = 65536,
    parallelism = 4,
    hash_len    = 32
) → raw_key → base64url → Fernet(key) → CryptoManager
```

- Salt unikalny dla każdego użytkownika — uniemożliwia ataki z precomputed tables
- Klucz istnieje **wyłącznie w RAM** przez czas trwania sesji
- Po wylogowaniu / auto-lock: `CryptoManager` usuwany z pamięci

### Szyfrowanie wpisów

```
Fernet.encrypt(plaintext) →  [HMAC-SHA256 | IV | AES-128-CBC(plaintext)]
```

- Algorytm: AES-128-CBC z losowym IV per operację
- HMAC-SHA256 zapewnia integralność — modyfikacja zaszyfrowanego blob-a jest wykrywalna
- Każde hasło szyfrowane osobno własnym wywołaniem `encrypt()` z nowym IV
- Szyfrowane: hasło, wartości własnych pól (custom fields), treść zaszyfrowanych notatek

### Uwierzytelnianie dwuskładnikowe (2FA)

```
secret = pyotp.random_base32()                    ← generowane przy rejestracji
code   = TOTP(secret, digits=6, interval=30)      ← RFC 6238
verify(code, valid_window=1)                      ← akceptuje ±1 okres (±30s)
```

- Kompatybilny z Google Authenticator, Authy, Microsoft Authenticator, 1Password, Bitwarden
- QR kod generowany w formacie `otpauth://totp/AegisVault:username`
- Wbudowany authenticator per wpis hasła (kolumna `otp_secret` w `passwords`)

### Szyfrowanie sekretu TOTP

```
key = Fernet.generate_key()
keyring.set_password("AegisVault.totp", username, key)   ← OS keyring

user.totp_secret = Fernet(key).encrypt(totp_secret_base32)
```

- Klucz szyfrowania sekretu TOTP przechowywany w **OS keyring**:
  - Windows: Windows Credential Store
  - macOS: Keychain
  - Linux: SecretService (GNOME Keyring / KWallet)
- Kradzież samego pliku bazy danych NIE ujawnia sekretu TOTP
- Fallback: jeśli keyring niedostępny — sekret przechowywany jako plaintext z ostrzeżeniem w logu

### Klucz recovery

```
recovery_phrase → Argon2id(phrase, recovery_salt) → recovery_key
Fernet(recovery_key).encrypt(master_password) → recovery_encrypted_master
```

- 12-wyrazowa fraza generowana przy konfiguracji, przechowywana wyłącznie przez użytkownika
- Umożliwia reset masterhasła bez utraty zaszyfrowanych danych
- Wymagana do re-szyfrowania wszystkich wpisów nowym kluczem

---

## Gdzie co jest przechowywane

| Dane | Lokalizacja | Forma |
|------|-------------|-------|
| Hasło główne | **Nigdzie** (nigdy nie jest zapisywane) | — |
| Hash hasła głównego | `aegisvault.db` → tabela `users` | Argon2id hash |
| Salt użytkownika | `aegisvault.db` → tabela `users` | 32 bajty plaintext |
| Sekret TOTP (konta) | `aegisvault.db` → tabela `users` | Fernet-encrypted |
| Klucz szyfrowania TOTP | OS keyring (per użytkownik) | Fernet key |
| Recovery phrase | **Wyłącznie u użytkownika** (wydruk / menedżer haseł) | — |
| Encrypted master (recovery) | `aegisvault.db` → tabela `users` | Fernet-encrypted |
| Zaszyfrowane hasła | `aegisvault.db` → tabela `passwords` | Fernet blob |
| Custom fields | `aegisvault.db` → tabela `password_fields` | Fernet blob |
| Sekret TOTP (wpisy) | `aegisvault.db` → tabela `passwords` | Fernet blob |
| Klucz AES (Fernet) | **Wyłącznie RAM** podczas sesji | In-memory |
| Token JWT (sync) | RAM aplikacji podczas sesji sync | In-memory |
| Dane na serwerze sync | `server_data.db` | Zaszyfrowane blob-y (serwer nie ma klucza) |

---

## Sesja i automatyczne blokowanie

### Aplikacja desktop

- **Auto-lock**: 5 minut braku aktywności → ponowne wymaganie hasła głównego
- Aktywność: każde kliknięcie lub naciśnięcie klawisza resetuje timer
- Po blokadzie: `CryptoManager` jest usuwany z pamięci — klucz AES znika

### Limit prób logowania

- Max prób wpisania masterhasła → exponential cooldown (konfigurowalny)
- TOTP: po 3 błędnych kodach → 30s cooldown
- Licznik resetuje się po poprawnym logowaniu

### Wtyczka przeglądarkowa

- Sesja przechowywana w `chrome.storage.session` (automatycznie czyszczona przy zamknięciu przeglądarki)
- **Sliding expiry**: każde żądanie uwierzytelnione przesuwa czas wygaśnięcia o 5 minut
- Klucz AES żyje w procesie Native Host (`host_session.py`) — nie w storage przeglądarki
- Chrome Alarms sprawdzają wygaśnięcie co minutę i aktualizują badge

### Schowek systemowy

- Skopiowane hasło jest **automatycznie usuwane ze schowka po 30 sekundach**
- Odliczanie widoczne w pasku statusu aplikacji desktop
- Opcjonalne: czyszczenie historii schowka Windows (Win+V) przez WinRT API

---

## Ochrona ekranu (Windows)

```python
SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
```

- Okno aplikacji jest wykluczone z zrzutów ekranu i nagrań ekranu
- Zawartość widoczna wyłącznie live — na screenshotach pojawia się czarny prostokąt
- Działa na Windows 10 2004+ (build 19041)
- Toggle w ustawieniach: "Chroń okno przed zrzutami ekranu"

---

## Audit log

Tabela `audit_log` rejestruje:

| Zdarzenie | Kiedy |
|-----------|-------|
| `login_ok` / `login_fail` | Każda próba logowania |
| `password_copied` | Skopiowanie hasła do schowka |
| `password_created` / `edited` / `deleted` | Operacje na wpisach |
| `master_changed` | Zmiana hasła masterowego |
| `2fa_enabled` / `2fa_disabled` | Zmiany ustawień 2FA |
| `export` | Eksport danych |
| `import` | Import danych |

- Ostatnie 90 dni, auto-purge starszych wpisów
- Widoczny w settings → zakładka Bezpieczeństwo

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

### Native Messaging — izolacja

- Port native messaging jest per-extension (identyfikowany przez `allowed_origins` w manifeście hosta)
- Tylko rozszerzenie z konkretnym Extension ID może się połączyć z hostem
- Komunikacja przez pipe IPC (stdin/stdout) — niedostępna dla innych procesów użytkownika

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
| TOTP brak replay protection | Okno 60s jest akceptowalne w modelu zagrożeń desktop |
| Jeden użytkownik per instancja (desktop) | Izolacja kont przez oddzielne profile OS |
| Keyring fallback = plaintext TOTP | Gdy OS keyring niedostępny (np. headless Linux), sekret TOTP nie jest szyfrowany — logowane jako ostrzeżenie |
| Bezpieczne czyszczenie RAM | Python GC nie gwarantuje natychmiastowego usunięcia klucza po wylogowaniu |
| Screen capture tylko Windows | `SetWindowDisplayAffinity` dostępne wyłącznie na Windows 10 2004+ |
