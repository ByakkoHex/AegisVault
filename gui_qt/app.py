"""
app.py — QApplication singleton dla AegisVault (PyQt6)
======================================================
Inicjalizuje QApplication, ustawia globalny styl QSS i udostępnia
helpers do zmiany motywu w locie.

Użycie:
    from gui_qt.app import create_app, apply_theme

    app = create_app()
    # ... tworzenie okien ...
    app.exec()
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import Qt
import os

from gui_qt.style import current_qss, build_qss

_app: QApplication | None = None


def create_app() -> QApplication:
    """Tworzy i konfiguruje QApplication. Wywołaj raz na start programu."""
    global _app
    if _app is not None:
        return _app

    # Wyłącz scaling DPI — Qt6 domyślnie włączone, ale upewnij się
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    _app = QApplication(sys.argv)
    _app.setApplicationName("AegisVault")
    _app.setApplicationVersion("1.3.0")
    _app.setOrganizationName("AegisVault")

    # Ikona aplikacji
    _assets = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
    icon_path = os.path.join(_assets, "icon.png")
    if os.path.exists(icon_path):
        _app.setWindowIcon(QIcon(icon_path))

    # Czcionka systemowa z fallbackiem
    font = QFont()
    font.setFamilies(["Segoe UI", "SF Pro Text", "Ubuntu", "Helvetica Neue", "sans-serif"])
    font.setPointSize(10)
    _app.setFont(font)

    # Globalny styl z PrefsManager
    _app.setStyleSheet(current_qss())

    return _app


def get_app() -> QApplication:
    """Zwraca istniejący QApplication lub tworzy nowy."""
    if _app is None:
        return create_app()
    return _app


def apply_theme(accent: str | None = None, dark: bool | None = None) -> None:
    """
    Zmienia motyw w locie — natychmiast aktualizuje cały UI.

    accent — kolor akcentu (hex, np. '#4F8EF7'). None = odczyt z PrefsManager.
    dark   — True = ciemny, False = jasny. None = odczyt z PrefsManager.
    """
    app = get_app()
    from utils.prefs_manager import PrefsManager
    prefs = PrefsManager()

    if accent is None:
        accent = prefs.get_accent()
    if dark is None:
        dark = (prefs.get("appearance_mode") or "dark").lower() != "light"

    app.setStyleSheet(build_qss(accent=accent, dark=dark))
