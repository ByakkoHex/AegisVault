#! python3.10
"""
main.py - Punkt wejścia aplikacji AegisVault (PyQt6)
=====================================================
Uruchomienie: py main.py
Flagi:        --no-splash   pomiń ekran startowy
"""

import sys

from utils.logger import setup_logging
from utils.paths import get_db_path
from utils.prefs_manager import PrefsManager


def _acquire_mutex():
    """Zapobiega uruchomieniu dwóch instancji."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "AegisVaultRunning")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            ctypes.windll.user32.MessageBoxW(
                0, "AegisVault jest już uruchomiony.", "AegisVault", 0x40,
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

    db_path   = get_db_path("aegisvault.db")
    no_splash = "--no-splash" in sys.argv

    if not no_splash:
        _run_splash(app, db_path)

    from gui_qt.app_window import AppWindow
    window = AppWindow(db_path)
    window.show()
    app.exec()


def _run_splash(app, db_path: str) -> None:
    """Splash screen z prawdziwym ładowaniem bazy w tle."""
    from version import APP_VERSION
    from gui_qt.splash_screen import SplashScreen
    from PyQt6.QtCore import QTimer

    splash = SplashScreen(APP_VERSION)
    splash.show()
    app.processEvents()

    steps = [
        (15,  "Inicjalizacja..."),
        (45,  "Ładowanie bazy danych..."),
        (75,  "Sprawdzanie integralności..."),
        (95,  "Przygotowywanie interfejsu..."),
        (100, "Gotowe!"),
    ]
    idx = [0]
    done = [False]

    def _next():
        if idx[0] >= len(steps):
            QTimer.singleShot(280, lambda: splash.finish(lambda: None))
            done[0] = True
            return
        pct, label = steps[idx[0]]
        idx[0] += 1
        splash.set_progress(pct, label)
        app.processEvents()
        if pct == 45:
            try:
                from database.models import init_db
                init_db(db_path)
            except Exception:
                pass
        QTimer.singleShot(200, _next)

    # Uruchom kroki i poczekaj aż splash się zamknie
    QTimer.singleShot(0, _next)
    while not done[0] or splash.isVisible():
        app.processEvents()
        from PyQt6.QtCore import QThread
        QThread.msleep(16)


if __name__ == "__main__":
    _mutex = _acquire_mutex()
    main()
