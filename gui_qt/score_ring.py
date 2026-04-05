"""
score_ring.py — Animowany wskaźnik bezpieczeństwa (PyQt6)
=========================================================
Zamiennik gui/score_ring.py. QWidget.paintEvent + QPainter.drawArc
zamiast tk.Canvas. Gradient łuku (czerwony→pomarańczowy→zielony),
animacja do docelowej wartości (18% kroku per klatka), subtelny pulse.

Publiczne API identyczne z CTk wersją:
    ring.animate_to(score)   — animuje łuk do wartości 0-100
    ring.start_pulse()       — uruchamia pulsowanie
    ring.stop_pulse()        — zatrzymuje wszystko
    ring.set_bg(color, dark) — zmiana tła przy zmianie motywu
"""

import math
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore    import Qt, QTimer, QRect, QRectF
from PyQt6.QtGui     import (
    QPainter, QColor, QPen, QFont, QFontMetrics,
    QConicalGradient, QBrush,
)


_ARC_TRACK_DARK  = "#2e2e2e"
_ARC_TRACK_LIGHT = "#e0e0e0"


def _lerp_str(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"


def _score_color(score: int) -> str:
    t = max(0, min(100, score)) / 100.0
    if t <= 0.5:
        return _lerp_str("#e05252", "#f0a500", t / 0.5)
    return _lerp_str("#f0a500", "#4caf50", (t - 0.5) / 0.5)


class AnimatedScoreRing(QWidget):
    """
    Kołowy wskaźnik postępu z gradientem i animacją.

    size    — rozmiar widgetu w px (kwadrat)
    bg_color — kolor tła (dopasuj do rodzica)
    is_dark  — True dla dark mode (kolor toru łuku)
    """

    def __init__(self, parent=None, size: int = 44,
                 bg_color: str = "#1a1a1a", is_dark: bool = True, **kw):
        super().__init__(parent, **kw)
        self._sz       = size
        self._bg_color = bg_color
        self._is_dark  = is_dark
        self._score    = 0
        self._displayed = 0.0    # aktualny kąt łuku w stopniach (0–359.9)
        self._target    = 0.0
        self._pulse_phase = 0.0
        self._pulsing   = False

        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Timer dla animacji łuku (~60fps)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._step_arc)

        # Timer dla pulse (20fps)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._pulse_tick)

    # ── Publiczne API ─────────────────────────────────────────────────

    def animate_to(self, score: int) -> None:
        """Animuje łuk do nowej wartości score (0-100)."""
        self._score  = max(0, min(100, score))
        self._target = self._score / 100.0 * 359.9
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def start_pulse(self) -> None:
        """Uruchamia subtelne pulsowanie."""
        self._pulsing = True
        if not self._pulse_timer.isActive():
            self._pulse_timer.start()

    def stop_pulse(self) -> None:
        """Zatrzymuje animacje."""
        self._pulsing = False
        self._anim_timer.stop()
        self._pulse_timer.stop()

    def set_bg(self, bg_color: str, is_dark: bool = True) -> None:
        self._bg_color = bg_color
        self._is_dark  = is_dark
        self.update()

    # ── Wewnętrzna logika ─────────────────────────────────────────────

    def _step_arc(self) -> None:
        diff = self._target - self._displayed
        if abs(diff) < 0.5:
            self._displayed = self._target
            self._anim_timer.stop()
        else:
            self._displayed += diff * 0.18
        self.update()

    def _pulse_tick(self) -> None:
        self._pulse_phase = (self._pulse_phase + 0.04) % (2 * math.pi)
        self.update()

    # ── Rysowanie ────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        s   = self._sz
        pad = max(4, s // 11)
        arc_w = max(3, s // 9)   # grubość łuku

        rect = QRectF(pad, pad, s - pad * 2, s - pad * 2)

        # Tło widgetu
        painter.fillRect(self.rect(), QColor(self._bg_color))

        # Pulse — lekkie rozjaśnienie koloru łuku
        pulse = 0.12 * math.sin(self._pulse_phase) if self._pulsing else 0.0

        # ── Tor (szare pełne koło) ──────────────────────────────────
        track_color = _ARC_TRACK_DARK if self._is_dark else _ARC_TRACK_LIGHT
        pen = QPen(QColor(track_color))
        pen.setWidth(arc_w)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        # Qt: kąty w 1/16 stopnia, start=90° (góra), pełne koło = -360*16
        painter.drawArc(rect.toRect(), 90 * 16, -360 * 16)

        # ── Łuk postępu z gradientem ─────────────────────────────────
        if self._displayed > 0.5:
            N = 60   # segmentów gradientu
            seg_angle = self._displayed / N

            for i in range(N):
                seg_start = i * seg_angle
                if (i + 0.5) * seg_angle > self._displayed + 0.01:
                    break
                extent = min(seg_angle, self._displayed - seg_start)
                if extent <= 0:
                    break

                color_str = _score_color(int(i / N * 100))
                # Pulse: rozjaśnienie
                if pulse > 0:
                    color_str = _lerp_str(color_str, "#ffffff", pulse)

                pen = QPen(QColor(color_str))
                pen.setWidth(arc_w)
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                painter.setPen(pen)

                qt_start  = int((90 - seg_start) * 16)
                qt_extent = int(-extent * 16)
                painter.drawArc(rect.toRect(), qt_start, qt_extent)

        # ── Tekst w centrum ──────────────────────────────────────────
        score_str = str(self._score) if self._score > 0 else "--"
        font_size = max(7, s // 5)
        font = QFont("Segoe UI", font_size)
        font.setBold(True)
        painter.setFont(font)

        if self._score > 0:
            text_color = _score_color(self._score)
            if pulse > 0:
                text_color = _lerp_str(text_color, "#ffffff", pulse)
        else:
            text_color = "#555555" if self._is_dark else "#aaaaaa"

        painter.setPen(QColor(text_color))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, score_str)

        painter.end()
