# Generowanie instalatorów — AegisVault

## Przegląd

System budowania generuje natywne instalatory dla każdej platformy z jednego repozytorium:

| System | Format | Narzędzie |
|--------|--------|-----------|
| Windows | `.exe` (installer) | Inno Setup 6 |
| macOS | `.dmg` | hdiutil / create-dmg |
| Linux | `.deb` | dpkg-deb + fakeroot |
| Chrome/Edge | `.zip` | zip/Compress-Archive |
| Firefox | `.zip` | zip/Compress-Archive |

---

## Wymagania narzędziowe

### Wspólne (wszystkie platformy)

```bash
pip install pyinstaller      # budowanie binarki
pip install -r requirements.txt
```

### Windows

- **Inno Setup 6** — [jrsoftware.org/isinfo.php](https://jrsoftware.org/isinfo.php)
  - Lub przez Chocolatey: `choco install innosetup`
- Python 3.10+ (w PATH — wymagany dla native host)

### macOS

- `hdiutil` — wbudowany w macOS (zawsze dostępny)
- **create-dmg** (opcjonalny, ładniejszy DMG):
  ```bash
  npm install -g create-dmg
  ```

### Linux (Debian/Ubuntu)

```bash
sudo apt-get install fakeroot dpkg-dev
```

### Rozszerzenie przeglądarkowe

- `zip` (Unix) lub PowerShell (Windows) — standardowo dostępne
- **browser-polyfill.js** musi istnieć w `extension/lib/`:
  ```bash
  curl -L -o extension/lib/browser-polyfill.js \
    https://unpkg.com/webextension-polyfill@latest/dist/browser-polyfill.min.js
  ```

---

## Szybki start — wszystko naraz

### Unix (macOS / Linux)

```bash
# 1. Zbuduj wszystko
bash installer/build_all.sh

# 2. Lub z opcjami
bash installer/build_all.sh --skip-pyinstaller   # pomiń PyInstaller (gdy dist/ już istnieje)
bash installer/build_all.sh --extension-only      # tylko rozszerzenie przeglądarkowe
```

### Windows (PowerShell)

```powershell
# 1. Zbuduj wszystko
.\installer\build_all.ps1

# 2. Lub z opcjami
.\installer\build_all.ps1 -SkipPyInstaller
.\installer\build_all.ps1 -ExtensionOnly
.\installer\build_all.ps1 -AppVersion "1.2.0"
```

**Wynik:** pliki gotowe w `dist/`

---

## Krok po kroku

### Krok 1 — Zbuduj binarkę (PyInstaller)

Musi być wykonany na docelowej platformie (Windows → .exe, macOS → .app, Linux → binary).

```bash
# Wszystkie platformy
pyinstaller aegisvault.spec --noconfirm
```

Wyniki:
- Windows: `dist/AegisVault/AegisVault.exe` + folder z DLL
- macOS: `dist/AegisVault.app`
- Linux: `dist/aegisvault` (single file ELF)

### Krok 2 — Zbuduj instalator platformy

#### Windows — Inno Setup (.exe)

```batch
rem Znajdź iscc.exe i uruchom:
"C:\Program Files (x86)\Inno Setup 6\iscc.exe" /DAppVersion=1.0.0 installer\windows\aegisvault.iss

rem Wynik: dist\AegisVault-Setup-1.0.0.exe
```

Instalator:
- Kopiuje `dist\AegisVault\` do `%LocalAppData%\Programs\AegisVault\`
- Tworzy skrót w menu Start i (opcjonalnie) na pulpicie
- Rejestruje native messaging host przez `post_install.ps1`
- Waliduje obecność Python w PATH przed instalacją
- Tworzy wpis deinstalacji w "Programy i funkcje"

#### macOS — DMG

```bash
bash installer/macos/build_dmg.sh

# Wynik: dist/AegisVault-1.0.0.dmg
```

Zawartość DMG:
- `AegisVault.app` — aplikacja
- Symlink do `/Applications` — drag-and-drop install
- `README - Integracja z przeglądarką.txt` — instrukcja native host

#### Linux — pakiet .deb

```bash
bash installer/linux/build_deb.sh

# Wynik: dist/aegisvault_1.0.0_amd64.deb
```

Instalacja przez użytkownika:
```bash
sudo dpkg -i dist/aegisvault_1.0.0_amd64.deb
sudo apt-get install -f   # napraw zależności jeśli potrzeba
```

Pakiet instaluje:
- `/usr/bin/aegisvault` — binary
- `/usr/share/aegisvault/` — native host scripts, moduły Python
- `/usr/share/applications/aegisvault.desktop` — skrót w menu systemu
- Uruchamia `postinst` który wyświetla instrukcję instalacji native host

### Krok 3 — Pakuj rozszerzenie przeglądarkowe

```bash
# Unix
bash installer/extension/build_extension.sh

# Windows
.\installer\extension\build_extension.ps1
```

Wyniki:
- `dist/extension-chrome-1.0.0.zip` — do Chrome Web Store / ręczne ładowanie
- `dist/extension-firefox-1.0.0.zip` — do Firefox AMO / ręczne ładowanie

---

## Zarządzanie wersją

Wersja odczytywana jest automatycznie z `extension/manifest.json`:

```json
{
  "version": "1.0.0"
}
```

To jest **jedyne miejsce** gdzie zmienia się wersję — wszystkie skrypty odczytują ją stamtąd.

### Procedura wydania nowej wersji

```bash
# 1. Zmień wersję w extension/manifest.json
#    "version": "1.1.0"

# 2. Zbuduj wszystko
bash installer/build_all.sh

# 3. Przetestuj instalatory lokalnie

# 4. Commit + tag → GitHub Actions zbuduje automatycznie
git add extension/manifest.json
git commit -m "Release v1.1.0"
git tag v1.1.0
git push origin main --tags
```

---

## GitHub Actions — automatyczny build

Po wypchnięciu tagu `v*` GitHub Actions automatycznie:

1. **Buduje binarkę** na Windows, macOS i Linux (równolegle)
2. **Tworzy instalator** dla każdej platformy
3. **Pakuje rozszerzenie** przeglądarkowe
4. **Tworzy GitHub Release** z wszystkimi plikami do pobrania

```
Tag v1.0.0
    │
    ├── job: build (windows)  → dist/AegisVault/
    ├── job: build (macos)    → dist/AegisVault.app
    ├── job: build (linux)    → dist/aegisvault
    │        ↓
    ├── job: package-windows  → AegisVault-Setup-1.0.0.exe
    ├── job: package-macos    → AegisVault-1.0.0.dmg
    ├── job: package-linux    → aegisvault_1.0.0_amd64.deb
    ├── job: package-extension→ extension-chrome-1.0.0.zip
    │                           extension-firefox-1.0.0.zip
    └── job: release          → GitHub Release z wszystkimi plikami
```

Czas działania workflow: ~15-20 minut.

---

## Podpisywanie kodu (Code Signing)

Bez podpisania kodu:
- Windows: SmartScreen ostrzeże użytkownika ("nieznany wydawca")
- macOS: Gatekeeper zablokuje uruchomienie bez ominięcia

### Windows — Code Signing

Wymaga kupionego certyfikatu od CA (DigiCert, Sectigo, ~$200/rok).

```batch
rem Podpisz binarki przed Inno Setup
signtool sign /td SHA256 /fd SHA256 /a dist\AegisVault\AegisVault.exe
rem Podpisz instalator
signtool sign /td SHA256 /fd SHA256 /a dist\AegisVault-Setup-1.0.0.exe
```

Dodaj do `aegisvault.iss`:
```ini
[Setup]
SignTool=mysign
```

### macOS — notaryzacja Apple

Wymaga Apple Developer Account ($99/rok).

```bash
# Podpisz .app
codesign --deep --force --verify --verbose \
  --sign "Developer ID Application: TWOJE_IMIE (TEAM_ID)" \
  dist/AegisVault.app

# Wyślij do notaryzacji
xcrun notarytool submit dist/AegisVault-1.0.0.dmg \
  --apple-id twoj@email.com \
  --team-id TEAM_ID \
  --password APP_SPECIFIC_PASSWORD \
  --wait

# Staple notarization
xcrun stapler staple dist/AegisVault-1.0.0.dmg
```

### Linux — GPG podpisanie pakietu

```bash
# Podpisz plik .deb
gpg --armor --detach-sign dist/aegisvault_1.0.0_amd64.deb
# Wynik: aegisvault_1.0.0_amd64.deb.asc
```

---

## Struktura katalogu installer/

```
installer/
├── build_all.sh              # Główny skrypt build (Unix/macOS/Linux)
├── build_all.ps1             # Główny skrypt build (Windows)
│
├── windows/
│   ├── aegisvault.iss        # Inno Setup script
│   └── post_install.ps1      # Rejestracja native host po instalacji
│
├── macos/
│   └── build_dmg.sh          # Tworzenie .dmg
│
├── linux/
│   ├── build_deb.sh          # Tworzenie pakietu .deb
│   └── deb_template/
│       ├── DEBIAN/
│       │   ├── control       # Metadane pakietu
│       │   ├── postinst      # Skrypt po instalacji
│       │   └── prerm         # Skrypt przed deinstalacją
│       └── usr/
│           ├── bin/          # (puste — binary kopiowane przez build_deb.sh)
│           └── share/
│               ├── applications/aegisvault.desktop
│               └── doc/aegisvault/copyright
│
└── extension/
    ├── build_extension.sh    # Pakowanie ZIP (Unix)
    └── build_extension.ps1   # Pakowanie ZIP (Windows)
```

---

## Rozwiązywanie problemów

### PyInstaller: `ModuleNotFoundError` w spakowanej aplikacji

Dodaj brakujący moduł do `hiddenimports` w `aegisvault.spec`:

```python
hiddenimports=["nazwa.brakujacego.modulu"]
```

### Inno Setup: nie znaleziono pliku

Sprawdź czy `dist\AegisVault\` istnieje i zawiera `AegisVault.exe` przed uruchomieniem `iscc.exe`.

### macOS: DMG — "hdiutil: create failed"

```bash
# Sprawdź dostępne miejsce
df -h /tmp

# Zmniejsz rozmiar w build_dmg.sh (parametr -size)
```

### Linux .deb: błędy uprawnień

```bash
# Upewnij się że fakeroot jest zainstalowany
which fakeroot
# Jeśli nie: sudo apt install fakeroot
```

### Rozszerzenie: błąd "browser-polyfill.js not found"

```bash
curl -L -o extension/lib/browser-polyfill.js \
  https://unpkg.com/webextension-polyfill@latest/dist/browser-polyfill.min.js
```
