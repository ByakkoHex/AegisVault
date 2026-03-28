# Instalacja AegisVault — Wtyczka do przeglądarki

## Wymagania

- Python 3.10+ (ten sam co dla aplikacji desktop)
- Zależności: `pip install -r requirements.txt` (w katalogu głównym projektu)
- Aplikacja AegisVault musi być wcześniej używana (musi istnieć baza danych)

---

## Krok 1 — Pobierz browser-polyfill

W katalogu `extension/lib/` umieść plik `browser-polyfill.js`:
Szczegóły w `extension/lib/DOWNLOAD_POLYFILL.md`.

---

## Krok 2 — Załaduj rozszerzenie w Chrome/Edge

1. Otwórz `chrome://extensions` (lub `edge://extensions`)
2. Włącz **Tryb deweloperski** (prawy górny róg)
3. Kliknij **Załaduj rozpakowane**
4. Wskaż folder `extension/` z projektu
5. Skopiuj **ID rozszerzenia** (ciąg ~32 znaków, np. `abcdefghijklmnopqrstuvwxyz123456`)

---

## Krok 3 — Zainstaluj Native Messaging Host

```bash
# Windows:
py native_host/install/install.py --extension-id TWOJE_EXTENSION_ID

# macOS / Linux:
python3 native_host/install/install.py --extension-id TWOJE_EXTENSION_ID
```

Instalator zarejestruje hosta we wszystkich wykrytych przeglądarkach.

---

## Krok 4 — Załaduj rozszerzenie w Firefox

1. Otwórz `about:debugging`
2. Kliknij **Ten Firefox** → **Załaduj tymczasowy dodatek**
3. Wskaż plik `extension/manifest.json`

> Dla Firefox **nie jest wymagane** podawanie Extension ID — używa Gecko ID z manifestu.

---

## Krok 5 — Test

1. Kliknij ikonę AegisVault w przeglądarce
2. Podaj login i hasło główne (te same co w aplikacji desktop)
3. Przejdź na stronę z formularzem logowania — kliknij pole hasła
4. Powinien pojawić się chip "Uzupełnij przez AegisVault"

---

## Odinstalowanie

```bash
py native_host/install/uninstall.py
```
