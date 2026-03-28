"""
autostart.py - Uruchamianie AegisVault przy starcie Windows
============================================================
Zapisuje/usuwa wpis w HKCU/SOFTWARE/Microsoft/Windows/CurrentVersion/Run.
"""

import sys
import os

_REG_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"  # noqa: W605
_APP_NAME  = "AegisVault"


def _get_command() -> str:
    """Buduje komendę uruchamiającą aplikację (pythonw, bez okna konsoli)."""
    exe = sys.executable
    # Zamień python.exe → pythonw.exe żeby nie pokazywać konsoli
    pythonw = exe.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = exe  # fallback

    # Ścieżka do main.py (katalog nadrzędny względem tego pliku)
    main_py = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "main.py")
    )
    return f'"{pythonw}" "{main_py}"'


def is_enabled() -> bool:
    """Zwraca True jeśli wpis autostartu istnieje w rejestrze."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, _APP_NAME)
        winreg.CloseKey(key)
        return True
    except (OSError, FileNotFoundError):
        return False


def enable() -> bool:
    """Dodaje wpis autostartu. Zwraca True przy sukcesie."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, _get_command())
        winreg.CloseKey(key)
        return True
    except OSError:
        return False


def disable() -> bool:
    """Usuwa wpis autostartu. Zwraca True przy sukcesie."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, _APP_NAME)
        winreg.CloseKey(key)
        return True
    except (OSError, FileNotFoundError):
        return False
