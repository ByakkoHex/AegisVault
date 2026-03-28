# Instalacja AegisVault

## Wymagania systemowe

| Komponent | Wymaganie |
|-----------|-----------|
| Python | 3.10 lub nowszy |
| System | Windows 10/11, macOS 12+, Ubuntu 20.04+ / dowolna dystrybucja Linux |
| Miejsce na dysku | ~150 MB (z zależnościami Python) |
| RAM | min. 256 MB |

---

## Instalacja aplikacji desktop

### Windows

```batch
:: 1. Sprawdź wersję Pythona
py --version

:: 2. Sklonuj lub pobierz projekt do wybranego folderu

:: 3. Zainstaluj zależności
py -m pip install -r requirements.txt

:: 4. Uruchom aplikację
py main.py
```

### macOS

```bash
# 1. Upewnij się że Python 3.10+ jest zainstalowany
# Zalecane: przez Homebrew
brew install python@3.11

# 2. Sklonuj lub pobierz projekt

# 3. Zainstaluj zależności
pip3 install -r requirements.txt

# 4. Uruchom aplikację
python3 main.py
```

> **macOS + tkinter**: jeśli pojawi się błąd tkinter, zainstaluj:
> `brew install python-tk@3.11`

### Linux (Ubuntu / Debian)

```bash
# 1. Zainstaluj Python i tkinter
sudo apt update
sudo apt install python3 python3-pip python3-tk

# 2. Zainstaluj zależności
pip3 install -r requirements.txt

# 3. Uruchom aplikację
python3 main.py
```

### Linux (Fedora / RHEL)

```bash
sudo dnf install python3 python3-pip python3-tkinter
pip3 install -r requirements.txt
python3 main.py
```

### Linux (Arch)

```bash
sudo pacman -S python python-pip tk
pip install -r requirements.txt
python main.py
```

---

## Pierwsze uruchomienie

1. Aplikacja tworzy bazę danych automatycznie przy pierwszym starcie:
   - Windows: `%APPDATA%\AegisVault\aegisvault.db`
   - macOS: `~/Library/Application Support/AegisVault/aegisvault.db`
   - Linux: `~/.local/share/aegisvault/aegisvault.db`

2. Kliknij **Zarejestruj** i utwórz konto z hasłem głównym.

3. (Opcjonalnie) Włącz 2FA podczas rejestracji — zeskanuj QR kod aplikacją Authenticator.

---

## Instalacja serwera synchronizacji (opcjonalna)

Serwer jest opcjonalny — AegisVault działa w pełni lokalnie bez niego.

### Uruchomienie

```batch
:: Windows
start_server.bat
```

```bash
# macOS / Linux
bash start_server.sh
```

Skrypty automatycznie instalują brakujące zależności (`fastapi`, `uvicorn`, itd.).

### Ręczna instalacja zależności serwera

```bash
pip install -r requirements-server.txt
python3 -m uvicorn server.main:app --reload --port 8000
```

### Dostęp

- API: `http://localhost:8000`
- Dokumentacja Swagger: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Konfiguracja przed wdrożeniem produkcyjnym

W pliku `server/auth.py` zmień klucz JWT:

```python
# Zmień na losowy string min. 32 znaki:
SECRET_KEY = "twoj-losowy-klucz-produkcyjny-min-32-znaki"
```

---

## Instalacja wtyczki przeglądarkowej

### Krok 1 — Pobierz browser-polyfill

Pobierz `browser-polyfill.min.js` ze strony [mozilla/webextension-polyfill](https://github.com/mozilla/webextension-polyfill/releases/latest) i zapisz jako `extension/lib/browser-polyfill.js`.

Alternatywnie przez npm:

```bash
npm install webextension-polyfill
cp node_modules/webextension-polyfill/dist/browser-polyfill.min.js extension/lib/browser-polyfill.js
```

### Krok 2 — Załaduj rozszerzenie w Chrome / Edge

1. Otwórz `chrome://extensions` (lub `edge://extensions`)
2. Włącz **Tryb deweloperski** (prawy górny róg)
3. Kliknij **Załaduj rozpakowane**
4. Wskaż folder `extension/` z projektu
5. Zapisz wyświetlone **ID rozszerzenia** (np. `abcdefghijklmnopqrstuvwxyz123456`)

### Krok 3 — Zainstaluj Native Messaging Host

```batch
:: Windows
py native_host/install/install.py --extension-id TWOJE_EXTENSION_ID
```

```bash
# macOS / Linux
python3 native_host/install/install.py --extension-id TWOJE_EXTENSION_ID
```

Instalator zarejestruje hosta dla Chrome, Edge i Firefox jednocześnie.

### Krok 4 — Załaduj w Firefox (opcjonalnie)

1. Otwórz `about:debugging`
2. **Ten Firefox** → **Załaduj tymczasowy dodatek**
3. Wskaż `extension/manifest.json`

> Firefox nie wymaga podawania Extension ID — używa `gecko.id` z manifestu (`aegisvault@aegisvault.pl`).

### Krok 5 — Weryfikacja

1. Kliknij ikonę AegisVault w przeglądarce
2. Zaloguj się hasłem głównym (tym samym co w aplikacji desktop)
3. Przejdź na stronę z formularzem — kliknij pole hasła
4. Powinien pojawić się chip "Uzupełnij przez AegisVault"

### Odinstalowanie hosta

```bash
python3 native_host/install/uninstall.py
```

---

## Rozwiązywanie problemów

### `ModuleNotFoundError: No module named 'customtkinter'`

```bash
pip install customtkinter
```

### `ModuleNotFoundError: No module named '_tkinter'`

```bash
# Ubuntu/Debian:
sudo apt install python3-tk

# Fedora:
sudo dnf install python3-tkinter

# macOS (Homebrew):
brew install python-tk@3.11
```

### Wtyczka: "Host not found" / "Native host has exited"

1. Sprawdź czy instalator został uruchomiony: `py native_host/install/install.py`
2. Sprawdź czy Python jest w PATH: `py --version` / `python3 --version`
3. Sprawdź logi w `chrome://extensions` → Szczegóły rozszerzenia → Wyświetl widok: service worker → Console

### Wtyczka: brak chipa autofill

1. Upewnij się że jesteś zalogowany w popupie rozszerzenia
2. Sprawdź czy strona ma pola `<input type="password">`
3. Sprawdź czy dla tej domeny istnieje wpis z URL w aplikacji desktop

### Serwer: port 8000 zajęty

```bash
python3 -m uvicorn server.main:app --port 8001
```

Zaktualizuj URL serwera w oknie synchronizacji aplikacji desktop.
