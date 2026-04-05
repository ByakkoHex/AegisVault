"""
hex_background.py — Tło hexagonalne dla AegisVault (PyQt6)
==========================================================
Zamiennik gui/hex_background.py.

Główna klasa:
    HexBackground(parent) — QWidget z siatką hexagonów i animacją glow.
    Umieść jako pierwsze dziecko kontenera, wywołaj stackUnder(inne_widgety)
    lub lower() żeby znalazła się pod treścią.

Helper:
    setup_hex_background(parent) — tworzy i pozycjonuje HexBackground
    jako pełnoekranowe tło widgetu parent.

Tryby glow (glow_mode):
    "breath" — ~2s glow, sin-wave, kolor akcentu
    "fire"   — szybkie zapalenie + wolne gaśnięcie, więcej komórek

Architektura Qt:
    - paintEvent rysuje całą siatkę w jednym przejściu QPainter
    - QTimer dla harmonogramowania nowych glow (co 800ms)
    - Każdy aktywny glow to słownik iid→(step, steps_total, intensity)
    - Przejście koloru liczone bezpośrednio w paintEvent (bez osobnych timerów)
    - QTimer(40ms) dla kroków animacji glow aktywnych hexów
    - resizeEvent → odbudowanie siatki (z 80ms debounce)
"""

import math
import random
import functools
from PyQt6.QtWidgets import QWidget, QScrollArea, QSizePolicy
from PyQt6.QtCore    import Qt, QTimer, QPointF, QRectF, QSize
from PyQt6.QtGui     import (
    QPainter, QColor, QPen, QPolygonF, QBrush,
)

from utils.prefs_manager import PrefsManager


# ── Kolory ────────────────────────────────────────────────────────────
_DARK_BG   = "#1a1a1a"
_DARK_HEX  = "#2e2e2e"
_LIGHT_BG  = "#f5f5f5"
_LIGHT_HEX = "#ebebeb"

_DARK_GLOW_FB  = "#3a5288"
_LIGHT_GLOW_FB = "#d8e8fd"

# ── Timing ────────────────────────────────────────────────────────────
_GLOW_STEP_MS   = 40

_BREATH_STEPS   = 50
_FIRE_STEPS_MIN = 38
_FIRE_STEPS_MAX = 50

_BREATH_INT_MS  = 800
_FIRE_INT_MIN   = 150
_FIRE_INT_MAX   = 500

_BREATH_GLOW_PCT = 0.04
_FIRE_GLOW_PCT   = 0.09


# ── Helpers ───────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=512)
def _hex_pts(cx: float, cy: float, size: float) -> tuple:
    """Wierzchołki flat-top hexagonu."""
    pts = []
    for i in range(6):
        a = math.radians(60 * i)
        pts.append(QPointF(cx + size * math.cos(a), cy + size * math.sin(a)))
    return tuple(pts)


def _lerp_hex(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return (f"#{int(r1 + (r2-r1)*t):02x}"
            f"{int(g1 + (g2-g1)*t):02x}"
            f"{int(b1 + (b2-b1)*t):02x}")


def _glow_curve(step: int, steps: int, mode: str) -> float:
    t = step / max(steps, 1)
    if mode == "fire":
        if t <= 0.30:
            return math.sin(math.pi / 2 * (t / 0.30))
        return math.cos(math.pi / 2 * ((t - 0.30) / 0.70))
    return math.sin(math.pi * t)


def _get_accent() -> str:
    try:
        return PrefsManager().get_accent()
    except Exception:
        return _DARK_GLOW_FB


def _is_dark_mode() -> bool:
    try:
        from utils.prefs_manager import PrefsManager
        return (PrefsManager().get("appearance_mode") or "dark").lower() != "light"
    except Exception:
        return True


# ══════════════════════════════════════════════════════════════════════
# HexBackground
# ══════════════════════════════════════════════════════════════════════

class HexBackground(QWidget):
    """
    Widget z siatką hexagonów i animacją glow.

    Użycie jako tło:
        hex_bg = HexBackground(parent, glow_mode="breath")
        hex_bg.setGeometry(0, 0, parent.width(), parent.height())
        hex_bg.lower()   # lub stackUnder(inny_widget)

    Lub przez helper:
        hex_bg = setup_hex_background(parent)
    """

    def __init__(
        self,
        parent=None,
        hex_size:        int  = 36,
        animate:         bool = True,
        glow_max:        int  = 4,
        glow_interval_ms:int  = 800,
        glow_mode:       str  = "breath",
        bg_color:        str  | None = None,
        hidden_grid:     bool = False,
        **kw,
    ):
        super().__init__(parent, **kw)
        dark = _is_dark_mode()
        self._bg_color    = bg_color or (_DARK_BG if dark else _LIGHT_BG)
        self._hex_size    = hex_size
        self._animate     = animate
        self._base_max    = glow_max
        self._glow_int    = glow_interval_ms
        self._glow_mode   = glow_mode
        self._hidden_grid = hidden_grid

        # Siatka: lista krotek (cx, cy)
        self._hex_centers: list[tuple[float, float]] = []

        # Aktywne glow: index→(step, steps_total, intensity)
        self._glowing: dict[int, tuple[int, int, float]] = {}

        # Krok glow — jeden timer dla wszystkich aktywnych
        self._glow_step_timer = QTimer(self)
        self._glow_step_timer.setInterval(_GLOW_STEP_MS)
        self._glow_step_timer.timeout.connect(self._tick_glow_steps)

        # Harmonogram nowych glow
        self._sched_timer = QTimer(self)
        self._sched_timer.setSingleShot(True)
        self._sched_timer.timeout.connect(self._try_glow)

        # Debounce resize
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(80)
        self._resize_timer.timeout.connect(self._rebuild)

        # Styl: brak obramowania, transparentne tło obsługiwane w paintEvent
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAutoFillBackground(False)

    # ── Publiczne API ─────────────────────────────────────────────────

    def start_animation(self) -> None:
        if not self._animate:
            self._animate = True
        if self._hex_centers and not self._sched_timer.isActive():
            self._schedule_glow()

    def stop_animation(self) -> None:
        self._sched_timer.stop()
        self._glow_step_timer.stop()
        self._glowing.clear()
        self.update()

    def update_accent(self, new_accent: str | None = None) -> None:
        self.update()

    def update_theme(self) -> None:
        dark = _is_dark_mode()
        self._bg_color = _DARK_BG if dark else _LIGHT_BG
        self._rebuild()

    # ── Geometria ────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_timer.start()   # debounce 80ms

    def _rebuild(self) -> None:
        w, h = self.width(), self.height()
        if w <= 1 or h <= 1:
            return

        dark = _is_dark_mode()
        self._bg_color = _DARK_BG if dark else _LIGHT_BG
        if not self._hidden_grid:
            hex_col = _DARK_HEX if dark else _LIGHT_HEX
        else:
            hex_col = self._bg_color
        self._hex_col = hex_col

        size     = self._hex_size
        col_step = size * 1.5
        row_step = size * math.sqrt(3)

        self._hex_centers.clear()
        self._glowing.clear()

        for col in range(-1, int(w / col_step) + 3):
            cx    = col * col_step
            y_off = (row_step / 2) if (col % 2) else 0.0
            for row in range(-1, int(h / row_step) + 3):
                cy = row * row_step + y_off
                self._hex_centers.append((cx, cy))

        eff_max = max(self._base_max,
                      min(self._base_max * 8,
                          int(len(self._hex_centers) *
                              (_FIRE_GLOW_PCT if self._glow_mode == "fire"
                               else _BREATH_GLOW_PCT))))
        self._eff_max = eff_max

        if self._animate and self._hex_centers:
            self._schedule_glow()
            if not self._glow_step_timer.isActive():
                self._glow_step_timer.start()

        self.update()

    # ── Animacja glow ────────────────────────────────────────────────

    def _next_interval(self) -> int:
        if self._glow_mode == "fire":
            return random.randint(_FIRE_INT_MIN, _FIRE_INT_MAX)
        return _BREATH_INT_MS

    def _schedule_glow(self) -> None:
        if not self._sched_timer.isActive():
            self._sched_timer.start(self._next_interval())

    def _try_glow(self) -> None:
        if not self._animate or not self._hex_centers:
            return
        eff_max = getattr(self, "_eff_max", self._base_max)
        if len(self._glowing) < eff_max:
            calm = [i for i in range(len(self._hex_centers))
                    if i not in self._glowing]
            if calm:
                idx = random.choice(calm)
                if self._glow_mode == "fire":
                    steps = random.randint(_FIRE_STEPS_MIN, _FIRE_STEPS_MAX)
                    intensity = random.uniform(0.6, 1.0)
                else:
                    steps = _BREATH_STEPS
                    intensity = 1.0
                self._glowing[idx] = (0, steps, intensity)
                if not self._glow_step_timer.isActive():
                    self._glow_step_timer.start()
        self._schedule_glow()

    def _tick_glow_steps(self) -> None:
        """Krok animacji dla wszystkich aktywnych glow. Wywoływany co 40ms."""
        finished = []
        for idx, (step, steps_total, intensity) in self._glowing.items():
            next_step = step + 1
            if next_step >= steps_total:
                finished.append(idx)
            else:
                self._glowing[idx] = (next_step, steps_total, intensity)

        for idx in finished:
            del self._glowing[idx]

        if not self._glowing:
            self._glow_step_timer.stop()

        self.update()   # jeden repaint dla wszystkich

    # ── Rysowanie ────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Tło
        painter.fillRect(self.rect(), QColor(self._bg_color))

        if not self._hex_centers:
            painter.end()
            return

        hex_col   = getattr(self, "_hex_col", _DARK_HEX)
        accent    = _get_accent()
        size      = self._hex_size
        pen_width = 2

        for idx, (cx, cy) in enumerate(self._hex_centers):
            # Kolor outlines tego hexa
            if idx in self._glowing:
                step, steps_total, intensity = self._glowing[idx]
                t   = _glow_curve(step, steps_total, self._glow_mode) * intensity
                col = _lerp_hex(hex_col, accent, t)
            else:
                col = hex_col

            pen = QPen(QColor(col))
            pen.setWidth(pen_width)
            painter.setPen(pen)
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))

            pts = _hex_pts(cx, cy, size - 2)
            poly = QPolygonF(list(pts))
            painter.drawPolygon(poly)

        painter.end()


# ══════════════════════════════════════════════════════════════════════
# Helper — zakładanie tła na istniejący widget
# ══════════════════════════════════════════════════════════════════════

def setup_hex_background(
    parent:          QWidget,
    hex_size:        int  = 36,
    glow_max:        int  = 4,
    glow_interval_ms:int  = 800,
    glow_mode:       str  = "breath",
    hidden_grid:     bool = False,
) -> HexBackground:
    """
    Tworzy HexBackground jako pełnoekranowe tło widgetu parent.

    Automatycznie:
    - dopasowuje rozmiar do parent przy resize (przez resizeEvent override)
    - ustawia się pod innymi dziećmi (lower())

    Użycie:
        hex_bg = setup_hex_background(self)  # w __init__ widgetu
        # Dodawaj inne widgety normalnie — hex_bg jest na dole z-order
    """
    hex_bg = HexBackground(
        parent,
        hex_size=hex_size,
        animate=True,
        glow_max=glow_max,
        glow_interval_ms=glow_interval_ms,
        glow_mode=glow_mode,
        hidden_grid=hidden_grid,
    )
    hex_bg.setGeometry(0, 0, parent.width(), parent.height())
    hex_bg.lower()

    # Nadpisz resizeEvent rodzica żeby hex_bg się dopasowywał
    _orig_resize = getattr(parent, "_hex_bg_orig_resize", None)
    if _orig_resize is None:
        orig = parent.__class__.resizeEvent

        def _patched_resize(self_parent, event):
            orig(self_parent, event)
            try:
                if hex_bg and not hex_bg.isHidden():
                    hex_bg.setGeometry(
                        0, 0,
                        self_parent.width(),
                        self_parent.height(),
                    )
            except RuntimeError:
                pass  # widget usunięty

        parent.__class__.resizeEvent = _patched_resize
        parent._hex_bg_orig_resize   = orig

    return hex_bg


def setup_hex_for_scroll(
    scroll_area: QScrollArea,
    **kw,
) -> HexBackground:
    """
    Zakłada HexBackground jako tło contentu QScrollArea.
    Hex widget jest wewnątrz scroll_area.widget() (content widget),
    na samym dole z-order.
    """
    content = scroll_area.widget()
    if content is None:
        raise ValueError("QScrollArea nie ma content widget — wywołaj setWidget() najpierw")
    return setup_hex_background(content, **kw)
