"""
app_window.py — Pojedyncze okno aplikacji AegisVault
=====================================================
Jedno okno przez cały cykl życia:
  • strona 0 — LoginWindow (panel logowania, pełna szerokość)
  • strona 1 — MainWindow  (vault)
Przejście: cross-fade bez zmiany rozmiaru.
"""

import os
from PyQt6.QtWidgets import (
    QMainWindow, QStackedWidget, QApplication,
    QGraphicsOpacityEffect,
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QIcon

from utils.prefs_manager import PrefsManager

_WINDOW_SIZE = (980, 660)
_WINDOW_MIN  = (800, 520)
_FADE_MS     = 200


class AppWindow(QMainWindow):
    """Jedyne okno top-level aplikacji — zarządza przejściem login ↔ vault."""

    def __init__(self, db_path: str):
        super().__init__()
        self._db_path = db_path
        self._prefs   = PrefsManager()

        self.setWindowTitle("AegisVault")
        self.setMinimumSize(*_WINDOW_MIN)
        self._set_icon()

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._show_login()

    # ── Login ─────────────────────────────────────────────────────────

    def _show_login(self):
        from gui_qt.login_window import LoginWindow
        self._login_win = LoginWindow(db_path=self._db_path, embedded=True)
        self._login_win.login_success.connect(self._on_login_success)
        self._stack.addWidget(self._login_win)
        self._stack.setCurrentWidget(self._login_win)
        self.resize(*_WINDOW_SIZE)
        self._center_on_screen()
        self.setWindowTitle("AegisVault — Logowanie")

    def _on_login_success(self, user, crypto, db):
        from gui_qt.main_window import MainWindow
        self._main_win = MainWindow(db, crypto, user, embedded=True)
        self._main_win.logout_requested.connect(self._on_logout)
        self._stack.addWidget(self._main_win)
        self._crossfade(self._login_win, self._main_win,
                        after=lambda: self.setWindowTitle(f"AegisVault — {user.username}"))

    # ── Logout ────────────────────────────────────────────────────────

    def _on_logout(self):
        old_main = self._main_win

        def _cleanup():
            self._stack.removeWidget(old_main)
            old_main.deleteLater()

        # Nowe logowanie przed animacją
        from gui_qt.login_window import LoginWindow
        self._login_win = LoginWindow(db_path=self._db_path, embedded=True)
        self._login_win.login_success.connect(self._on_login_success)
        self._stack.addWidget(self._login_win)

        self._crossfade(old_main, self._login_win,
                        after=lambda: (_cleanup(),
                                       self.setWindowTitle("AegisVault — Logowanie")))

    # ── Animacja ──────────────────────────────────────────────────────

    def _crossfade(self, outgoing, incoming, after=None):
        """Płynne przejście fade-out → switch → fade-in."""
        # Fade-out
        eff_out = QGraphicsOpacityEffect(outgoing)
        outgoing.setGraphicsEffect(eff_out)
        anim_out = QPropertyAnimation(eff_out, b"opacity", self)
        anim_out.setDuration(_FADE_MS)
        anim_out.setStartValue(1.0)
        anim_out.setEndValue(0.0)
        anim_out.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _switch():
            outgoing.setGraphicsEffect(None)
            self._stack.setCurrentWidget(incoming)

            eff_in = QGraphicsOpacityEffect(incoming)
            incoming.setGraphicsEffect(eff_in)
            eff_in.setOpacity(0.0)
            anim_in = QPropertyAnimation(eff_in, b"opacity", self)
            anim_in.setDuration(_FADE_MS)
            anim_in.setStartValue(0.0)
            anim_in.setEndValue(1.0)
            anim_in.setEasingCurve(QEasingCurve.Type.InCubic)

            def _done():
                incoming.setGraphicsEffect(None)
                if after:
                    after()

            anim_in.finished.connect(_done)
            self._anim_in = anim_in
            anim_in.start()

        anim_out.finished.connect(_switch)
        self._anim_out = anim_out
        anim_out.start()

    # ── Helpers ───────────────────────────────────────────────────────

    def _set_icon(self):
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png"
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    def _center_on_screen(self):
        try:
            screen = QApplication.primaryScreen().geometry()
            self.move(
                screen.x() + (screen.width()  - self.width())  // 2,
                screen.y() + (screen.height() - self.height()) // 2,
            )
        except Exception:
            pass
