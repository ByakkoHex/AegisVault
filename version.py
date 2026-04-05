"""
version.py - Wersja aplikacji AegisVault
=========================================
Zmień APP_VERSION przy każdym wydaniu, aby klienci mogli wykryć aktualizację.
Format: MAJOR.MINOR.PATCH
"""

APP_VERSION = "1.3.0"

APP_CHANGELOG = """\
• Migracja interfejsu na PyQt6 — płynniejsze animacje, lepszy rendering
• Nowy panel ustawień — wysuwa się z prawej bez osobnego okna
• Zmiana motywu ciemny/jasny — przełącznik słońce/księżyc, zero flashu
• Naprawiono błąd: zmiana motywu nie aktualizowała tła hexagonalnego
• 15 kolorów akcentu (nowe: Granatowy, Magenta, Miętowy) w siatce 5×3
• Kafelki akcentu 52×52 px — hover zmienia kolor i nazwę na żywo
• Ikona aplikacji w topbarze koloryzowana aktywnym akcentem
• Przeprojektowane przyciski wierszy haseł — równe rozmiary (100×36 px)
• Gwiazdka ulubionych zawsze widoczna — ramka + hover złoty kolor
• Tło hexagonalne widoczne w pustej przestrzeni panelu ustawień
• Naprawiono obcinanie tekstu w przyciskach toggle (Autostart, WH, itp.)
"""
