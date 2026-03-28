# AegisVault

Bezpieczny, wieloplatformowy menedżer haseł z szyfrowaniem AES-256, uwierzytelnianiem dwuskładnikowym (TOTP), opcjonalną synchronizacją między urządzeniami i wtyczką do przeglądarki.

---

## Funkcje

### Bezpieczeństwo
| Funkcja | Opis |
|---------|------|
| Szyfrowanie AES-256 | Każde hasło szyfrowane osobno kluczem pochodnym od hasła głównego (Fernet) |
| PBKDF2-HMAC-SHA256 | 480 000 iteracji — zgodnie z OWASP 2023 |
| bcrypt | Hasło masterowe hashowane bcrypt (rounds=12) — nigdy nie zapisywane w plaintext |
| 2FA / TOTP | Kompatybilny z Google Authenticator, Microsoft Authenticator, Authy |
| Push 2FA | Zatwierdzanie logowania kliknięciem w przeglądarce (własny serwer) |
| HaveIBeenPwned | Sprawdzanie wycieków metodą k-anonymity — hasło nigdy nie opuszcza urządzenia |
| Reset 2FA | Możliwość wygenerowania nowego QR po weryfikacji hasła masterowego |

### Zarządzanie hasłami
| Funkcja | Opis |
|---------|------|
| Daty ważności | ⛔ wygasłe / ⏰ wkrótce wygasają (≤7 dni) |
| Historia haseł | Archiwum poprzednich wersji (maks. 10), możliwość przywrócenia |
| Kosz | Przenoszenie do kosza, przywracanie, auto-czyszczenie po 30 dniach |
| Kategorie | Wbudowane (Social Media, Praca, Bankowość…) + własne z kolorem |
| Import | Automatyczny import z LastPass CSV, Bitwarden JSON, 1Password CSV, Generic CSV |
| Wizard importu | Kreator importu przy pierwszym uruchomieniu aplikacji |
| Generator haseł | Kryptograficznie bezpieczny (`secrets`), konfigurowalny zestaw znaków |

### Interfejs i użyteczność
| Funkcja | Opis |
|---------|------|
| Security Score | Wynik 0–100 widoczny w topbarze (siła + ważność + unikalność) |
| Toasty | Niemodalne powiadomienia (sukces/błąd/info) z animacją fade |
| Tray icon | Minimalizacja do zasobnika systemowego |
| Skróty klawiszowe | `Ctrl+N` nowe, `Ctrl+F` szukaj, `Ctrl+L` wyloguj, `Ctrl+W` zamknij |
| Dark / Light mode | Przełącznik w ustawieniach |
| Kolory akcentu | 5 motywów: niebieski, zielony, fioletowy, pomarańczowy, morski |
| Tryb kompaktowy | Zmniejszony widok listy haseł |
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
│   ├── crypto.py               # AES-256, PBKDF2, bcrypt, generator haseł
│   └── totp.py                 # TOTP (RFC 6238), QR kody
│
├── database/                   # Warstwa danych
│   ├── models.py               # Modele SQLAlchemy: User, Password, PasswordHistory, CustomCategory
│   └── db_manager.py           # CRUD: hasła, kosz, historia, kategorie, ważność
│
├── gui/                        # Interfejs graficzny (customtkinter)
│   ├── login_window.py         # Logowanie, rejestracja, 2FA (TOTP + Push), wizard importu
│   ├── main_window.py          # Główne okno: lista, sidebar, Security Score, skróty, tray
│   ├── settings_window.py      # Ustawienia: motyw, zmiana hasła, reset 2FA, usuń konto
│   ├── dialogs.py              # Własne dialogi (show_error, show_info, ask_yes_no)
│   ├── toast.py                # Powiadomienia niemodalne z animacją fade
│   ├── tray.py                 # Ikona zasobnika systemowego (pystray)
│   ├── security_analysis_window.py  # Szczegółowy raport bezpieczeństwa
│   └── sync_window.py          # Konfiguracja synchronizacji
│
├── server/                     # Serwer synchronizacji (FastAPI)
│   ├── main.py                 # Endpointy API
│   ├── auth.py                 # JWT, bcrypt
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
│   ├── font_manager.py         # Ładowanie fontów (cross-platform)
│   ├── password_strength.py    # Ocena siły haseł (wynik 0-4 + procent)
│   ├── security_score.py       # Security Score 0-100 (siła + ważność + unikalność)
│   ├── hibp.py                 # HaveIBeenPwned — sprawdzanie wycieków (k-anonymity)
│   ├── import_manager.py       # Import z LastPass, Bitwarden, 1Password, CSV
│   ├── prefs_manager.py        # Singleton — preferencje UI (motyw, compact mode)
│   ├── push_auth.py            # Klient Push 2FA (challenge, polling)
│   └── sync_client.py          # Klient HTTP synchronizacji
│
├── assets/fonts/               # Font Roboto (pobierany przy starcie)
├── requirements.txt            # Zależności klienta
├── requirements-server.txt     # Zależności serwera
├── aegisvault.spec             # Konfiguracja PyInstaller
├── start_server.bat            # Uruchomienie serwera (Windows)
├── start_server.sh             # Uruchomienie serwera (macOS/Linux)
└── .github/workflows/build.yml # CI/CD — automatyczne buildy
```

---

## Szczegóły bezpieczeństwa

### Przepływ szyfrowania

```
Hasło masterowe + Sól (16B)
         │
         ▼  PBKDF2-HMAC-SHA256 (480 000 iteracji)
      Klucz AES-256 (w RAM, nigdy na dysku)
         │
         ▼  Fernet (AES-128-CBC + HMAC-SHA256)
   Zaszyfrowane hasło → SQLite
```

### Weryfikacja hasła masterowego

```
Rejestracja: hasło → bcrypt(rounds=12) → baza danych
Logowanie:   bcrypt.checkpw(hasło, hash) → True/False
```

### HaveIBeenPwned (k-anonymity)

```
SHA1(hasło) = ABCDE12345...
Wysyłane: GET /range/ABCDE   ← tylko 5 znaków
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

---

## Import haseł

Obsługiwane formaty wykrywane automatycznie po strukturze pliku:

| Format | Typ | Wykrywanie |
|---|---|---|
| **LastPass** | CSV | kolumna `grouping` |
| **Bitwarden** | JSON | pole `encrypted: false` |
| **1Password** | CSV | kolumna `notesPlain` |
| **Generic** | CSV | fallback |

Dostępny też **kreator importu** przy pierwszym uruchomieniu aplikacji.

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
- [ ] Etap 3 — Aplikacja mobilna (iOS, Android)

---

## Licencja

Projekt dostępny na licencji **GNU Affero General Public License v3.0 (AGPL-3.0)**.

Możesz używać, modyfikować i dystrybuować kod — pod warunkiem że zachowasz tę samą licencję i udostępnisz zmiany (w tym kod serwera jeśli go hostujesz).

Zobacz plik [LICENSE](LICENSE) lub [gnu.org/licenses/agpl-3.0](https://www.gnu.org/licenses/agpl-3.0.html).
