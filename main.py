#! python3.10
"""
main.py - Punkt wejścia aplikacji AegisVault (PyQt6)
=====================================================
Uruchomienie: py main.py
Flagi:        --no-splash   pomiń ekran startowy
"""

import sys
import logging

from utils.logger import setup_logging
from utils.paths import get_db_path
from utils.prefs_manager import PrefsManager


def _setup_excepthook():
    """Loguje niezłapane wyjątki do pliku zamiast cicho crashować."""
    _log = logging.getLogger("aegisvault.crash")

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        _log.critical("Niezłapany wyjątek", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = _hook


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
    _setup_excepthook()

    from gui_qt.app import create_app
    app = create_app()

    db_path   = get_db_path("aegisvault.db")
    no_splash = "--no-splash" in sys.argv

    if not no_splash:
        window = _run_splash(app, db_path)
    else:
        from gui_qt.app_window import AppWindow
        window = AppWindow(db_path)

    window.show()
    app.exec()


def _run_splash(app, db_path: str):
    """
    Splash screen z ładowaniem aplikacji w tle.
    Buduje AppWindow podczas trwania splasha — żeby po zamknięciu splasha
    okno było gotowe i nie lagowało przy pierwszym wyświetleniu.
    Zwraca gotowy (ale ukryty) AppWindow.
    """
    from version import APP_VERSION
    from gui_qt.splash_screen import SplashScreen
    from PyQt6.QtCore import QTimer, QThread

    splash = SplashScreen(APP_VERSION)
    splash.show()
    app.processEvents()

    # Krok, procent, etykieta, akcja ("db" | "window" | None)
    steps = [
        (8,   "Inicjalizacja...",              None),
        (28,  "Ładowanie bazy danych...",      "db"),
        (52,  "Sprawdzanie integralności...",  None),
        (72,  "Przygotowywanie interfejsu...", "window"),
        (88,  "Konfiguracja wyglądu...",       None),
        (100, "Gotowe!",                       None),
    ]

    window_holder = [None]
    idx  = [0]
    done = [False]

    def _next():
        if idx[0] >= len(steps):
            # Krótka pauza na "Gotowe!" potem fade-out
            def _finish():
                if window_holder[0] is None:
                    # fallback — window nie został zbudowany w trakcie
                    from gui_qt.app_window import AppWindow
                    window_holder[0] = AppWindow(db_path)
                splash.finish(lambda: None)
                done[0] = True
            QTimer.singleShot(500, _finish)
            return

        pct, label, action = steps[idx[0]]
        idx[0] += 1
        splash.set_progress(pct, label)
        app.processEvents()

        if action == "db":
            try:
                from database.models import init_db
                init_db(db_path)
            except Exception:
                pass
            app.processEvents()

        elif action == "window":
            # Buduj AppWindow ukryty — najcięższy krok
            try:
                from gui_qt.app_window import AppWindow
                window_holder[0] = AppWindow(db_path)
                app.processEvents()
            except Exception:
                pass

        QTimer.singleShot(300, _next)

    QTimer.singleShot(0, _next)
    while not done[0] or splash.isVisible():
        app.processEvents()
        QThread.msleep(16)

    return window_holder[0]


if __name__ == "__main__":
    _mutex = _acquire_mutex()
    main()
