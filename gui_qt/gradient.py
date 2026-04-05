"""
gradient.py — GradientWidget + AnimatedGradientWidget (PyQt6)
=============================================================
Zamiennik gui/gradient.py. Zamiast tk.Canvas z ręcznie zarządzanymi
prostokątami — QWidget.paintEvent + QLinearGradient. Qt sam robi
smooth gradient w jednym wywołaniu, bez loopów przez N pasków.

GradientWidget          — statyczny gradient między dwoma kolorami
AnimatedGradientWidget  — animowany separator / ambient background
    anim_mode="breathe" — intensywność akcentu tętni sinusoidalnie
    anim_mode="slide"   — pasmo akcentu przesuwa się wzdłuż gradientu
    anim_mode="sweep"   — gaussowski rozbłysk przesuwa się wzdłuż

Publiczne API identyczne z CTk wersją:
    start_animation() / stop_animation()
    update_accent(accent, base)
    pause() / resume()
"""

import math
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore    import Qt, QTimer, QRectF, pyqtSignal
from PyQt6.QtGui     import (
    QPainter, QLinearGradient, QColor, QPen, QBrush,
)

from utils.prefs_manager import PrefsManager


def _lerp_color(c1: str, c2: str, t: float) -> QColor:
    """Interpolacja liniowa między dwoma kolorami hex."""
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return QColor(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


def _hex_lerp(c1: str, c2: str, t: float) -> str:
    """Zwraca interpolowany kolor jako hex string."""
    c = _lerp_color(c1, c2, t)
    return f"#{c.red():02x}{c.green():02x}{c.blue():02x}"


# ══════════════════════════════════════════════════════════════════════
# GradientWidget — statyczny gradient
# ══════════════════════════════════════════════════════════════════════

class GradientWidget(QWidget):
    """
    Statyczny gradient między color_from a color_to.

    direction="h" — poziomy (lewo→prawo)
    direction="v" — pionowy (góra→dół)
    """

    def __init__(
        self,
        parent=None,
        color_from: str = "#4F8EF7",
        color_to:   str = "#1a1a1a",
        direction:  str = "h",
        **kw,
    ):
        super().__init__(parent, **kw)
        self._c1  = color_from
        self._c2  = color_to
        self._dir = direction
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

    def update_colors(self, color_from: str | None = None,
                      color_to: str | None = None) -> None:
        if color_from is not None:
            self._c1 = color_from
        if color_to is not None:
            self._c2 = color_to
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        r = self.rect()

        if self._dir == "h":
            grad = QLinearGradient(r.left(), 0, r.right(), 0)
        else:
            grad = QLinearGradient(0, r.top(), 0, r.bottom())

        grad.setColorAt(0.0, QColor(self._c1))
        grad.setColorAt(1.0, QColor(self._c2))

        painter.fillRect(r, grad)
        painter.end()


# ══════════════════════════════════════════════════════════════════════
# AnimatedGradientWidget — animowany gradient
# ══════════════════════════════════════════════════════════════════════

class AnimatedGradientWidget(GradientWidget):
    """
    Gradient z animacją. Używa QTimer zamiast after() — zero glitchy.

    Tryby (anim_mode):
        "breathe" — intensywność akcentu tętni sinusoidalnie (ambient glow)
        "slide"   — pasmo akcentu przesuwa się wzdłuż (separator shimmer)
        "sweep"   — gaussowski rozbłysk przesuwa się wzdłuż

    Parametry:
        accent      — kolor akcentu (#rrggbb)
        base        — kolor tła (#rrggbb)
        anim_mode   — "breathe" | "slide" | "sweep"
        alpha_min   — min intensywność akcentu (breathe)
        alpha_max   — max intensywność akcentu (breathe)
        period_ms   — czas pełnego cyklu (ms)
        fps         — klatki/s animacji (15 wystarczy dla separatorów)
        n_bands     — ile pasm widocznych jednocześnie (slide)
        reverse     — odwróć kierunek gradientu
    """

    def __init__(
        self,
        parent=None,
        accent:    str   = "#4F8EF7",
        base:      str   = "#1a1a1a",
        anim_mode: str   = "breathe",
        alpha_min: float = 0.05,
        alpha_max: float = 0.15,
        period_ms: int   = 4000,
        fps:       int   = 15,
        n_bands:   int   = 1,
        reverse:   bool  = False,
        **kw,
    ):
        self._accent_hex = accent
        self._base_hex   = base
        self._anim_mode  = anim_mode
        self._alpha_min  = alpha_min
        self._alpha_max  = alpha_max
        self._period_ms  = period_ms
        self._fps        = fps
        self._n_bands    = n_bands
        self._reverse    = reverse
        self._phase      = 0.0
        self._paused     = False

        mid = (alpha_min + alpha_max) / 2
        if reverse:
            c_from, c_to = base, _hex_lerp(base, accent, mid)
        else:
            c_from, c_to = _hex_lerp(base, accent, mid), base

        super().__init__(parent, color_from=c_from, color_to=c_to, **kw)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ── Publiczne API ─────────────────────────────────────────────────

    def start_animation(self) -> None:
        if not self._timer.isActive():
            interval = max(16, 1000 // self._fps)
            self._timer.start(interval)

    def stop_animation(self) -> None:
        self._timer.stop()

    def pause(self) -> None:
        if not self._paused:
            self._paused = True
            self._timer.stop()

    def resume(self) -> None:
        if self._paused:
            self._paused = False
            self.start_animation()

    def update_accent(self, accent: str, base: str) -> None:
        self._accent_hex = accent
        self._base_hex   = base
        self._c2         = base
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._paused and not self._timer.isActive():
            self.start_animation()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._timer.isActive():
            self._timer.stop()

    # ── Wewnętrzna pętla ──────────────────────────────────────────────

    def _tick(self) -> None:
        dt = (2 * math.pi) / (self._period_ms / (1000.0 / self._fps))
        self._phase = (self._phase + dt) % (2 * math.pi)
        self._update_colors()
        self.update()   # schedules repaint — Qt batch-uje, zero flicker

    def _update_colors(self) -> None:
        """Przelicza _c1/_c2 według aktualnej fazy."""
        if self._anim_mode == "breathe":
            alpha = self._alpha_min + (self._alpha_max - self._alpha_min) * (
                0.5 + 0.5 * math.sin(self._phase)
            )
            if self._reverse:
                self._c1 = self._base_hex
                self._c2 = _hex_lerp(self._base_hex, self._accent_hex, alpha)
            else:
                self._c1 = _hex_lerp(self._base_hex, self._accent_hex, alpha)
                self._c2 = self._base_hex
        # slide i sweep: kolory liczone bezpośrednio w paintEvent

    def paintEvent(self, event) -> None:
        if self._anim_mode == "breathe":
            # Normalny gradient z aktualnymi _c1/_c2
            super().paintEvent(event)
            return

        # slide i sweep: N pasm → QLinearGradient z wieloma stops
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        r    = self.rect()
        w, h = r.width(), r.height()
        if w <= 0 or h <= 0:
            painter.end()
            return

        if self._dir == "h":
            grad = QLinearGradient(0, 0, w, 0)
        else:
            grad = QLinearGradient(0, 0, 0, h)

        slide = self._phase / (2 * math.pi)  # 0.0 → 1.0

        N = 64   # liczba stop-ów gradientu — Qt interpoluje między nimi
        for i in range(N + 1):
            t = i / N
            if self._reverse:
                t = 1.0 - t

            if self._anim_mode == "slide":
                t_shifted = (t - slide) % 1.0
                wave = 0.5 + 0.5 * math.sin(
                    t_shifted * self._n_bands * 2 * math.pi
                )
                color = _lerp_color(self._base_hex, self._accent_hex, wave)

            else:  # sweep
                sweep_pos = slide
                sigma_sq  = 2 * 0.09 * 0.09
                base_t    = t
                dist      = abs(base_t - sweep_pos)
                if dist > 0.5:
                    dist = 1.0 - dist
                glow  = math.exp(-(dist * dist) / sigma_sq)
                # base gradient accent→base
                bc    = _lerp_color(self._accent_hex, self._base_hex, base_t)
                color = _lerp_color(
                    f"#{bc.red():02x}{bc.green():02x}{bc.blue():02x}",
                    self._accent_hex,
                    glow * 0.55,
                )

            grad.setColorAt(i / N, color)

        painter.fillRect(r, grad)
        painter.end()
