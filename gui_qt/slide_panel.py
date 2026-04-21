"""
slide_panel.py — Bazowa klasa slide-in paneli (PyQt6)
=====================================================
SlidePanelBase: QFrame wjeżdżający z prawej strony z ciemnym overlay.
"""

from PyQt6.QtWidgets import QFrame, QWidget, QApplication
from PyQt6.QtCore import Qt, QRect, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QPainter, QColor

from gui_qt.hex_background import HexBackground
from utils.prefs_manager import PrefsManager


class _Overlay(QWidget):
    """Półprzezroczyste tło blokujące kliknięcia — klik zamyka panel."""

    clicked = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor(0, 0, 0, 120))
        painter.end()

    def mousePressEvent(self, event):
        self.clicked.emit()


class SlidePanelBase(QFrame):
    """
    Bazowa klasa slide-in panelu.
    Szerokość: min(PANEL_WIDTH, parent.width()*0.92).
    Wysokość: ograniczona do faktycznie widocznego obszaru (uwzględnia taskbar/ekran).
    """

    PANEL_WIDTH = 580
    ANIM_IN_MS  = 220
    ANIM_OUT_MS = 180

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._prefs = PrefsManager()
        self._anim: QPropertyAnimation | None = None
        self._overlay = _Overlay(parent)
        self._overlay.clicked.connect(self.close)
        self._overlay.hide()

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setContentsMargins(0, 0, 0, 0)
        self.hide()

        self._hex_bg = HexBackground(self, hex_size=30, glow_max=2, glow_interval_ms=2200,
                                     animate=False)
        self._hex_bg.lower()

        self._build_ui()

    # ── Helpers prywatne ──────────────────────────────────────────────

    def _safe_height(self, parent: QWidget) -> int:
        """
        Zwraca bezpieczną wysokość panelu.

        Oblicza ile pikseli okna wychodzi poza dostępny obszar ekranu
        (pasek zadań, krawędź monitora) i odejmuje tę nadwyżkę, żeby
        panel nigdy nie był przycinany przez system.
        """
        ph = parent.height()
        win = parent.window()

        # Preferuj ekran okna, fallback na główny ekran
        try:
            screen = win.screen()
        except Exception:
            screen = QApplication.primaryScreen()

        if screen:
            avail      = screen.availableGeometry()   # bez paska zadań
            win_inner  = win.geometry()               # klient (bez dekoracji)
            # Jak bardzo dolna krawędź klienta wychodzi poza dostępny obszar?
            overflow = max(0, win_inner.bottom() - avail.bottom())
            ph = max(ph - overflow - 4, 100)

        return ph

    # ── Animacje tła main window ──────────────────────────────────────

    def _pause_main_window_bg(self):
        mw = self.parentWidget().window() if self.parentWidget() else None
        if mw and hasattr(mw, "_pause_bg_animations"):
            try:
                mw._pause_bg_animations()
            except Exception:
                pass

    def _resume_main_window_bg(self):
        mw = self.parentWidget().window() if self.parentWidget() else None
        if mw and hasattr(mw, "_resume_bg_animations"):
            try:
                mw._resume_bg_animations()
            except Exception:
                pass

    # ── Do nadpisania ─────────────────────────────────────────────────

    def _build_ui(self):
        raise NotImplementedError

    # ── Animacje ──────────────────────────────────────────────────────

    def open(self):
        """Wysuwa panel z prawej i pokazuje overlay."""
        parent = self.parentWidget()
        pw = parent.width()
        ph = self._safe_height(parent)
        w  = min(self.PANEL_WIDTH, int(pw * 0.92))

        self._pause_main_window_bg()

        self._overlay.setGeometry(0, 0, pw, ph)
        self._overlay.show()
        self._overlay.raise_()

        self.setGeometry(pw, 0, w, ph)
        self.show()
        self.raise_()
        self._resize_hex(w, ph)

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(self.ANIM_IN_MS)
        self._anim.setStartValue(QRect(pw, 0, w, ph))
        self._anim.setEndValue(QRect(pw - w, 0, w, ph))
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def close(self):
        """Chowa panel z animacją i usuwa overlay."""
        if self._anim and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()

        cur = self.geometry()
        pw  = self.parentWidget().width()

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(self.ANIM_OUT_MS)
        self._anim.setStartValue(cur)
        self._anim.setEndValue(QRect(pw, cur.y(), cur.width(), cur.height()))
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.finished.connect(self._on_closed)
        self._anim.start()

    def _on_closed(self):
        self._resume_main_window_bg()
        self.hide()
        self._overlay.hide()
        if hasattr(self, "_hex_bg") and self._hex_bg:
            self._hex_bg.stop_animation()
        self._overlay.deleteLater()
        self.deleteLater()

    # ── Helpers ───────────────────────────────────────────────────────

    def _resize_hex(self, w, h):
        if hasattr(self, "_hex_bg") and self._hex_bg:
            self._hex_bg.setGeometry(0, 0, w, h)
            self._hex_bg.lower()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_hex(self.width(), self.height())

    def paintEvent(self, event):
        dark = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor("#1a1a1a" if dark else "#f5f5f5"))
        painter.end()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
