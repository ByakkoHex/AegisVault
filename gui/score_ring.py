"""
score_ring.py — Animowany wskaźnik bezpieczeństwa (kołowy pasek postępu)
========================================================================
Wyświetla wynik bezpieczeństwa jako wypełniony łuk z animacją:
- Łuk rysuje się od 0 do docelowej wartości przy każdej aktualizacji (animate_to)
- Pulsuje subtelnie (kolor łuku lekko jaśnieje/ciemnieje)
- Kolor: czerwony (<40), pomarańczowy (40–69), zielony (≥70)
"""

import tkinter as tk
import math


# Paleta kolorów łuku wg progu bezpieczeństwa
_ARC_COLORS = {
    "low":    "#e05252",   # czerwony
    "medium": "#f0a500",   # pomarańczowy
    "high":   "#4caf50",   # zielony
}

_ARC_DARK_TRACK  = "#2e2e2e"   # kolor "toru" łuku — dark mode
_ARC_LIGHT_TRACK = "#e0e0e0"   # kolor "toru" łuku — light mode


def _hex_lerp(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    r1,g1,b1 = int(c1[1:3],16), int(c1[3:5],16), int(c1[5:7],16)
    r2,g2,b2 = int(c2[1:3],16), int(c2[3:5],16), int(c2[5:7],16)
    return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"


def _gradient_arc_color(t: float) -> str:
    """Zwraca kolor gradientu dla pozycji t ∈ [0,1]:
    t=0.0 → #e05252 (czerwony), t=0.5 → #f0a500 (pomarańczowy), t=1.0 → #4caf50 (zielony).
    """
    t = max(0.0, min(1.0, t))
    if t <= 0.5:
        return _hex_lerp("#e05252", "#f0a500", t / 0.5)
    else:
        return _hex_lerp("#f0a500", "#4caf50", (t - 0.5) / 0.5)


class AnimatedScoreRing(tk.Canvas):
    """
    Kołowy wskaźnik postępu z animacją.

    Użycie:
        ring = AnimatedScoreRing(parent, size=44, bg_color="#1a1a1a")
        ring.pack(side="right", padx=8)
        ring.animate_to(85)   # animuje łuk do 85%
        ring.start_pulse()    # uruchamia subtelne pulsowanie
        ring.stop_pulse()     # zatrzymuje (przy zamknięciu okna)
    """

    def __init__(self, parent, size: int = 44, bg_color: str = "#1a1a1a",
                 is_dark: bool = True, **kw):
        super().__init__(
            parent,
            width=size, height=size,
            bg=bg_color,
            highlightthickness=0, borderwidth=0,
            cursor="hand2",
            **kw,
        )
        self._size       = size
        self._bg_color   = bg_color
        self._is_dark    = is_dark
        self._score      = 0
        self._displayed  = 0.0    # aktualnie wyświetlany kąt łuku (dla animacji)
        self._target     = 0.0    # docelowy kąt łuku
        self._arc_color  = _ARC_COLORS["low"]
        self._pulse_phase = 0.0
        self._pulse_id   = None
        self._anim_id    = None
        self._draw()

    # ── API publiczne ──────────────────────────────────────────────────────

    def animate_to(self, score: int) -> None:
        """Animuje łuk od aktualnej pozycji do nowej wartości score (0-100)."""
        self._score  = max(0, min(100, score))
        self._target = self._score / 100.0 * 359.9   # max 359.9° (pełne koło)
        self._arc_color = self._score_to_color(self._score)
        self._animate_arc()

    def start_pulse(self) -> None:
        """Uruchamia subtelne pulsowanie łuku."""
        if self._pulse_id is None:
            self._pulse_tick()

    def stop_pulse(self) -> None:
        """Zatrzymuje pulsowanie."""
        if self._pulse_id is not None:
            try:
                self.after_cancel(self._pulse_id)
            except Exception:
                pass
            self._pulse_id = None
        if self._anim_id is not None:
            try:
                self.after_cancel(self._anim_id)
            except Exception:
                pass
            self._anim_id = None

    def set_bg(self, bg_color: str, is_dark: bool = True) -> None:
        """Aktualizuje kolor tła (przy zmianie motywu)."""
        self._bg_color = bg_color
        self._is_dark  = is_dark
        self.configure(bg=bg_color)
        self._draw()

    # ── Wewnętrzna logika ──────────────────────────────────────────────────

    def _score_to_color(self, score: int) -> str:
        if score >= 70:
            return _ARC_COLORS["high"]
        elif score >= 40:
            return _ARC_COLORS["medium"]
        return _ARC_COLORS["low"]

    def _animate_arc(self) -> None:
        """Płynna animacja łuku do _target."""
        if self._anim_id is not None:
            try:
                self.after_cancel(self._anim_id)
            except Exception:
                pass
        self._step_arc()

    def _step_arc(self) -> None:
        diff = self._target - self._displayed
        if abs(diff) < 0.5:
            self._displayed = self._target
            self._draw()
            return
        # Easing: 18% kroku na klatkę
        self._displayed += diff * 0.18
        self._draw()
        self._anim_id = self.after(16, self._step_arc)  # ~60fps dla płynności

    def _pulse_tick(self) -> None:
        self._pulse_phase = (self._pulse_phase + 0.04) % (2 * math.pi)
        self._draw()
        self._pulse_id = self.after(50, self._pulse_tick)  # 20fps wystarczy

    def _draw(self) -> None:
        self.delete("all")
        s    = self._size
        pad  = 4
        x0, y0, x1, y1 = pad, pad, s - pad, s - pad
        width = max(3, s // 9)   # grubość łuku ~ proporcjonalna do rozmiaru

        # Pulsowanie: lekkie rozjaśnienie koloru łuku
        pulse = 0.12 * math.sin(self._pulse_phase) if self._pulse_id else 0

        # Tor (szare tło łuku)
        track = _ARC_DARK_TRACK if self._is_dark else _ARC_LIGHT_TRACK
        self.create_arc(
            x0, y0, x1, y1,
            start=90, extent=-359.9,
            style="arc", outline=track, width=width,
        )

        # Łuk postępu — N segmentów z gradientem czerwony→pomarańczowy→zielony
        if self._displayed > 0.5:
            N = 60
            seg_angle = 359.9 / N
            for i in range(N):
                seg_start_angle = i * seg_angle
                # Rysuj segment tylko jeśli jego środek mieści się w wyświetlanym kącie
                if (i + 0.5) * seg_angle <= self._displayed + 0.01:
                    seg_color = _gradient_arc_color(i / N)
                    seg_color = _hex_lerp(seg_color, "#ffffff", max(0, pulse))
                    # Ostatni (częściowy) segment może mieć mniejszy extent
                    extent = min(seg_angle, self._displayed - seg_start_angle)
                    if extent <= 0:
                        break
                    self.create_arc(
                        x0, y0, x1, y1,
                        start=90 - seg_start_angle,
                        extent=-extent,
                        style="arc", outline=seg_color, width=width,
                    )

        # Tekst — wynik w centrum
        cx, cy = s // 2, s // 2
        score_str = str(self._score) if self._score > 0 else "--"
        font_size = max(7, s // 5)
        text_color = _hex_lerp(
            _gradient_arc_color(self._score / 100), "#ffffff", max(0, pulse)
        ) if self._score > 0 else ("#555" if self._is_dark else "#aaa")
        self.create_text(
            cx, cy,
            text=score_str,
            fill=text_color,
            font=("Segoe UI", font_size, "bold"),
            anchor="center",
        )
