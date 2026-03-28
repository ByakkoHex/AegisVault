"""
version.py - Wersja aplikacji AegisVault
=========================================
Zmień APP_VERSION przy każdym wydaniu, aby klienci mogli wykryć aktualizację.
Format: MAJOR.MINOR.PATCH
"""

APP_VERSION = "1.2.3"

APP_CHANGELOG = """\
• Aktualizator pobiera nową wersję bezpośrednio z GitHub Releases
• Popup 'Hej! Jest nowa wersja' po zalogowaniu z changelogiem
• Dropdown panel z informacją o aktualizacji w topbarze
• Naprawiono budowanie na Linux i macOS w CI/CD
• Instalator pokazuje teraz informację o aktualizacji z poprzedniej wersji
"""
