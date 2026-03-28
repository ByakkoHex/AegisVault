"""
paths.py - Ścieżki danych aplikacji AegisVault (cross-platform)
===============================================================
Windows : %APPDATA%\AegisVault\
macOS   : ~/Library/Application Support/AegisVault/
Linux   : ~/.local/share/aegisvault/
"""

import os
import sys


APP_NAME = "AegisVault"


def get_app_data_dir() -> str:
    """Zwraca katalog danych aplikacji odpowiedni dla bieżącego systemu."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        path = os.path.join(base, APP_NAME)
    elif sys.platform == "darwin":
        path = os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_NAME)
    else:
        # Linux / BSD
        xdg = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
        path = os.path.join(xdg, APP_NAME.lower())

    os.makedirs(path, exist_ok=True)
    return path


def get_db_path(filename: str = "aegisvault.db") -> str:
    """Zwraca pełną ścieżkę do pliku bazy danych."""
    return os.path.join(get_app_data_dir(), filename)


def get_assets_dir() -> str:
    """Zwraca ścieżkę do folderu assets (obsługuje pakiet PyInstaller)."""
    if getattr(sys, "frozen", False):
        # Jesteśmy w spakowanym binarnym pliku PyInstaller
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets")
