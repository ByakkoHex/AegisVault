# AegisVault — Backlog funkcji (poza animacjami)

Priorytetyzacja: 🔴 krytyczne bezpieczeństwo / 🟠 ważne UX / 🟡 przydatne / 🟢 nice-to-have

---

## 🔐 Kryptografia i bezpieczeństwo

### ✅ Argon2id zamiast PBKDF2 + bcrypt

Zaimplementowane w `core/crypto.py` — commit `0b03cf8`.
Parametry: `time_cost=3, memory_cost=65536 (64MB), parallelism=4`.
Pole `kdf_version` w tabeli `users` (0=PBKDF2+bcrypt, 1=Argon2id).
Migracja przy pierwszym logowaniu w tle.

---

### ✅ Reset masterhasła (offline, bez serwera)

Zaimplementowane — commity `5b08e88` + `11f3e95`.
Flow: TOTP → formularz nowego masterhasła → re-szyfrowanie wpisów.
`change_master_password()` w `db_manager.py`.

---

### ✅ Klucz recovery (backup unlock)

Zaimplementowane — commit `11f3e95`, `utils/recovery.py`.
12-wyrazowy phrase → Argon2id → klucz → zaszyfrowane masterhasło.

---

### ✅ Fix: PasswordHistory re-encryption przy zmianie masterhasła

Naprawione — commit `bd2fed1`.
`change_master_password()` iteruje też `PasswordHistory` i kosz.

---

### ✅ Szyfrowanie sekretu TOTP w bazie

`totp_secret` szyfrowany Fernet-kluczem z OS keyring (`AegisVault.totp` / username).
`db_manager.get_totp_secret()` / `set_totp_secret()` / `has_totp()`.
Migracja automatyczna: stary plaintext odszyfruje się przez fallback, re-szyfrowanie przy następnym `set_totp_secret`.

---

### 🟠 Szyfrowanie pliku bazy danych (SQLCipher)

- [ ] Opcjonalne: użyć `sqlcipher3` (SQLCipher Python binding) zamiast zwykłego SQLite
- [ ] Klucz szyfrowania bazy = derive z masterhasła (oddzielna ścieżka od klucza Fernet)
- [ ] Alternatywa prostsza: szyfrowanie całego pliku `.db` AES przed zamknięciem (mniej wydajne)

---

### ✅ Limit prób logowania + lockout

Zaimplementowane — commit `547945b`.
Max prób → lockout z odliczaniem. TOTP cooldown po 3 błędnych kodach.

---

### 🟡 Bezpieczne czyszczenie pamięci

- [ ] Po wylogowaniu / auto-lock: wyzerować bajty klucza Fernet z RAM
  - Python nie gwarantuje natychmiastowego GC, ale `ctypes.memset` może pomóc
- [ ] Zmienna `self._fernet` w `CryptoManager` → po `destroy()` nadpisać `_fernet._signing_key`
- [ ] Schowek: już jest 30s auto-clear — OK

---

### 🟡 TOTP replay protection

- [ ] Przechowywać ostatnio użyty kod TOTP (TTL 60s) w pamięci
- [ ] Odrzucać ponowne użycie tego samego kodu w tym samym oknie czasowym
- [ ] Prosta implementacja: `Set` z `(code, timestamp//30)` — czyścić po upływie okna

---

### ✅ Audit log (dziennik zdarzeń)

Zaimplementowane — commit `edbd82f`.
Tabela `audit_log`, widok w settings, auto-purge po 90 dniach.

---

## 🖥️ UX / Funkcje desktopowe

### ✅ Ekran startowy (splash screen)

Zaimplementowane — `gui_qt/splash_screen.py`.
Bezramkowe okno 600×340, tło HexBackground z animacją "breath", logo + "AegisVault" + wersja.
Pasek postępu 3px z 5 etapami (prawdziwe ładowanie bazy przy kroku 40%).
Fade-out 350ms przed otwarciem LoginWindow.
Flaga `--no-splash` do pominięcia. Integracja w `main.py`.

---

### ✅ Logowanie zintegrowane z głównym oknem (single-window flow)

Zaimplementowane — `gui_qt/app_window.py`.
Jedno okno `AppWindow(QMainWindow)` przez cały cykl życia aplikacji.
`LoginWindow` i `MainWindow` w trybie `embedded=True` — sygnały zamiast `close()`.
Cross-fade 220ms + animacja rozmiaru okna przy przejściu login↔vault.
`main.py` uproszczony — tylko `AppWindow(db_path).show()`.

### 🟡 Logowanie zintegrowane z głównym oknem — do dopracowania

Aktualnie: `LoginWindow` i `MainWindow` to osobne okna — przy przejściu migotanie i zmiana rozmiaru.
Cel: jedno okno aplikacji przez cały cykl życia — przejście login → vault przez animację.

**Implementacja:**
- [ ] Główne okno `AppWindow(QMainWindow)` — nadrzędny kontener przez cały czas
- [ ] `QStackedWidget` jako centralny widget: strona 0 = login, strona 1 = vault
- [ ] Login (`LoginPanel`) i vault (`MainPanel`) jako `QWidget`, nie osobne `QMainWindow`
- [ ] Przejście: `QPropertyAnimation` na `opacity` lub `geometry` — fade / slide między stronami
- [ ] Rozmiar okna dostosowuje się animowanie (login ~480×640, vault ~1200×720)
- [ ] `_complete_login()` → `AppWindow.show_vault(user, crypto)`
- [ ] Wylogowanie → `AppWindow.show_login()` z fade-out vaultu
- [ ] Tytuł paska: "AegisVault — Logowanie" ↔ "AegisVault — {username}"
- [ ] Duże zadanie — wymaga refaktoru `LoginWindow` i `MainWindow` na panele

---

### 🟡 Windows Hello / biometria do odblokowywania (auto-lock)

Aktualnie: Windows Hello działa przy logowaniu (pierwsze uruchomienie).
Brakuje: odblokowanie po auto-lock przez WH / odpowiednik na macOS / Linux.

**Implementacja:**
- [ ] `utils/biometrics.py` — abstrakycja `BiometricUnlock.authenticate(reason) -> bool`:
  - Windows: `WinRT` `UserConsentVerifier` (już używane w `utils/windows_hello.py`) — reuse
  - macOS: `LocalAuthentication` framework przez `pyobjc-framework-LocalAuthentication`
  - Linux: `fprintd` przez D-Bus (`pydbus` / `dbus-python`)
- [ ] `main_window._lock_master_dialog()` i `_lock_pin_dialog()` — przycisk "Odblokuj przez Windows Hello" (tylko gdy WH dostępne)
- [ ] Po kliknięciu: wywołaj `BiometricUnlock.authenticate("Odblokuj AegisVault")` → jeśli OK → odblokuj
- [ ] Toggle w settings (zakładka Bezpieczeństwo): "Zezwól na odblokowanie biometryczne"
  - Domyślnie wyłączone — użytkownik musi świadomie włączyć
  - Osobny toggle per metoda: Windows Hello / Touch ID / Linia papilarnych
- [ ] Fallback: jeśli biometria niedostępna / anulowana → normalny PIN lub masterhasło
- [ ] `utils/windows_hello.py` już ma `is_available()` — rozszerzyć o `unlock()` dla auto-lock

---

### ✅ Pole URL per wpis + matching

Zaimplementowane — commit `22dd746`.
Kolumna `url` w modelu, pole w formularzu, przycisk "Otwórz stronę".

---

### ✅ Secure notes (zaszyfrowane notatki bez hasła)

Zaimplementowane — commit `22dd746`.
Typ `entry_type = "note"`, osobna kategoria w sidebarze, inna ikona.

---

### 🟠 Dialogi jako panele in-app (zamiast wyskakujących okien)

Aktualnie: większość akcji otwiera osobne okna systemowe (`QDialog.exec()`).
Wzorzec: okno ustawień (`SettingsWindow`) — slide-in panel wewnątrz głównego okna.

Okna do przepisania na styl in-app (slide-in panel):
- [ ] `PasswordFormDialog` — dodawanie / edycja hasła
- [ ] `NoteFormDialog` — dodawanie / edycja notatki
- [ ] `ExportDialog` — wybór formatu eksportu
- [ ] `TrashDialog` — kosz (aktualnie osobne okno)
- [ ] `CategoryDialog` — nowa kategoria

Mechanizm (wzorowany na `SettingsWindow`):
- [ ] Panel `QFrame` nakładany na `MainWindow` z prawej strony
- [ ] `QPropertyAnimation` na `geometry` — wjazd/wyjazd bez migania
- [ ] Ciemne tło-overlay (`QWidget` z `rgba(0,0,0,0.5)`) klikalny → zamknięcie panelu
- [ ] Klawisz Escape zamyka panel
- [ ] Bazowa klasa `SlidePanelBase(QFrame)` z metodami `slide_in()` / `slide_out()`

---

### ✅ Bulk operacje na wpisach

Zaimplementowane — commit `e23d2c9`.
Checkbox, toolbar, Ctrl+A, przenoszenie kategorii, kosz zbiorowy.

---

### ✅ PIN / quick unlock

Zaimplementowane — `db_manager.set_pin/verify_pin/clear_pin/has_pin()`, kolumna `users.pin_hash` (Argon2id, niski koszt).
`main_window._lock_pin_dialog()` — 6-cyfrowy PIN, po 3 błędach fallback na masterhasło.
Sekcja "PIN do odblokowywania" w settings — ustaw/zmień/usuń.

---

### 🟡 Globalna skróty klawiaturowe (system-wide hotkey)

- [ ] Ctrl+Shift+P (konfigurowalne) → przynieś AegisVault na wierzch z dowolnego miejsca
- [ ] Ctrl+Shift+C → quick-copy hasła dla ostatnio wybranego wpisu
- [ ] Implementacja: `keyboard` library lub Windows `RegisterHotKey` API przez ctypes
- [ ] Ustawienie w settings: "Globalne skróty" + pole rebind

---

### ✅ Autostart z Windows

Zaimplementowane — `utils/autostart.py`.
Wpis w `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, toggle w settings.

---

### 🟡 Lock przy blokadzie ekranu Windows

- [ ] Nasłuchiwanie `WM_WTSSESSION_CHANGE` (Windows) lub D-Bus `org.gnome.ScreenSaver` (Linux)
- [ ] Po wykryciu lock screena → auto-lock vaultu (wyczyść klucz z RAM)
- [ ] `utils/session_monitor.py` — thread nasłuchujący w tle

---

### 🟡 Wiele profili / vaultów

- [ ] Przy starcie: wybór profilu (lub "Nowy profil") jeśli istnieje więcej niż jeden
- [ ] Każdy profil = oddzielny plik `.db` + oddzielne masterhasło
- [ ] Zarządzanie profilami w settings: dodaj, usuń, zmień nazwę, zmień ścieżkę

---

### 🟡 Zaawansowane wyszukiwanie

- [ ] Operatory: `url:github.com`, `tag:praca`, `weak:true`, `expired:true`, `created:>2024-01-01`
- [ ] Podświetlanie dopasowań w wynikach
- [ ] Historia wyszukiwań (ostatnie 10, autocomplete)

---

### 🟢 Emergency access (dostęp awaryjny)

- [ ] Wyeksportuj zaszyfrowany vault zaszyfrowany kluczem publicznym zaufanej osoby
- [ ] Format: `vault.aegis.emergency` — odszyfrowanie wymaga klucza prywatnego odbiorcy
- [ ] Prostsza wersja: wydrukuj zaszyfrowany vault + recovery phrase jako "koperta awaryjna"

---

### 🟢 Password health report

- [ ] Eksport do PDF: lista słabych, starych, duplikatów + rekomendacje
- [ ] `utils/health_report.py` → `reportlab` lub `fpdf2`
- [ ] Przycisk w SecurityAnalysisWindow: "Eksportuj raport PDF"

---

## 📤 Import / Eksport

### ✅ Eksport do CSV / JSON / XML

Zaimplementowane — commit `4b95cb6`, `utils/export_manager.py`.
Formaty: Generic CSV, Bitwarden JSON, 1Password CSV, KeePass XML.

---

### 🟡 Scalanie vaultów (merge)

- [ ] Import z innego pliku `.aegis` → zamiast zastępowania, scalanie (duplikaty po URL/loginie = skip lub pytaj)
- [ ] Przydatne przy przejściu z innego urządzenia bez pełnego sync

---

## 🗄️ Baza danych

### ✅ SQLite WAL mode — już zaimplementowane

`models.py:123` — `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, `PRAGMA cache_size=-32000`, `PRAGMA busy_timeout=5000`.

---

### ✅ Database integrity check przy starcie

Zaimplementowane — commit `a6c3fee`.
`PRAGMA integrity_check` przy uruchomieniu, dialog przy błędzie.

---

## 📱 Migracja PyQt6 (branch feature/pyqt6-migration)

### ✅ PyQt6 migration — zrobione

Zmigrowane — commit `1c60aae` (v1.3.0). Wszystkie okna przepisane w `gui_qt/`.

---

## 🍎 macOS — instalator nie działa

**Objaw:** Gatekeeper blokuje aplikacje niepodpisane / nienotaryzowane.

**Szybki workaround dla testerów (nie fix):**
```
prawoklik na .app → Otwórz → "Otwórz mimo to"
# lub:
xattr -dr com.apple.quarantine AegisVault.app
```

**Właściwy fix — do zrobienia w `.github/workflows/build.yml`:**
- [ ] Ad-hoc signing:
  ```
  codesign --force --deep --sign - AegisVault.app
  ```
- [ ] Pełne code signing + notaryzacja (wymaga Apple Developer Program ~$99/rok)
- [ ] Sekrety w GitHub Actions: `APPLE_CERTIFICATE_P12`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_ID`, `APPLE_APP_PASSWORD`

---

## ⚠️ Znalezione problemy w kodzie (do naprawy)

### ✅ Import: UTF-8 BOM (Excel CSV) — już naprawione

`import_file()` używa `encoding="utf-8-sig"`.

---

### ✅ Import Bitwarden: typy non-login

Naprawione — `_from_bitwarden()` obsługuje:
- type 1 (Login) → wpis hasła + OTP z pola `login.totp`
- type 2 (Secure Note) → wpis notatki (`entry_type="note"`, kategoria "Notatki")
- type 3 (Card) / 4 (Identity) → po cichu pomijane (nieobsługiwany typ)

---

### ✅ Fix: datetime.utcnow() — deprecated w Python 3.12+

Naprawione — commit `900c9b5`. Zamienione na `datetime.now(timezone.utc)` we wszystkich plikach.

---

### ✅ Windows Clipboard History leak

Zaimplementowane — `utils/clipboard.py`, funkcja `copy_sensitive()`.
`dt.Clipboard.clear_history()` przez WinRT API, toggle w settings "Wyczyść historię schowka".

---

### ✅ Ochrona przed screen capture (Windows)

Zaimplementowane — commit `a6c3fee`.
`SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)`, toggle w settings.

---

### ✅ Sortowanie kolumn w liście haseł

Zaimplementowane — commit `a6c3fee`.
Klikalne nagłówki, zapamiętywanie sortowania w preferencjach.

---

### 🟡 Przeciągnij i upuść między kategoriami

- [ ] Drag & drop wpisu z listy na kategorię w sidebarze → przeniesienie kategorii
- [ ] Wizualny feedback: highlight kategorii przy hover podczas dragu

---

### ✅ Pola niestandardowe (custom fields)

Zaimplementowane — commit `a8b2302`.
Tabela `password_fields`, sekcja w formularzu, szyfrowane wartości.

---

## 🎮 Dodatkowe funkcje (pomysły)

### 🟡 Logowanie przez TOTP (login window)

- [ ] Opcja w settings: "Wymagaj TOTP przy logowaniu"
- [ ] LoginWindow: po poprawnym masterhaśle → dodatkowy krok z polem na 6-cyfrowy kod
- [ ] Weryfikacja przez `utils/totp.py` (już istnieje `verify_totp()`)
- [ ] Obsługa odzyskiwania: jeśli brak dostępu do authenticatora → login tylko przez klucz recovery

---

### ✅ Zapamiętanie TOTP na 30 dni ("Zaufaj tej maszynie")

Zaimplementowane — tabela `trusted_devices`, token UUID w keyring (`AegisVault.trusted / username`).
Checkbox na ekranie TOTP w login_window → zapisuje token po udanej weryfikacji.
Przy logowaniu: token z keyring → sprawdź w bazie → pomiń 2FA jeśli ważny.
Sekcja "Zaufane urządzenia" w settings — lista z datą wygaśnięcia + usuń per urządzenie / usuń wszystkie.

---

### ✅ TOTP authenticator wbudowany w wpisy

Zaimplementowane — commit `eb166c7`.
Kolumna `otp_secret` w `passwords`, aktywny kod w detail view, animowany timer, przycisk "Kopiuj kod".

---

### ✅ Diceware / passphrase generator

Zaimplementowane — commit `e2f6312`.
EFF wordlist, slider słów, separator, capitalize, pasek entropii. Drugi tab w generatorze.

---

### ✅ Duplikowanie wpisu

Zaimplementowane w obu GUI. `db_manager.duplicate_password()` — deep copy z custom fields i otp_secret.
Qt: duplikuje zaznaczony wpis (lub pierwszy widoczny), Ctrl+D.

---

### ✅ Szybkie kopiowanie loginu (username)

Zaimplementowane — `gui_qt/main_window.py` i `gui/main_window.py`.
Przycisk kopiowania loginu obok przycisku hasła.

---

### ✅ KeePass KDBX import

Zaimplementowane — `utils/import_manager.py`, `_from_keepass()` + `ImportManager.import_keepass()`.
Biblioteka `pykeepass` (dodana do `requirements.txt`).
Mapowanie: title, username, password, url, notes, grupy → category (pełna ścieżka), OTP z custom properties.
Dialog hasła KeePass w `main_window._import_keepass()`.
Filter pliku `.kdbx` dodany do dialogu importu zewnętrznego.

---

### 🟡 macOS Touch ID / Linux PAM

- [ ] macOS: `LocalAuthentication` framework przez `pyobjc-framework-LocalAuthentication`
- [ ] Linux: PAM (`python-pam`) lub `fprintd` przez D-Bus
- [ ] `utils/biometrics.py` — abstrakcja `BiometricAuth.authenticate()` → deleguje do platform-specific impl

---

## 🌍 Wielojęzyczność (i18n)

### 🟡 Obsługa wielu języków interfejsu

Aktualnie: cały interfejs wyłącznie po polsku (napisy hardcodowane).

- [ ] Biblioteka: `gettext` (stdlib) lub `babel` — `.po` / `.mo` pliki tłumaczeń
- [ ] Katalog `locales/` z plikami `pl/LC_MESSAGES/aegisvault.po`, `en/...`, itd.
- [ ] Funkcja `_(text)` — wszystkie napisy w UI przez `_("Tekst")`
- [ ] Ekstrakcja istniejących napisów: `xgettext` / `pybabel extract`
- [ ] Języki startowe: **Polski** (domyślny) + **English**
- [ ] Ustawienie w settings: "Język / Language" — dropdown, restart nie wymagany
- [ ] `utils/i18n.py` — `set_language(lang_code)` ładuje odpowiedni katalog
- [ ] Przygotowanie pod kolejne języki: Deutsch, Français, Español — po wypełnieniu pliku `.po`

---

## Pozostałe do zrobienia (priorytet)

```
[1]  Szyfrowanie TOTP secret w bazie     ← bezpieczeństwo
[2]  Dialogi in-app (slide panel)        ← UX (duże zadanie)
[3]  KeePass KDBX import                 ← często proszony
[4]  PIN / quick unlock                  ← komfort
[5]  Duplikowanie wpisu (Qt)             ← małe, brakuje w nowym GUI
[6]  Import Bitwarden non-login info     ← bugfix UX
[7]  Lock przy blokadzie ekranu          ← bezpieczeństwo
[8]  TOTP replay protection              ← bezpieczeństwo
[9]  Bezpieczne czyszczenie pamięci      ← bezpieczeństwo
[10] Globalne skróty klawiaturowe        ← komfort
[11] Zaawansowane wyszukiwanie           ← UX
[12] macOS Touch ID / Linux PAM          ← cross-platform
[13] SQLCipher                           ← opcjonalne
[14] Wiele profili / vaultów             ← zaawansowane
```
