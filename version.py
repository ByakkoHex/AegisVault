"""
version.py - Wersja aplikacji AegisVault
=========================================
Zmień APP_VERSION przy każdym wydaniu, aby klienci mogli wykryć aktualizację.
Format: MAJOR.MINOR.PATCH
"""

APP_VERSION = "1.2.6"

APP_CHANGELOG = """\
• Płynna zmiana koloru akcentu — aktualizacja in-place, zero flashu
• Płynne przełączanie trybu ciemny/jasny — fade alpha, zero rebuildu
• Kolory wierszy haseł aktualizują się przy zmianie motywu
• Logo w oknie logowania zmienia kolor zgodnie z akcentem
• Brak animacji przy pierwszym załadowaniu listy haseł
• Domyślny kolor akcentu zmieniony na kobaltowy niebieski (#0F52BA)
• Automatyczne sprawdzanie aktualizacji co 4 godziny w tle
• Toast z powiadomieniem o nowej wersji bez restartu aplikacji
• Naprawiono bgerror przy zamknięciu (anulowanie after() callbacków)
• Naprawiono kolory generatora haseł przy zmianie akcentu
"""
