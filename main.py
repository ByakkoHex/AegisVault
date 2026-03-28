"""
main.py - Punkt wejścia aplikacji AegisVault
=============================================
Uruchomienie: py main.py
"""

from gui.login_window import LoginWindow
from gui.main_window import MainWindow
from utils.font_manager import setup_fonts
from utils.logger import setup_logging
from utils.paths import get_db_path
from utils.prefs_manager import PrefsManager
import customtkinter as ctk
import tkinter as tk
import sys
import os


def _suppress_stale_after_errors(exc, val, tb):
    """Wycisza 'invalid command name' — harmless callbacks po zniszczeniu widgetu."""
    if "invalid command name" in str(val):
        return
    # Pozostałe błędy wyświetl standardowo
    import traceback
    traceback.print_exception(exc, val, tb)


def _acquire_mutex():
    """Zapobiega uruchomieniu dwóch instancji i informuje instalator że app działa."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "AegisVaultRunning")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            ctypes.windll.user32.MessageBoxW(
                0,
                "AegisVault jest już uruchomiony.",
                "AegisVault",
                0x40,  # MB_ICONINFORMATION
            )
            sys.exit(0)
        return mutex
    except Exception:
        return None


def main():
    prefs = PrefsManager()
    setup_logging(prefs.get("log_retention_days"))
    # Załaduj font Roboto
    APP_FONT = setup_fonts()
    # Ustaw globalnie dla CTk
    ctk.CTkFont._default_font_family = APP_FONT

    # Ikona aplikacji (pasek zadań + Alt+Tab)
    _icon = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")

    # 1. Pokaż okno logowania (z cross-platform ścieżką DB)
    login = LoginWindow(db_path=get_db_path("aegisvault.db"))
    login.report_callback_exception = _suppress_stale_after_errors
    if os.path.exists(_icon):
        login.iconbitmap(_icon)
    login.mainloop()

    # 2. Jeśli zalogowano — otwórz główne okno
    if login.logged_user and login.crypto:
        # Hide the (already-destroyed) login window to close any lingering frame
        # before the main window builds; guard in case it was already destroyed.
        try:
            login.withdraw()
        except Exception:
            pass

        app = MainWindow(login.db, login.crypto, login.logged_user)
        app.report_callback_exception = _suppress_stale_after_errors
        if os.path.exists(_icon):
            app.iconbitmap(_icon)
        app.protocol("WM_DELETE_WINDOW", app.on_close)
        app.mainloop()


if __name__ == "__main__":
    _mutex = _acquire_mutex()
    main()
