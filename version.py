"""
version.py - Wersja aplikacji AegisVault
=========================================
Zmień APP_VERSION przy każdym wydaniu, aby klienci mogli wykryć aktualizację.
Format: MAJOR.MINOR.PATCH
"""

APP_VERSION = "1.4.0"

# Historia wersji — lista (wersja, tytuł, [zmiany])
# Najnowsza wersja na górze.
VERSION_HISTORY = [
    (
        "1.4.0",
        "Bezpieczeństwo — Argon2id, AES-256, Zero-knowledge",
        [
            "Szyfrowanie: migracja KDF z PBKDF2+bcrypt na Argon2id (time=3, mem=64 MB, par=4) — standard OWASP 2023",
            "Szyfrowanie: wszystkie hasła chronione AES-256 (Fernet) z kluczem derywowanym per-użytkownik",
            "Architektura zero-knowledge: hasło masterowe nigdy nie opuszcza urządzenia w postaci jawnej",
            "Auto-migracja: konta z PBKDF2 automatycznie migrowane do Argon2id przy pierwszym logowaniu",
            "Recovery key: klucz odzyskiwania derywowany przez osobną instancję Argon2id (time=2, mem=32 MB)",
            "PIN (szybkie odblokowanie): hash PIN-u przechowywany jako Argon2id, nigdy plaintext",
            "Naprawiono: przycisk aktualizacji w topbarze nie otwierał dropdownu (Qt Popup → Tool window)",
            "Naprawiono: CI/CD — usunięto brakujące joby macOS DMG i rozszerzenie przeglądarki",
            "Naprawiono: odczyt wersji w instalatorze Windows (z version.py zamiast manifest.json)",
            "Naprawiono: installer Windows — usunięto referencje do nieistniejącego native_host",
        ],
    ),
    (
        "1.3.4",
        "Poprawki UI, stabilność, bugfixy",
        [
            "Naprawiono: animacja hexów w panelu ustawień nie uruchamiała się przy otwarciu",
            "Naprawiono: przycisk 'Usuń' przy zaufanych urządzeniach był przycinany",
            "Naprawiono: sprawdzanie wycieku hasła (HIBP) zatrzymywało się na 'Sprawdzanie...'",
            "Naprawiono: aktualizacja aplikacji — przycisk nic nie robił po kliknięciu",
            "Naprawiono: błąd TypeError (naive vs aware datetime) przy sprawdzaniu auto-backup",
            "Naprawiono: błąd TypeError (naive vs aware datetime) przy odznakach wygaśnięcia haseł",
            "Naprawiono: QPixmap null pixmap w splash screenie przy ścieżce względnej ikony",
            "Naprawiono: wygenerowane hasła nie były czyszczone ze schowka po 30s",
            "Splash screen: dłuższe wyświetlanie + okno aplikacji budowane w tle (brak lagów po zamknięciu)",
            "Splash screen: więcej i częstsze świecenie hexagonów",
        ],
    ),
    (
        "1.3.3",
        "Wielojęzyczność EN/PL + splash screen",
        [
            "Pełne wsparcie dla języka angielskiego — wszystkie napisy w UI tłumaczą się po zmianie języka",
            "Splash screen przy starcie aplikacji z paskiem postępu",
            "Naprawiono: nazwy kategorii, generatora, formularzy i ekranu logowania nie zmieniały języka",
            "Naprawiono: przyciski toggle (Włączone/Wyłączone) nie reagowały na zmianę języka",
            "Naprawiono: nazwy kolorów akcentu i dni retencji logów nie były tłumaczone",
            "macOS: dodano skrypt 'Zezwól na uruchomienie' w DMG usuwający blokadę Gatekeepera",
        ],
    ),
    (
        "1.3.0",
        "Nowy interfejs — migracja na PyQt6",
        [
            "Całkowita migracja GUI z customtkinter na PyQt6 — płynniejsze animacje i lepszy rendering",
            "Panel ustawień wysuwa się z prawej strony bez otwierania nowego okna",
            "Przełącznik motywu ciemny/jasny jako ikona słońce/księżyc — zmiana bez przeładowania",
            "15 kolorów akcentu w siatce 5×3 z podglądem nazwy na hover",
            "Ikona aplikacji w topbarze koloryzowana aktywnym akcentem",
            "Przeprojektowane przyciski wierszy haseł — jednakowe rozmiary, gwiazdka zawsze widoczna",
            "Tło hexagonalne prześwituje przez okna dialogowe",
            "Naprawiono: zmiana motywu nie aktualizowała tła hexagonalnego",
            "Naprawiono: tekst w przyciskach toggle (Autostart, WH) był obcięty",
        ],
    ),
    (
        "1.2.6",
        "Płynne animacje i automatyczne aktualizacje",
        [
            "Płynna zmiana koloru akcentu — aktualizacja in-place, zero flashu",
            "Płynne przełączanie motywu ciemny/jasny bez przebudowy okna",
            "Kolory wierszy haseł aktualizują się natychmiast przy zmianie motywu",
            "Logo w oknie logowania zmienia kolor zgodnie z akcentem",
            "Automatyczne sprawdzanie aktualizacji co 4 godziny w tle",
            "Toast z powiadomieniem o nowej wersji bez restartu aplikacji",
            "Domyślny kolor akcentu zmieniony na kobaltowy niebieski",
            "Naprawiono błędy animacji przy zamknięciu aplikacji",
        ],
    ),
    (
        "1.2.5",
        "Wyszukiwanie rozmyte i optymalizacje",
        [
            "Wyszukiwanie rozmyte (fuzzy) — działa nawet z literówkami",
            "Optymalizacja SQLite: WAL mode, cache 32 MB, busy timeout",
            "Naprawiono przycinanie hexagonów w tle listy haseł",
            "Hexagony i gradienty aktualizują się po zmianie motywu",
            "Naprawiono czarny pasek pod separatorem w trybie jasnym",
            "Dialog 'Co nowego' pojawia się tylko po prawdziwej aktualizacji",
        ],
    ),
    (
        "1.2.3",
        "System aktualizacji z GitHub Releases",
        [
            "Aktualizator pobiera nową wersję bezpośrednio z GitHub Releases",
            "Popup 'Co nowego' po pierwszym uruchomieniu po aktualizacji",
            "Dropdown panel z informacją o aktualizacji w topbarze",
            "Naprawiono budowanie na Linux i macOS w CI/CD",
        ],
    ),
]

# Changelog bieżącej wersji (skrócony — do serwera aktualizacji)
APP_CHANGELOG = "\n".join(f"• {c}" for c in VERSION_HISTORY[0][2])
