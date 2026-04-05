"""
version.py - Wersja aplikacji AegisVault
=========================================
Zmień APP_VERSION przy każdym wydaniu, aby klienci mogli wykryć aktualizację.
Format: MAJOR.MINOR.PATCH
"""

APP_VERSION = "1.3.0"

# Historia wersji — lista (wersja, tytuł, [zmiany])
# Najnowsza wersja na górze.
VERSION_HISTORY = [
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
