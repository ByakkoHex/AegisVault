"""
animations.py — Helper funkcje animacji dla AegisVault (PyQt6)
=============================================================
Zamiennik gui/animations.py. Wszystko przez QPropertyAnimation —
zero glitchy, GPU-accelerated compositing.

Dostępne:
    slide_in(widget, direction, duration_ms, on_done)
    slide_out(widget, direction, duration_ms, on_done)
    fade_in(widget, duration_ms, on_done)
    fade_out(widget, duration_ms, on_done)
    shake(widget)
    pulse_color(widget, color_from, color_to, duration_ms)
    bind_hover(widget, normal_style, hover_style)
"""

import math
from PyQt6.QtWidgets import QWidget, QGraphicsOpacityEffect
from PyQt6.QtCore    import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QRect, QPoint, QParallelAnimationGroup, QSequentialAnimationGroup,
    pyqtSignal, QObject,
)
from PyQt6.QtGui import QColor


# ── Stałe czasu (ms) — spójne z utils/easing.py ──────────────────────
DURATION_MICRO  = 80
DURATION_SHORT  = 150
DURATION_MEDIUM = 220
DURATION_LONG   = 400


# ══════════════════════════════════════════════════════════════════════
# Slide
# ══════════════════════════════════════════════════════════════════════

def slide_in(
    widget:      QWidget,
    direction:   str  = "right",   # "right" | "left" | "bottom" | "top"
    duration_ms: int  = DURATION_MEDIUM,
    on_done              = None,
) -> QPropertyAnimation:
    """
    Wsuwa widget na ekran z wybranego kierunku.
    Widget musi być już widoczny i mieć poprawny rozmiar (po show() lub setGeometry).

    direction="right"  — wjeżdża z prawej strony rodzica
    direction="left"   — wjeżdża z lewej
    direction="bottom" — wjeżdża od dołu
    direction="top"    — wjeżdża od góry
    """
    parent = widget.parent()
    pw = parent.width()  if parent else widget.width()
    ph = parent.height() if parent else widget.height()
    ww = widget.width()
    wh = widget.height()

    if direction == "right":
        start = QRect(pw, 0, ww, wh)
        end   = QRect(0,  0, ww, wh)
    elif direction == "left":
        start = QRect(-ww, 0, ww, wh)
        end   = QRect(0,   0, ww, wh)
    elif direction == "bottom":
        start = QRect(0, ph,   ww, wh)
        end   = QRect(0, ph - wh, ww, wh)
    else:  # top
        start = QRect(0, -wh, ww, wh)
        end   = QRect(0, 0,   ww, wh)

    anim = QPropertyAnimation(widget, b"geometry")
    anim.setDuration(duration_ms)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    if on_done:
        anim.finished.connect(on_done)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def slide_out(
    widget:      QWidget,
    direction:   str = "right",
    duration_ms: int = DURATION_MEDIUM,
    on_done           = None,
) -> QPropertyAnimation:
    """Wysuwa widget poza ekran. Po animacji on_done jest wywoływany."""
    parent = widget.parent()
    pw = parent.width()  if parent else widget.width()
    ph = parent.height() if parent else widget.height()
    ww = widget.width()
    wh = widget.height()
    cur = widget.geometry()

    if direction == "right":
        end = QRect(pw, cur.y(), ww, wh)
    elif direction == "left":
        end = QRect(-ww, cur.y(), ww, wh)
    elif direction == "bottom":
        end = QRect(cur.x(), ph, ww, wh)
    else:  # top
        end = QRect(cur.x(), -wh, ww, wh)

    anim = QPropertyAnimation(widget, b"geometry")
    anim.setDuration(duration_ms)
    anim.setStartValue(cur)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.Type.InCubic)
    if on_done:
        anim.finished.connect(on_done)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


# ══════════════════════════════════════════════════════════════════════
# Fade
# ══════════════════════════════════════════════════════════════════════

def fade_in(
    widget:      QWidget,
    duration_ms: int = DURATION_SHORT,
    on_done           = None,
) -> QPropertyAnimation:
    """Fade-in widgetu od opacity=0 do 1."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)
    widget.show()

    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutQuad)
    if on_done:
        anim.finished.connect(on_done)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def fade_out(
    widget:      QWidget,
    duration_ms: int  = DURATION_SHORT,
    on_done            = None,
    hide_after:  bool = True,
) -> QPropertyAnimation:
    """Fade-out widgetu. Opcjonalnie chowa go po animacji."""
    if widget.graphicsEffect() is None:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    else:
        effect = widget.graphicsEffect()

    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration_ms)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.InQuad)

    def _finish():
        if hide_after:
            widget.hide()
        if on_done:
            on_done()

    anim.finished.connect(_finish)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


# ══════════════════════════════════════════════════════════════════════
# Shake — animacja błędu (np. błędne hasło)
# ══════════════════════════════════════════════════════════════════════

def shake(widget: QWidget, amplitude: int = 8, duration_ms: int = 350) -> None:
    """
    Animacja poziomego shake'a (jak na iOS przy złym haśle).
    Wywołaj po nieudanym logowaniu.
    """
    orig = widget.pos()
    steps = 6
    step_ms = duration_ms // (steps * 2)

    offsets = [amplitude, -amplitude, amplitude * 0.6,
               -amplitude * 0.6, amplitude * 0.3, 0]

    def _step(i=0):
        if i >= len(offsets):
            widget.move(orig)
            return
        widget.move(orig.x() + int(offsets[i]), orig.y())
        QTimer.singleShot(step_ms, lambda: _step(i + 1))

    _step()


# ══════════════════════════════════════════════════════════════════════
# Hover binding — smooth kolor przycisku
# ══════════════════════════════════════════════════════════════════════

def bind_hover_smooth(
    widget:       QWidget,
    normal_sheet: str,
    hover_sheet:  str,
) -> None:
    """
    Podmienia stylesheet przy hover z płynnym opóźnieniem.
    Prosta wersja — Qt obsługuje :hover w QSS, więc zazwyczaj
    wystarczy dodać QPushButton:hover { ... } w globalnym QSS.
    Ta funkcja jest dla przypadków niestandardowych widgetów.
    """
    widget.enterEvent = lambda e: widget.setStyleSheet(hover_sheet)
    widget.leaveEvent = lambda e: widget.setStyleSheet(normal_sheet)


# ══════════════════════════════════════════════════════════════════════
# Slide + Fade combo — panel główny
# ══════════════════════════════════════════════════════════════════════

def slide_fade_in(
    widget:      QWidget,
    direction:   str = "right",
    duration_ms: int = DURATION_MEDIUM,
    on_done           = None,
) -> QParallelAnimationGroup:
    """Slide-in + fade-in jednocześnie — używane dla paneli."""
    parent = widget.parent()
    pw = parent.width()  if parent else widget.width()
    ww = widget.width()
    wh = widget.height()

    if direction == "right":
        start_geom = QRect(pw, 0, ww, wh)
        end_geom   = QRect(0, 0, ww, wh)
    elif direction == "left":
        start_geom = QRect(-ww, 0, ww, wh)
        end_geom   = QRect(0, 0, ww, wh)
    else:
        start_geom = QRect(0, parent.height() if parent else wh, ww, wh)
        end_geom   = QRect(0, 0, ww, wh)

    # Geometry animation
    geo_anim = QPropertyAnimation(widget, b"geometry")
    geo_anim.setDuration(duration_ms)
    geo_anim.setStartValue(start_geom)
    geo_anim.setEndValue(end_geom)
    geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # Opacity animation
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)
    widget.show()

    op_anim = QPropertyAnimation(effect, b"opacity")
    op_anim.setDuration(duration_ms)
    op_anim.setStartValue(0.0)
    op_anim.setEndValue(1.0)
    op_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

    group = QParallelAnimationGroup()
    group.addAnimation(geo_anim)
    group.addAnimation(op_anim)
    if on_done:
        group.finished.connect(on_done)
    group.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return group


def slide_fade_out(
    widget:      QWidget,
    direction:   str  = "right",
    duration_ms: int  = DURATION_MEDIUM,
    on_done            = None,
    hide_after:  bool = True,
) -> QParallelAnimationGroup:
    """Slide-out + fade-out jednocześnie."""
    parent = widget.parent()
    pw = parent.width()  if parent else widget.width()
    ph = parent.height() if parent else widget.height()
    cur = widget.geometry()
    ww  = cur.width()
    wh  = cur.height()

    if direction == "right":
        end_geom = QRect(pw, cur.y(), ww, wh)
    elif direction == "left":
        end_geom = QRect(-ww, cur.y(), ww, wh)
    else:
        end_geom = QRect(cur.x(), ph, ww, wh)

    geo_anim = QPropertyAnimation(widget, b"geometry")
    geo_anim.setDuration(duration_ms)
    geo_anim.setStartValue(cur)
    geo_anim.setEndValue(end_geom)
    geo_anim.setEasingCurve(QEasingCurve.Type.InCubic)

    if widget.graphicsEffect() is None:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    else:
        effect = widget.graphicsEffect()

    op_anim = QPropertyAnimation(effect, b"opacity")
    op_anim.setDuration(duration_ms)
    op_anim.setStartValue(1.0)
    op_anim.setEndValue(0.0)
    op_anim.setEasingCurve(QEasingCurve.Type.InQuad)

    group = QParallelAnimationGroup()
    group.addAnimation(geo_anim)
    group.addAnimation(op_anim)

    def _finish():
        if hide_after:
            widget.hide()
        if on_done:
            on_done()

    group.finished.connect(_finish)
    group.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return group
