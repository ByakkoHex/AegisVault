#! python3.10
"""
main.py - Punkt wejścia aplikacji AegisVault (PyQt6)
=====================================================
Uruchomienie: py main.py
"""

import sys
import os

from utils.logger import setup_logging
from utils.paths import get_db_path
from utils.prefs_manager import PrefsManager


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

    from gui_qt.app import create_app
    app = create_app()

    from gui_qt.login_window import LoginWindow
    login = LoginWindow(db_path=get_db_path("aegisvault.db"))
    login.show()
    app.exec()

    # Po zamknięciu LoginWindow — sprawdź czy zalogowano
    while login.logged_user and login.crypto:
        from gui_qt.main_window import MainWindow
        main_win = MainWindow(login.db, login.crypto, login.logged_user)
        main_win.show()
        app.exec()

        if not main_win.logged_out:
            break  # normalne zamknięcie okna — wyłącz aplikację

        # Wylogowanie — wróć do ekranu logowania
        from gui_qt.login_window import LoginWindow
        login = LoginWindow(db_path=get_db_path("aegisvault.db"))
        login.show()
        app.exec()


if __name__ == "__main__":
    _mutex = _acquire_mutex()
    main()
