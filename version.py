"""
version.py - Wersja aplikacji AegisVault
=========================================
Zmień APP_VERSION przy każdym wydaniu, aby klienci mogli wykryć aktualizację.
Format: MAJOR.MINOR.PATCH
"""

APP_VERSION = "1.2.5"

APP_CHANGELOG = """\
• Naprawiono przycinanie hexagonów w tle listy haseł
• Hexagony i gradienty aktualizują się teraz po zmianie motywu
• Naprawiono czarny pasek pod separatorem w trybie jasnym
• Wyszukiwanie rozmyte (fuzzy) dzięki rapidfuzz — działa nawet z literówkami
• Optymalizacja SQLite: WAL, cache 32MB, busy timeout
• Dialog 'Co nowego' pojawia się tylko po prawdziwej aktualizacji
• Dropdown z aktualizacją wyświetla się teraz pod ikonką w topbarze
"""
