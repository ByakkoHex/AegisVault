"""
clipboard.py — bezpieczne kopiowanie wrażliwych danych do schowka.

Na Windows 11 z włączoną historią schowka (Win+V) hasła mogą w niej
pozostać na stałe nawet po 30s auto-clear. Jeśli użytkownik włączył opcję
"Wyczyść historię schowka po kopiowaniu", funkcja usuwa wpis przez WinRT API.

Fallback: jeśli winrt niedostępne — kopiuje normalnie bez czyszczenia historii.
"""

import sys
import pyperclip
from utils.logger import get_logger

_logger = get_logger(__name__)

# Czy winrt jest dostępne (Windows 10 2004+ z pakietem winrt)
_winrt_available: bool | None = None   # None = nie sprawdzone jeszcze


def _check_winrt() -> bool:
    global _winrt_available
    if _winrt_available is not None:
        return _winrt_available
    if sys.platform != "win32":
        _winrt_available = False
        return False
    try:
        import winrt.windows.applicationmodel.datatransfer as _dt  # noqa: F401
        _winrt_available = True
    except Exception:
        _winrt_available = False
    return _winrt_available


def _clear_clipboard_history() -> bool:
    """
    Czyści historię schowka Windows (Win+V).
    Zwraca True gdy operacja się powiodła.
    """
    try:
        import winrt.windows.applicationmodel.datatransfer as dt
        dt.Clipboard.clear_history()
        return True
    except Exception as e:
        _logger.debug(f"clipboard history clear failed: {e}")
        return False


def copy_sensitive(text: str, clear_history: bool | None = None) -> bool:
    """
    Kopiuje wrażliwy tekst do schowka.

    Args:
        text:          Tekst do skopiowania.
        clear_history: True = wyczyść historię schowka Win+V.
                       None = odczytaj z PrefsManager ("clear_clipboard_history").

    Zwraca True gdy dane trafiły do schowka.
    """
    try:
        pyperclip.copy(text)
    except Exception as e:
        _logger.error(f"pyperclip.copy failed: {e}")
        return False

    if clear_history is None:
        try:
            from utils.prefs_manager import PrefsManager
            clear_history = bool(PrefsManager().get("clear_clipboard_history"))
        except Exception:
            clear_history = False

    if clear_history and _check_winrt():
        _clear_clipboard_history()

    return True
