# AegisVault — Backlog funkcji (poza animacjami)

Priorytetyzacja: 🔴 krytyczne bezpieczeństwo / 🟠 ważne UX / 🟡 przydatne / 🟢 nice-to-have

---

## 🔐 Kryptografia i bezpieczeństwo

### 🔴 Argon2id zamiast PBKDF2 + bcrypt

Aktualnie: `PBKDF2-HMAC-SHA256 (480k iter)` do derywacji klucza + `bcrypt (rounds=12)` do hashowania.
Argon2id jest odporny na ataki GPU i ASIC — złoty standard od 2015 (winner PHC).

- [ ] Zamienić `derive_key()` w `crypto.py`: `PBKDF2HMAC` → `argon2.low_level.hash_secret_raw()`
  - Parametry: `time_cost=3, memory_cost=65536 (64MB), parallelism=4`
  - Nowa sól: 32 bajty zamiast 16
- [ ] Zamienić `hash_master_password()`: `bcrypt` → `argon2.PasswordHasher`
  - Obie funkcje w jednym kroku: ten sam Argon2id derivuje klucz i weryfikuje hasło
  - **Uwaga:** wymaga migracji istniejących baz — przy pierwszym logowaniu re-hash w tle
- [ ] Dodać pole `kdf_version` w tabeli `users` (0=PBKDF2+bcrypt, 1=Argon2id) do backward compat
- [ ] Zaktualizować `docs/SECURITY.md`

---

### 🔴 Reset masterhasła (offline, bez serwera)

Flow:
1. Ekran logowania → przycisk "Nie pamiętam hasła"
2. Weryfikacja przez TOTP (kod z aplikacji authenticator) — jeśli 2FA jest włączone
3. Jeśli brak TOTP → tylko przez klucz recovery (patrz niżej)
4. Po weryfikacji → formularz nowego masterhasła
5. Re-szyfrowanie wszystkich wpisów: `decrypt(stary_klucz)` → `encrypt(nowy_klucz)`
6. Aktualizacja `master_password_hash` i `salt` w bazie

Pliki do zmian:
- `gui/login_window.py` — dodać link "Zapomniałem hasła"
- nowy `gui/reset_password_window.py` — okno resetu
- `database/db_manager.py` — `change_master_password(user, new_password)` (iteracja po wszystkich passwords + history)
- `core/crypto.py` — `reencrypt_all(entries, old_crypto, new_password)` (już jest `reencrypt()` per wpis)

---

### 🔴 Klucz recovery (backup unlock)

Problem: bez klucza recovery, zapomniane masterhasło = trwała utrata danych.

- [ ] Przy rejestracji/konfiguracji: generuj 12-wyrazowy recovery phrase (BIP-39 wordlist lub losowe)
- [ ] Phrase → Argon2id → klucz → zaszyfruj nim masterhasło → zapisz `encrypted_master` w bazie
- [ ] Przy resecie bez TOTP: wpisz recovery phrase → odszyfruj masterhasło → normalny reset flow
- [ ] GUI: `gui/recovery_setup_dialog.py` — wyświetl, wymuś przepisanie, potwierdź
- [ ] Opcja w settings: "Pokaż/regeneruj klucz recovery" (weryfikacja masterhasłem przed pokazaniem)

---

### 🟠 Szyfrowanie sekretu TOTP w bazie

Aktualnie `totp_secret` przechowywany jako plaintext Base32 w `users.totp_secret`.
`docs/SECURITY.md` sam to oznacza jako znane ograniczenie.

- [ ] Szyfrować `totp_secret` kluczem AES sesji (`crypto.encrypt(totp_secret)`)
- [ ] Przy enable 2FA — zapis zaszyfrowany, odczyt z decrypt w pamięci
- [ ] Migracja: przy pierwszym logowaniu po update — re-zapisz zaszyfrowany sekret

---

### 🟠 Szyfrowanie pliku bazy danych (SQLCipher)

- [ ] Opcjonalne: użyć `sqlcipher3` (SQLCipher Python binding) zamiast zwykłego SQLite
- [ ] Klucz szyfrowania bazy = derive z masterhasła (oddzielna ścieżka od klucza Fernet)
- [ ] Alternatywa prostsza: szyfrowanie całego pliku `.db` AES przed zamknięciem (mniej wydajne)

---

### 🟠 Limit prób logowania + lockout

- [ ] Max 5 prób błędnego hasła → 30s lockout (exponential: 5→30s, 10→5min, 15→trwały do restartu)
- [ ] Przechowywanie licznika w pamięci (nie bazie — nie powodować dyskowego I/O przy każdej próbie)
- [ ] Wyświetlanie w LoginWindow: "Pozostało X prób" / "Odblokowanie za Xs"

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

### 🟡 Audit log (dziennik zdarzeń)

- [ ] Nowa tabela `audit_log`: `id, event_type, entry_id, timestamp, details`
- [ ] Zdarzenia: login_ok, login_fail, password_copied, password_viewed, password_created, password_edited, password_deleted, master_changed, 2fa_enabled/disabled, export, import
- [ ] Widok w settings ("Dziennik aktywności") — filtrowalny po typie, ostatnie 100 wpisów
- [ ] Auto-purge po 90 dniach

---

## 🖥️ UX / Funkcje desktopowe

### 🟠 Pole URL per wpis + matching

Aktualnie: brak dedykowanego pola URL — wpisywane ręcznie w "notatki" lub "login".

- [ ] Dodać kolumnę `url TEXT` w tabeli `passwords` (migracja)
- [ ] Pole URL w `PasswordFormWindow` z walidacją (https://, auto-prefix)
- [ ] "Otwórz stronę" button w accordion / detail view
- [ ] Fuzzy matching URL → pole do przyszłej wtyczki przeglądarki

---

### 🟠 Secure notes (zaszyfrowane notatki bez hasła)

- [ ] Nowy typ wpisu: `entry_type = "note"` (vs `"password"`)
- [ ] Formularz bez pól login/hasło, tylko tytuł + treść (wieloliniowa)
- [ ] Osobna kategoria "Notatki" w sidebarze
- [ ] Wyświetlanie inną ikoną w liście (📝 zamiast 🔑)

---

### 🟠 Bulk operacje na wpisach

- [ ] Checkbox przy każdym wierszu (Shift+klik = zaznacz zakres)
- [ ] Toolbar pojawia się gdy zaznaczono > 0: "Przenieś do kategorii" / "Do kosza" / "Eksportuj zaznaczone"
- [ ] Skrót Ctrl+A = zaznacz wszystkie (w aktywnej kategorii)

---

### 🟠 PIN / quick unlock

- [ ] Opcjonalny 6-cyfrowy PIN jako szybki unlock po auto-lock (nie zastępuje masterhasła przy starcie)
- [ ] PIN → Argon2id → małokosztowy derive → odblokuj zapisany w RAM zaszyfrowany klucz sesji
- [ ] Próg: po 3 błędnych PIN → wymagane pełne masterhasło
- [ ] Toggle w settings: "Włącz PIN do odblokowywania"

---

### 🟡 Globalna skróty klawiaturowe (system-wide hotkey)

- [ ] Ctrl+Shift+P (konfigurowalne) → przynieś AegisVault na wierzch z dowolnego miejsca
- [ ] Ctrl+Shift+C → quick-copy hasła dla ostatnio wybranego wpisu
- [ ] Implementacja: `keyboard` library lub Windows `RegisterHotKey` API przez ctypes
- [ ] Ustawienie w settings: "Globalne skróty" + pole rebind

---

### 🟡 Autostart z Windows

- [ ] Toggle w settings: "Uruchamiaj z Windows"
- [ ] Implementacja: wpis w `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
- [ ] Opcja: "Minimalizuj do traya przy starcie"
- [ ] `utils/autostart.py` — enable/disable/is_enabled

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

- [ ] Wyeksportuj zaszyfrowany vault zaszyfrowany kluczem publiccznym zaufanej osoby
- [ ] Format: `vault.aegis.emergency` — odszyfrowanie wymaga klucza prywatnego odbiorcy
- [ ] Prostsza wersja: wydrukuj zaszyfrowany vault + recovery phrase jako "koperta awaryjna"

---

### 🟢 Password health report

- [ ] Eksport do PDF: lista słabych, starych, duplikatów + rekomendacje
- [ ] `utils/health_report.py` → `reportlab` lub `fpdf2`
- [ ] Przycisk w SecurityAnalysisWindow: "Eksportuj raport PDF"

---

## 📤 Import / Eksport

### 🟠 Eksport do CSV / JSON / XML

Aktualnie: tylko format `.aegis` (zaszyfrowany). Brak eksportu do standardowych formatów.

- [ ] `utils/export_manager.py` — mirror do `import_manager.py`
- [ ] Formaty wyjściowe:
  - **Generic CSV** — tytuł, login, hasło, URL, notatki
  - **Bitwarden JSON** — `{"encrypted": false, "items": [...]}` — identyczna struktura jak Bitwarden export, kompatybilna z importem Bitwarden
  - **Bitwarden XML** — jak Bitwarden export XML (`<Items><Item>...</Item></Items>`) — natywna biblioteka `xml.etree.ElementTree`, zero zależności
  - **KeePass XML** (`.kdbx` przez `pykeepass` lub plain `.xml` KeePass 2 format)
  - **1Password 1PUX** — ZIP z `export.data` w JSON (opcjonalnie)
- [ ] Ostrzeżenie przy każdym plaintext formacie: "Plik zawiera hasła niezaszyfrowane — przechowuj bezpiecznie"
- [ ] Opcja: eksport z szyfrowaniem AES (`export.aegis.xml` — XML wewnątrz Fernet bloba)
- [ ] Przycisk w settings obok "Importuj"

---

### 🟡 Scalanie vaultów (merge)

- [ ] Import z innego pliku `.aegis` → zamiast zastępowania, scalanie (duplikaty po URL/loginie = skip lub pytaj)
- [ ] Przydatne przy przejściu z innego urządzenia bez pełnego sync

---

## 🗄️ Baza danych

### ✅ SQLite WAL mode — już zaimplementowane

`models.py:123` — `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, `PRAGMA cache_size=-32000`, `PRAGMA busy_timeout=5000` ustawiane w `event.listens_for(engine, "connect")`. Nic do roboty.

---

### 🟡 Database integrity check przy starcie

- [ ] `PRAGMA integrity_check` przy każdym uruchomieniu (szybkie dla małych baz)
- [ ] Jeśli błąd → dialog "Baza uszkodzona, przywróć backup?" z listą backupów
- [ ] `PRAGMA foreign_keys=ON` — dodać do listy PRAGMA w `models.py:123`

---

## 📱 Migracja PyQt6 (branch feature/pyqt6-migration)

> Poniższe są blokerami do merge'a do main — patrz też `gui_change.md`

- [ ] Wszystkie okna z `gui/` przepisane w `gui_qt/`
- [ ] Animacje przeniesione na `QPropertyAnimation` / `QTimeLine`
- [ ] Tray icon przez `QSystemTrayIcon`
- [ ] Auto-lock timer przez `QTimer`
- [ ] Testy smoke wszystkich okien na Windows i Linux

---

## 🍎 macOS — instalator nie działa

**Objaw:** Instalator otwiera się, ale wyświetla "nie można uruchomić aplikacji" — app nie startuje.

**Prawdopodobna przyczyna:** Apple Gatekeeper blokuje aplikacje niepodpisane lub nienotaryzowane.
Każda `.app` / `.dmg` dystrybuowana poza App Store musi być podpisana certyfikatem deweloperskim
i przesłana do Apple do notaryzacji — inaczej macOS odmawia uruchomienia domyślnie.

**Szybki workaround dla testerów (nie fix):**
```
prawoklik na .app → Otwórz → "Otwórz mimo to"
# lub:
xattr -dr com.apple.quarantine AegisVault.app
```

**Właściwy fix — do zrobienia w `.github/workflows/build.yml`:**
- [ ] Ad-hoc signing (bezpłatne, nie wymaga Apple Developer Account, ale Gatekeeper nadal ostrzega):
  ```
  codesign --force --deep --sign - AegisVault.app
  ```
- [ ] Pełne code signing + notaryzacja (wymaga Apple Developer Program ~$99/rok):
  ```
  codesign --force --deep --sign "Developer ID Application: ..." AegisVault.app
  xcrun notarytool submit AegisVault.dmg --apple-id ... --wait
  xcrun stapler staple AegisVault.dmg
  ```
- [ ] Sekrety w GitHub Actions: `APPLE_CERTIFICATE_P12`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_ID`, `APPLE_APP_PASSWORD`
- [ ] Sprawdzić też czy sam build CI na macOS przechodzi — osobny problem od signing (logi: `gh run view`)

---

## ⚠️ Znalezione problemy w kodzie (do naprawy)

### ✅ Import: UTF-8 BOM (Excel CSV) — już naprawione

`import_file()` używa `encoding="utf-8-sig"` — BOM stripowany przy odczycie pliku.

---

### 🟠 Import Bitwarden: typy non-login po cichu pomijane

`import_manager.py:59` — `if item.get("type") != 1: continue`
Bitwarden eksportuje też: type 2 = Secure Note, type 3 = Card, type 4 = Identity.
Aktualnie są **cicho odrzucane** bez komunikatu dla użytkownika.

- [ ] Policzyć pominięte wpisy i pokazać po imporcie: "Zaimportowano 42, pominięto 8 (notatki/karty — nieobsługiwany typ)"
- [ ] Docelowo: importować Secure Notes jako typ "note" gdy będzie zaimplementowany

---

### 🟠 Zmiana masterhasła nie re-szyfruje PasswordHistory

`crypto.py:112` — `reencrypt()` działa per-wpis, ale przy zmianie masterhasła
trzeba przeiterować też `password_history` — inaczej stare wersje haseł są
odszyfrowane starym kluczem i stają się nieodczytywalne po zmianie.

- [ ] `db_manager.py` — `change_master_password()` musi iterować `PasswordHistory` tak samo jak `Password`
- [ ] Podczas re-szyfrowania: progress dialog (dla dużych vaultów może trwać kilka sekund)

---

### 🟠 Pole URL w modelu istnieje, ale... sprawdź czy jest w formularzu

`models.py:49` — `url = Column(String(256))` już jest w bazie.
Do sprawdzenia: czy `PasswordFormWindow` w `gui/` rzeczywiście pokazuje i zapisuje to pole,
czy tylko model je ma a UI tego nie używa.

- [ ] Zweryfikować `gui/main_window.py` — `PasswordFormWindow` czy ma pole URL
- [ ] Jeśli nie → dodać pole + "Otwórz" button w accordion detail view

---

### 🟡 Weryfikacja integralności backupów

`utils/auto_backup.py` tworzy backup, ale nie weryfikuje czy plik jest czytelny po zapisie.
Backup mógł zostać urwany (brak miejsca na dysku, crash) i jest corrupted.

- [ ] Po zapisie backupu: `sqlite3.connect(backup_path).execute("PRAGMA integrity_check")`
- [ ] Jeśli check fail → usuń corrupted backup + toast ostrzeżenia

---

### 🟡 TOTP: brak rate-limitingu na próby kodu

W LoginWindow nie ma ograniczenia liczby prób kodu TOTP.
Atakujący z fizycznym dostępem do komputera (po obejściu masterhasła) może bruteforce'ować 6-cyfrowy kod.

- [ ] Po 3 błędnych kodach TOTP → 30s cooldown (analogicznie do limitu masterhasła)

---

### 🟠 Windows Clipboard History leak

Windows 11 ma historię schowka (Win+V) — kopiowane hasła trafiają do niej i zostają
**na stałe** nawet po 30s auto-clear. Użytkownik może nie wiedzieć, że hasło siedzi w historii.

- [ ] Przy kopiowaniu hasła: wyczyść konkretny wpis z historii schowka przez WinRT API
  ```python
  # Windows.ApplicationModel.DataTransfer.Clipboard.ClearHistory()
  import winrt.windows.applicationmodel.datatransfer as dt
  dt.Clipboard.clear_history()  # czyści całą historię — rozważyć czy OK
  ```
- [ ] Alternatywa mniej inwazyjna: toast ostrzeżenia "Hasło skopiowane — pamiętaj o historii schowka (Win+V)"
- [ ] Opcja w settings: "Wyczyść historię schowka przy kopiowaniu hasła"

---

### 🔴 `datetime.utcnow()` — deprecated w Python 3.12+

`datetime.utcnow()` jest użyte **32 razy w 9 plikach** (`models.py`, `db_manager.py`, `server/main.py`,
`auto_backup.py`, `gui/main_window.py`, `gui_qt/main_window.py`, `server/models.py`, `native_host/host_session.py`, `server/auth.py`).
Python 3.12 emituje `DeprecationWarning`, Python 3.14 usunie tę metodę.

- [ ] Zamienić wszędzie: `datetime.utcnow()` → `datetime.now(timezone.utc)`
- [ ] Dodać `from datetime import timezone` tam gdzie go nie ma
- [ ] Jednorazowy globalny search & replace — nie wymaga logiki, czysto mechaniczna zmiana

---

### 🟠 Ochrona przed screen capture (Windows)

Hasła wyświetlane w accordion/detail view mogą być przechwycone screenshotem lub przez
aplikacje do nagrywania ekranu. Windows 11 ma API do wykluczenia okna z captury.

- [ ] `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` przez `ctypes.windll.user32`
- [ ] Okno staje się czarne na screenshotach i w nagraniach — zawartość widoczna tylko live
- [ ] Toggle w settings: "Chroń okno przed zrzutami ekranu" (domyślnie: włączone)
- [ ] Uwaga: działa tylko na Windows 10 2004+ i tylko dla okna głównego (nie tray menu)

---

### 🟡 Sortowanie kolumn w liście haseł

Aktualnie lista posortowana stałe (ulubione na górze, potem alfabetycznie?).
Brak możliwości sortowania po dacie dodania, ostatnim użyciu, sile hasła.

- [ ] Klikalne nagłówki kolumn: "Nazwa ↑↓", "Ostatnio użyte ↑↓", "Siła ↑↓", "Dodano ↑↓"
- [ ] Zapamiętywanie ostatniego sortowania w preferencjach

---

### 🟡 Przeciągnij i upuść między kategoriami

- [ ] Drag & drop wpisu z listy na kategorię w sidebarze → przeniesienie kategorii
- [ ] Wizualny feedback: highlight kategorii przy hover podczas dragu

---

### 🟡 Pola niestandardowe (custom fields)

KeePass-style: każdy wpis może mieć dowolne pola klucz-wartość poza standardowymi.
Przydatne dla: PIN do karty, odpowiedzi na pytania zabezpieczające, numery kont, kody recovery.

- [ ] Nowa tabela `password_fields`: `id, password_id, field_name, encrypted_value`
- [ ] W formularzu: sekcja "Własne pola" — dodaj/usuń pary nazwa-wartość
- [ ] Wartości szyfrowane tak samo jak hasło (przez `crypto.encrypt`)

---

## 🎮 Dodatkowe funkcje (pomysły)

### 🟡 Logowanie przez TOTP (login window)

Możliwość logowania się do aplikacji za pomocą kodu TOTP zamiast (lub obok) masterhasła.
Przydatne jako drugi składnik przy wejściu do vaultu.

- [ ] Opcja w settings: "Wymagaj TOTP przy logowaniu" (obok istniejącego TOTP do 2FA sync)
- [ ] LoginWindow: po poprawnym masterhaśle → dodatkowy krok z polem na 6-cyfrowy kod
- [ ] Weryfikacja przez `utils/totp.py` (już istnieje `verify_totp()`)
- [ ] Obsługa odzyskiwania: jeśli brak dostępu do authenticatora → login tylko przez klucz recovery

---

### 🟠 TOTP authenticator wbudowany w wpisy

Możliwość zapisania `otp_secret` przy wpisie hasła — AegisVault pokazuje aktywny kod TOTP
bezpośrednio w liście (odliczanie, auto-odświeżanie). Jak 1Password / Bitwarden.

- [ ] Kolumna `otp_secret TEXT` w tabeli `passwords` (zaszyfrowany razem z hasłem lub osobno)
- [ ] W accordion detail view: wyświetl aktywny kod + animowany timer (okrąg 30s)
- [ ] Przycisk "Kopiuj kod" obok
- [ ] Import: `_from_1password` już czyta kolumnę `OTPAuth` — dane są, tylko nie są zapisywane

---

### 🟠 Diceware / passphrase generator

Obok generatora haseł losowych — generator zapamiętywalne fraz (4-6 słów z listy).
`correct-horse-battery-staple` style. Wysoka entropia + łatwe do zapamiętania.

- [ ] Wordlista EFF Large Wordlist (7776 słów) — plik `utils/eff_wordlist.txt` lub hardcoded jako moduł
- [ ] Slider "Liczba słów" (3–8), separator (myślnik/spacja/kropka), opcja capitalize
- [ ] Pasek entropii: "128 bitów (bardzo silne)"
- [ ] Dodać jako drugi tab w generatorze haseł w sidebarze

---

### 🟡 Duplikowanie wpisu

Prawy klik na wpisie → "Duplikuj" — tworzy kopię z tytułem "Kopia — [tytuł]".
Przydatne gdy kilka kont na tej samej stronie z podobnymi ustawieniami.

- [ ] `db_manager.py` — `duplicate_password(entry_id)` — deep copy bez historii
- [ ] Pozycja w context menu / menu "..." przy wpisie

---

### 🟡 Szybkie kopiowanie loginu (username)

Aktualnie: `Kopiuj` w wierszu kopiuje hasło. Żeby skopiować login trzeba rozwinąć accordion.

- [ ] Drugi przycisk "👤" obok "Kopiuj" w `PasswordRow` (kompaktowy, pojawia się on-hover)
- [ ] Lub: długie kliknięcie "Kopiuj" → mini-menu: "Kopiuj hasło / Kopiuj login / Kopiuj URL"

---

### 🟠 KeePass KDBX import

`import_manager.py` obsługuje LastPass, Bitwarden, 1Password, Generic CSV — brakuje KeePass,
który jest najpopularniejszym open-source managerem.

- [ ] Biblioteka `pykeepass` (`pip install pykeepass`) — czyta `.kdbx` v3 i v4
- [ ] `_from_keepass(file_path, password)` — wymaga podania hasła do bazy KeePass w dialogu importu
- [ ] Mapowanie: `entry.title`, `entry.username`, `entry.password`, `entry.url`, `entry.notes`, `entry.group.name` → category
- [ ] Obsługa grup zagnieżdżonych → spłaszczenie do jednego poziomu kategorii (np. `Root/Praca/GitHub` → `Praca`)

---

### 🟡 macOS Touch ID / Linux PAM

Windows Hello działa (utils/windows_hello.py). Brak odpowiednika na macOS i Linux.

- [ ] macOS: `LocalAuthentication` framework przez `pyobjc-framework-LocalAuthentication`
- [ ] Linux: PAM (`python-pam`) lub `fprintd` przez D-Bus
- [ ] `utils/biometrics.py` — abstrakcja `BiometricAuth.authenticate()` → deleguje do platform-specific impl

---

## Sugerowana kolejność implementacji

```
[1]  Argon2id                    ← fundament bezpieczeństwa, reszta na nim stoi
[2]  Limit prób logowania+TOTP   ← krytyczne, ~1h zadanie
[3]  Fix: UTF-8 BOM w imporcie   ← bugfix, 5 minut
[4]  Fix: PasswordHistory re-enc ← bugfix przy zmianie masterhasła
[5]  Reset masterhasła + TOTP    ← bez tego użytkownicy tracą dane przy zapomnieniu
[6]  Klucz recovery              ← uzupełnienie resetu
[7]  Pole URL w formularzu        ← model już istnieje, tylko UI do dokończenia
[8]  Secure notes                ← często proszony feature
[9]  Eksport CSV/JSON/XML        ← użytkownicy oczekują
[10] TOTP w wpisach              ← killer feature, import z 1Password już czyta OTPAuth
[11] Bulk operacje               ← komfort przy dużej liczbie wpisów
[12] Diceware generator          ← uzupełnienie generatora haseł
[13] Audit log                   ← bezpieczeństwo enterprise
[14] Database integrity check    ← stabilność
```
