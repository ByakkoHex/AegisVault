# AegisVault

Bezpieczny, wieloplatformowy menedżer haseł z szyfrowaniem AES-256, uwierzytelnianiem dwuskładnikowym (TOTP), kluczem recovery, audytem aktywności, opcjonalną synchronizacją między urządzeniami i wtyczką do przeglądarki.

---

## Funkcje

### Bezpieczeństwo
| Funkcja | Opis |
|---------|------|
| Szyfrowanie AES-256 | Każde hasło szyfrowane osobno kluczem pochodnym od hasła głównego (Fernet) |
| Argon2id KDF | Wyprowadzanie klucza — odporny na ataki GPU/ASIC, winner PHC 2015 (64 MB RAM, 3 iteracje) |
| Argon2id hashing | Hasło masterowe hashowane Argon2id — nigdy nie zapisywane w plaintext |
| 2FA / TOTP | Kompatybilny z Google Authenticator, Microsoft Authenticator, Authy |
| TOTP w wpisach | Wbudowany authenticator per wpis — aktywny kod + timer jak 1Password |
| Push 2FA | Zatwierdzanie logowania kliknięciem w przeglądarce (własny serwer) |
| Klucz recovery | 12-wyrazowa fraza odzyskiwania — reset masterhasła bez utraty danych |
| Szyfrowanie TOTP | Sekret TOTP szyfrowany kluczem z OS keyring (Windows Credential Store / macOS Keychain) |
| HaveIBeenPwned | Sprawdzanie wycieków metodą k-anonymity — hasło nigdy nie opuszcza urządzenia |
| Limit logowania | Blokada po błędnych próbach + exponential cooldown dla TOTP |
| Screen capture | Ochrona okna przed zrzutami ekranu (`SetWindowDisplayAffinity`, Windows) |
| Clipboard guard | Auto-clear schowka po 30s + opcjonalne czyszczenie historii Win+V |
| Audit log | Dziennik aktywności: logowania, kopiowania, zmiany haseł, eksport — 90 dni |

### Zarządzanie hasłami
| Funkcja | Opis |
|---------|------|
| Daty ważności | ⛔ wygasłe / ⏰ wkrótce wygasają (≤7 dni) |
| Historia haseł | Archiwum poprzednich wersji (maks. 10), możliwość przywrócenia |
| Własne pola | KeePass-style custom fields (klucz-wartość, szyfrowane) per wpis |
| Secure Notes | Zaszyfrowane notatki bez pola hasła — osobna kategoria |
| Kosz | Przenoszenie do kosza, przywracanie, auto-czyszczenie po 30 dniach |
| Kategorie | Wbudowane (Social Media, Praca, Bankowość…) + własne z kolorem i ikoną |
| Bulk operacje | Zaznaczanie wielu wpisów, przenoszenie, usuwanie zbiorcze, eksport zaznaczonych |
| Sortowanie | Klikalne nagłówki: nazwa, data dodania, ostatnio użyte, siła |
| Import | LastPass CSV, Bitwarden JSON, 1Password CSV, Generic CSV |
| Eksport | Generic CSV, Bitwarden JSON, 1Password CSV, KeePass XML |
| Integrity check | `PRAGMA integrity_check` przy starcie — wykrywanie uszkodzeń bazy |

### Generatory
| Funkcja | Opis |
|---------|------|
| Generator haseł | Kryptograficznie bezpieczny (`secrets`), konfigurowalny zestaw znaków i długość |
| Passphrase (Diceware) | Generator fraz z listy EFF — np. `correct-horse-battery-staple`, slider słów, pasek entropii |

### Interfejs i użyteczność
| Funkcja | Opis |
|---------|------|
| PyQt6 UI | Nowoczesny interfejs — migracja z customtkinter zakończona w v1.3.0 |
| Security Score | Wynik 0–100 widoczny w topbarze (siła + ważność + unikalność) |
| Toasty | Niemodalne powiadomienia (sukces/błąd/info) z animacją fade |
| Tray icon | Minimalizacja do zasobnika systemowego |
| Skróty klawiszowe | `Ctrl+N` nowe, `Ctrl+F` szukaj, `Ctrl+L` wyloguj, `Ctrl+W` zamknij |
| Dark / Light mode | Przełącznik w ustawieniach |
| Kolory akcentu | Wybór koloru akcentu w ustawieniach |
| Tryb kompaktowy | Zmniejszony widok listy haseł |
| Windows Hello | Biometryczne odblokowywanie (Windows 10/11 z PIN/odciskiem) |
| Autostart | Opcja uruchamiania z systemem Windows |
| Auto-aktualizacja | Sprawdzanie nowych wersji, changelog, pobieranie instalatora |
| Synchronizacja | Opcjonalny serwer FastAPI — dane zawsze szyfrowane po stronie klienta |
| Wtyczka przeglądarkowa | Autouzupełnianie formularzy w Chrome, Firefox, Edge |
| Cross-platform | Windows, macOS, Linux — jeden kod źródłowy |

---

## Szybki start

### Wymagania

- Python 3.10 lub nowszy
- pip

### Instalacja

```bash
# 1. Sklonuj lub pobierz projekt
# 2. Zainstaluj zależności
pip install -r requirements.txt

# 3. Uruchom aplikację
py main.py          # Windows
python3 main.py     # macOS / Linux
```

Baza danych tworzona jest automatycznie przy pierwszym uruchomieniu:
- Windows: `%APPDATA%\AegisVault\aegisvault.db`
- macOS: `~/Library/Application Support/AegisVault/aegisvault.db`
- Linux: `~/.local/share/aegisvault/aegisvault.db`

### Serwer synchronizacji (opcjonalny)

```bash
# Windows
start_server.bat

# macOS / Linux
bash start_server.sh
```

Serwer dostępny pod `http://localhost:8000`. Dokumentacja API: `http://localhost:8000/docs`.

---

## Struktura projektu

```
AegisVault/
├── main.py                     # Punkt wejścia aplikacji desktop
│
├── core/                       # Kryptografia i 2FA
│   ├── crypto.py               # AES-256, Argon2id KDF, generator haseł
│   └── totp.py                 # TOTP (RFC 6238), QR kody
│
├── database/                   # Warstwa danych
│   ├── models.py               # Modele SQLAlchemy: User, Password, PasswordHistory,
│   │                           #   CustomCategory, AuditLog, PasswordField
│   └── db_manager.py           # CRUD: hasła, kosz, historia, kategorie, audit log, TOTP
│
├── gui_qt/                     # Interfejs graficzny (PyQt6) — aktywny
│   ├── login_window.py         # Logowanie, rejestracja, 2FA, reset hasła, wizard importu
│   ├── main_window.py          # Główne okno: lista, sidebar, Security Score, bulk, sortowanie
│   ├── settings_window.py      # Ustawienia: motyw, hasło, 2FA, recovery, Windows Hello
│   ├── gradient.py             # Animowany separator gradientowy
│   └── ...                     # Pozostałe komponenty Qt
│
├── gui/                        # Interfejs graficzny (customtkinter) — legacy
│
├── server/                     # Serwer synchronizacji (FastAPI)
│   ├── main.py                 # Endpointy API
│   ├── auth.py                 # JWT, Argon2id
│   └── models.py               # Modele serwera
│
├── extension/                  # Wtyczka przeglądarkowa (WebExtension MV3)
│   ├── manifest.json
│   ├── background/             # Service Worker
│   ├── content/                # Content Script (autofill)
│   └── popup/                  # Interfejs popup
│
├── native_host/                # Python Native Messaging Host
│   ├── aegisvault_host.py      # Główna pętla hosta
│   ├── host_protocol.py        # Protokół 4-bajtowy
│   ├── host_session.py         # Sesja w pamięci
│   └── install/                # Instalator hosta
│
├── utils/                      # Narzędzia pomocnicze
│   ├── paths.py                # Cross-platform ścieżki danych
│   ├── password_strength.py    # Ocena siły haseł
│   ├── security_score.py       # Security Score 0-100
│   ├── hibp.py                 # HaveIBeenPwned (k-anonymity)
│   ├── import_manager.py       # Import: LastPass, Bitwarden, 1Password, CSV
│   ├── export_manager.py       # Eksport: CSV, Bitwarden JSON, 1Password CSV, KeePass XML
│   ├── clipboard.py            # Bezpieczne kopiowanie + auto-clear + Win clipboard history
│   ├── auto_backup.py          # Automatyczne kopie zapasowe bazy
│   ├── autostart.py            # Autostart z systemem Windows
│   ├── recovery.py             # Klucz recovery — generowanie i weryfikacja
│   ├── windows_hello.py        # Windows Hello (biometria + PIN)
│   ├── updater.py              # Auto-aktualizacja z GitHub Releases
│   ├── prefs_manager.py        # Singleton preferencji UI
│   ├── push_auth.py            # Klient Push 2FA
│   └── sync_client.py          # Klient HTTP synchronizacji
│
├── assets/fonts/               # Czcionki aplikacji
├── requirements.txt            # Zależności klienta
├── requirements-server.txt     # Zależności serwera
├── aegisvault.spec             # Konfiguracja PyInstaller
├── start_server.bat            # Uruchomienie serwera (Windows)
├── start_server.sh             # Uruchomienie serwera (macOS/Linux)
└── .github/workflows/build.yml # CI/CD — automatyczne buildy Windows/macOS/Linux
```

---

## Szczegóły bezpieczeństwa

### Przepływ szyfrowania

```
Hasło masterowe + Sól (32B)
         │
         ▼  Argon2id (time=3, mem=64MB, par=4)
      Klucz AES-256 (w RAM, nigdy na dysku)
         │
         ▼  Fernet (AES-128-CBC + HMAC-SHA256)
   Zaszyfrowane hasło → SQLite
```

### Weryfikacja hasła masterowego

```
Rejestracja: hasło → Argon2id(time=3, mem=64MB) → baza danych
Logowanie:   Argon2id.verify(hasło, hash) → True/False
```

### Szyfrowanie sekretu TOTP

```
Fernet.generate_key() → zapisany w OS keyring (Windows Credential Store / macOS Keychain)
Fernet(key).encrypt(totp_secret) → aegisvault.db
```

Sekret TOTP jest zaszyfrowany niezależnie od masterhasła — kradzież samego pliku bazy nie ujawnia sekretu.

### HaveIBeenPwned (k-anonymity)

```
SHA1(hasło) = ABCDE12345...
Wysyłane: GET /range/ABCDE   ← tylko 5 znaków prefiksu
Odpowiedź: lista sufiksów z licznikami
Sprawdzane lokalnie: czy 12345... jest na liście
```

### Security Score (0–100)

| Składnik | Waga | Szczegóły |
|---|---|---|
| Siła haseł | 40 pkt | Średnia ze wszystkich haseł (0–100%) |
| Ważność | 30 pkt | `-8` za wygasłe, `-3` za wkrótce wygasające |
| Unikalność | 30 pkt | `-6` za każde zduplikowane hasło |

---

## Skróty klawiszowe

| Skrót | Akcja |
|---|---|
| `Ctrl+N` | Dodaj nowe hasło |
| `Ctrl+F` | Fokus na wyszukiwarce |
| `Ctrl+L` | Wyloguj się |
| `Ctrl+W` | Zamknij / minimalizuj do tray |
| `Ctrl+A` | Zaznacz wszystkie wpisy |
| `Ctrl+D` | Duplikuj zaznaczony wpis |

---

## Import / Eksport haseł

### Import — obsługiwane formaty

| Format | Typ | Wykrywanie |
|---|---|---|
| **LastPass** | CSV | kolumna `grouping` |
| **Bitwarden** | JSON | pole `encrypted: false` |
| **1Password** | CSV | kolumna `notesPlain` |
| **Generic** | CSV | fallback |

### Eksport — obsługiwane formaty

| Format | Typ | Uwagi |
|---|---|---|
| **Generic CSV** | CSV | tytuł, login, hasło, URL, notatki |
| **Bitwarden** | JSON | kompatybilny z importem Bitwarden |
| **1Password** | CSV | kompatybilny z importem 1Password |
| **KeePass** | XML | format KeePass 2 |

> ⚠️ Pliki eksportu zawierają hasła w postaci niezaszyfrowanej — przechowuj je bezpiecznie i usuń po użyciu.

---

## Dokumentacja

| Dokument | Opis |
|----------|------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architektura systemu, przepływ danych |
| [SECURITY.md](docs/SECURITY.md) | Model bezpieczeństwa, kryptografia |
| [INSTALLATION.md](docs/INSTALLATION.md) | Instalacja na Windows, macOS, Linux |
| [DESKTOP_APP.md](docs/DESKTOP_APP.md) | Dokumentacja aplikacji desktop |
| [BROWSER_EXTENSION.md](docs/BROWSER_EXTENSION.md) | Dokumentacja wtyczki przeglądarkowej |
| [SYNC_SERVER.md](docs/SYNC_SERVER.md) | API serwera synchronizacji |
| [SERVER_DEPLOYMENT.md](docs/SERVER_DEPLOYMENT.md) | Wdrożenie serwera (Docker, VPS, cloud) |
| [INSTALLERS.md](docs/INSTALLERS.md) | Generowanie instalatorów (.exe, .dmg, .deb) |
| [BUILD.md](docs/BUILD.md) | Budowanie i pakowanie binariów |

---

## Roadmapa

- [x] Etap 1 — Cross-platform desktop (Windows, macOS, Linux)
- [x] Etap 2 — Wtyczka przeglądarkowa (Chrome, Firefox, Edge)
- [x] Etap 3 — Migracja UI do PyQt6 (v1.3.0)
- [ ] Etap 4 — Wielojęzyczność (Polski, English + kolejne)
- [ ] Etap 5 — Aplikacja mobilna (iOS, Android)

---

## Licencja

Copyright © 2026 Kamil Czajkowski (ByakkoHex). Wszelkie prawa zastrzeżone.

Projekt udostępniony na licencji **Source Available** — kod jest widoczny publicznie w celach przejrzystości i weryfikacji bezpieczeństwa, jednak **nie jest oprogramowaniem open source**.

| Działanie | Dozwolone? |
|-----------|-----------|
| Przeglądanie i czytanie kodu | ✅ Tak |
| Weryfikacja bezpieczeństwa | ✅ Tak |
| Zgłaszanie błędów i podatności | ✅ Tak |
| Używanie kodu w swoich projektach | ❌ Nie |
| Kopiowanie, modyfikowanie, tworzenie dzieł pochodnych | ❌ Nie |
| Dystrybucja, sublicencjonowanie, sprzedaż | ❌ Nie |
| Hostowanie własnej instancji na podstawie tego kodu | ❌ Nie |

Pełna treść licencji: [LICENSE](LICENSE)
