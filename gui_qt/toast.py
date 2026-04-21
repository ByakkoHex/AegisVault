"""
toast.py — Niemodalne powiadomienia (toasty) dla AegisVault (PyQt6)
===================================================================
Małe popupy w prawym dolnym rogu okna, znikające automatycznie.
Animacja: slide-up + fade-in przy pojawieniu, fade-out przy znikaniu.
Stack do 3 jednocześnie.

Użycie:
    toast = ToastManager(parent_window)
    toast.show("Skopiowano!", "success")
    toast.show("Błąd połączenia", "error", duration_ms=4000)
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QGraphicsOpacityEffect,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QRect, QPoint,
)
from PyQt6.QtGui import QColor

from utils.prefs_manager import PrefsManager


_ICONS = {
    "success": "✔",
    "error":   "✖",
    "warning": "⚠",
    "info":    "ℹ",
}

_COLORS = {
    "success": "#4caf50",
    "error":   "#e05252",
    "warning": "#f0a500",
    "info":    "#4F8EF7",
}

_TOAST_W  = 300
_TOAST_H  = 52
_MARGIN   = 16
_SPACING  = 8
_MAX      = 3


class _Toast(QWidget):
    """Pojedynczy toast widget."""

    def __init__(self, parent: QWidget, message: str, kind: str):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(_TOAST_W, _TOAST_H)

        prefs = PrefsManager()
        dark  = (prefs.get("appearance_mode") or "dark").lower() != "light"
        bg    = "#252525" if dark else "#ffffff"
        text  = "#f0f0f0" if dark else "#1a1a1a"
        border= "#333333" if dark else "#d0d0d0"
        color = _COLORS.get(kind, "#4F8EF7")
        icon  = _ICONS.get(kind, "ℹ")

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border-radius: 10px;
                border: 1px solid {border};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 16, 0)
        layout.setSpacing(10)

        # Kolorowy pasek po lewej (jako label z kolorem tła)
        bar = QLabel()
        bar.setFixedWidth(3)
        bar.setFixedHeight(_TOAST_H - 16)
        bar.setStyleSheet(f"background-color: {color}; border-radius: 2px; border: none;")
        layout.addWidget(bar)

        # Ikona
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: bold; background: transparent; border: none;")
        icon_lbl.setFixedWidth(20)
        layout.addWidget(icon_lbl)

        # Wiadomość
        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(False)
        msg_lbl.setStyleSheet(f"color: {text}; font-size: 12px; background: transparent; border: none;")
        msg_lbl.setMaximumWidth(220)
        layout.addWidget(msg_lbl, stretch=1)

        # Opacity effect dla animacji
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)

        self._anim_in  = None
        self._anim_out = None

    def animate_in(self, target_y: int, on_done=None):
        """Slide-up + fade-in."""
        start_y = target_y + 20
        self.move(self.x(), start_y)
        self.show()

        # Fade-in
        fa = QPropertyAnimation(self._effect, b"opacity")
        fa.setDuration(150)
        fa.setStartValue(0.0)
        fa.setEndValue(1.0)
        fa.setEasingCurve(QEasingCurve.Type.OutQuad)
        fa.start()
        self._anim_in = fa

        # Slide-up (przez move)
        self._slide_to_y(target_y, duration=150)

    def animate_out(self, on_done=None):
        """Fade-out, potem wywołaj on_done."""
        fa = QPropertyAnimation(self._effect, b"opacity")
        fa.setDuration(200)
        fa.setStartValue(1.0)
        fa.setEndValue(0.0)
        fa.setEasingCurve(QEasingCurve.Type.InQuad)
        if on_done:
            fa.finished.connect(on_done)
        fa.start()
        self._anim_out = fa

    def slide_to_y(self, target_y: int):
        """Przesuń toast na nową pozycję (gdy inne toasty znikają)."""
        self._slide_to_y(target_y, duration=180)

    def _slide_to_y(self, target_y: int, duration: int = 180):
        """Animuje ruch pionowy (bez zmiany x)."""
        current = self.pos()
        steps   = max(1, duration // 16)
        step_ms = duration // steps
        dy      = (target_y - current.y()) / steps

        def _tick(step=0, y=float(current.y())):
            try:
                if step >= steps:
                    self.move(current.x(), target_y)
                    return
                self.move(current.x(), int(y + dy))
                QTimer.singleShot(step_ms, lambda: _tick(step + 1, y + dy))
            except RuntimeError:
                pass  # widget już zniszczony

        _tick()


class ToastManager:
    """Zarządza stosem toastów dla danego okna rodzica."""

    def __init__(self, parent: QWidget):
        self._parent  = parent
        self._stack:  list[_Toast] = []

    def show(self, message: str, kind: str = "info", duration_ms: int = 3000):
        """Pokaż nowy toast. Maksymalnie _MAX jednocześnie — najstarszy usuwany."""
        if len(self._stack) >= _MAX:
            self._dismiss(self._stack[0])

        toast = _Toast(self._parent, message, kind)
        self._stack.append(toast)
        self._reposition_all(animate_new=toast)

        # Auto-dismiss
        QTimer.singleShot(duration_ms, lambda: self._dismiss(toast))

    def _dismiss(self, toast: _Toast):
        if toast not in self._stack:
            return
        self._stack.remove(toast)

        def _cleanup():
            try:
                toast.hide()
                toast.deleteLater()
            except Exception:
                pass
            self._reposition_all()

        toast.animate_out(on_done=_cleanup)

    def _reposition_all(self, animate_new: _Toast | None = None):
        """Przelicza pozycje wszystkich toastów (stos od dołu)."""
        parent_w = self._parent.width()
        parent_h = self._parent.height()
        x = parent_w - _TOAST_W - _MARGIN

        for i, t in enumerate(reversed(self._stack)):
            y = parent_h - _MARGIN - (i + 1) * (_TOAST_H + _SPACING)
            if t is animate_new:
                t.move(x, y)
                t.animate_in(target_y=y)
            else:
                t.slide_to_y(y)
