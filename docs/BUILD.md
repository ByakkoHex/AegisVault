# Budowanie i pakowanie — AegisVault

## Przegląd

AegisVault może być pakowany do samodzielnych binariów (bez wymaganego Pythona) za pomocą PyInstaller. GitHub Actions automatyzuje buildy dla wszystkich platform jednocześnie.

---

## Lokalne budowanie

### Wymagania

```bash
pip install pyinstaller
pip install -r requirements.txt
```

### Budowanie (bieżąca platforma)

```bash
pyinstaller aegisvault.spec --noconfirm
```

Wynik trafia do katalogu `dist/`.

### Wyniki na poszczególnych platformach

| System | Wynik | Uruchomienie |
|--------|-------|--------------|
| Windows | `dist/AegisVault/AegisVault.exe` | Dwuklik |
| macOS | `dist/AegisVault.app` | Dwuklik lub `open dist/AegisVault.app` |
| Linux | `dist/aegisvault` | `./dist/aegisvault` |

---

## Konfiguracja PyInstaller (`aegisvault.spec`)

### Hidden imports

PyInstaller nie zawsze wykrywa wszystkich importów dynamicznych. Zadeklarowane jawnie:

```python
hiddenimports=[
    "customtkinter",
    "PIL._tkinter_finder",     # wymagane przez Pillow + tkinter
    "cryptography",
    "bcrypt",
    "pyotp",
    "qrcode",
    "pyperclip",
    "httpx",
    "sqlalchemy",
    "sqlalchemy.dialects.sqlite",
]
```

### Dołączane zasoby (`datas`)

```python
added_files = [
    ("assets", "assets"),   # folder assets/ (fonty Roboto)
]
```

Przy dostępie do zasobów w spakowanej aplikacji użyj `utils/paths.py::get_assets_dir()` — obsługuje zarówno tryb deweloperski jak i `sys._MEIPASS` (PyInstaller).

### Konfiguracja per-platforma

**Windows** — `EXE` + `COLLECT` (folder z zależnościami):
- `console=False` — brak okna terminala
- `icon="assets/icon.ico"` — ikona aplikacji (dodaj plik `.ico`)

**macOS** — `EXE` + `COLLECT` + `BUNDLE` (`.app`):
- `bundle_identifier="pl.aegisvault.app"`
- `icon="assets/icon.icns"` — ikona macOS (dodaj plik `.icns`)
- `NSHighResolutionCapable: True` — obsługa Retina

**Linux** — pojedynczy plik EXE (dla prostoty dystrybucji):
- `console=False`

---

## GitHub Actions CI/CD (`.github/workflows/build.yml`)

### Kiedy uruchamiany

```yaml
on:
  push:
    tags:
      - "v*"          # Każdy tag v1.0.0, v2.1.3 itd.
  workflow_dispatch:  # Ręczne uruchomienie z GitHub UI
```

### Macierz platform

| Runner | Wynik |
|--------|-------|
| `windows-latest` | `AegisVault-windows.zip` |
| `macos-latest` | `AegisVault-macos.zip` |
| `ubuntu-latest` | `AegisVault-linux.tar.gz` |

### Dodatkowe zależności systemowe (Linux)

```yaml
sudo apt-get install -y \
  python3-tk \         # tkinter
  libxcb-xinerama0 \  # wymagane przez customtkinter
  xvfb \              # wirtualny display (headless)
  libglib2.0-0 \
  libfontconfig1
```

### Tworzenie Release

Po zbudowaniu wszystkich platform, job `release` (tylko dla tagów) tworzy GitHub Release z plikami do pobrania.

### Procedura wydania nowej wersji

```bash
# 1. Zaktualizuj wersję w extension/manifest.json
# 2. Commit zmian
git add .
git commit -m "Release v1.0.0"

# 3. Utwórz tag
git tag v1.0.0

# 4. Push z tagiem
git push origin main
git push origin v1.0.0

# → GitHub Actions automatycznie zbuduje wszystkie platformy
# → Po ~10 minutach Release będzie dostępny z plikami .zip i .tar.gz
```

---

## Ikony aplikacji

Przed budowaniem produkcyjnym przygotuj ikony:

| Plik | Rozmiar | Platforma |
|------|---------|-----------|
| `assets/icon.ico` | Multi-size (16/32/48/256 px) | Windows |
| `assets/icon.icns` | Multi-size | macOS |
| `extension/icons/icon16.png` | 16×16 px | Przeglądarka |
| `extension/icons/icon48.png` | 48×48 px | Przeglądarka |
| `extension/icons/icon128.png` | 128×128 px | Przeglądarka |

### Generowanie ikon z PNG (macOS)

```bash
# Ze źródłowego PNG 1024x1024:
mkdir icon.iconset
sips -z 16 16   icon.png --out icon.iconset/icon_16x16.png
sips -z 32 32   icon.png --out icon.iconset/icon_16x16@2x.png
sips -z 32 32   icon.png --out icon.iconset/icon_32x32.png
sips -z 64 64   icon.png --out icon.iconset/icon_32x32@2x.png
sips -z 128 128 icon.png --out icon.iconset/icon_128x128.png
sips -z 256 256 icon.png --out icon.iconset/icon_128x128@2x.png
sips -z 256 256 icon.png --out icon.iconset/icon_256x256.png
sips -z 512 512 icon.png --out icon.iconset/icon_256x256@2x.png
sips -z 512 512 icon.png --out icon.iconset/icon_512x512.png
iconutil -c icns icon.iconset -o assets/icon.icns
```

### Generowanie .ico (Windows, np. ImageMagick)

```bash
magick convert icon.png -define icon:auto-resize=256,128,64,48,32,16 assets/icon.ico
```

---

## Budowanie samodzielnego pakietu rozszerzenia

Rozszerzenie przeglądarkowe dystrybuowane jest jako folder (lub plik `.zip` / `.crx`).

```bash
# Utwórz plik ZIP gotowy do przesłania do Chrome Web Store
cd extension
zip -r ../AegisVault-extension.zip . --exclude "*.md"
```

Przed przesłaniem do Chrome Web Store należy:
1. Uzyskać konto deweloperskie ($5 opłata jednorazowa)
2. Wypełnić opis, screenshoty
3. Przejść review (kilka dni)

Dla Firefox Add-ons (AMO) podobna procedura przez [addons.mozilla.org](https://addons.mozilla.org).

---

## Znane problemy z budowaniem

### `cryptography` na macOS ARM (Apple Silicon)

```bash
# Jeśli PyInstaller nie może znaleźć bibliotek:
pip install cryptography --no-binary cryptography
```

### `customtkinter` fonts path w spakowanej aplikacji

Fonty muszą być dostępne przez `sys._MEIPASS`. Funkcja `get_assets_dir()` w `utils/paths.py` obsługuje to automatycznie:

```python
def get_assets_dir() -> str:
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS   # PyInstaller temp dir
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets")
```

### Antywirus Windows blokuje `.exe`

PyInstaller binaria są czasem fałszywie wykrywane jako malware. Rozwiązania:
- Podpisanie kodu certyfikatem (Code Signing Certificate)
- Zgłoszenie false positive do dostawcy AV
- Dystrybucja przez Microsoft Store
