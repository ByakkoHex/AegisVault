"""
hex_background.py - Tło hexagonalne dla AegisVault
====================================================
Dwa mechanizmy:

1. HexBackground(parent) — osobny tk.Canvas umieszczany na ramce.
   Działa tam gdzie parent ma widoczną pustą przestrzeń (okno logowania).

2. apply_hex_to_canvas(canvas) — rysuje hex BEZPOŚREDNIO na istniejącym
   canvas (np. CTkScrollableFrame._parent_canvas). Jedyny sposób na widoczne
   tło w obszarach przykrytych przez CTkFrame (które malują nieprzezroczyste tło).

Tryby glow (glow_mode):
  "breath" — ~2s glow, symetryczny sin-wave, kolor akcentu motywu
  "fire"   — ~1.5-2s glow, szybkie zapalenie + wolne gaśnięcie, więcej komórek
"""

import tkinter as tk
import customtkinter as ctk
import math
import random
import functools

from utils.prefs_manager import PrefsManager

# ── Kolory tła i siatki ───────────────────────────────────────────────
_DARK_BG   = "#1a1a1a"
_DARK_HEX  = "#2e2e2e"
_LIGHT_BG  = "#f5f5f5"
_LIGHT_HEX = "#ebebeb"

_DARK_GLOW_FB  = "#3a5288"   # fallback gdy accent niedostępny
_LIGHT_GLOW_FB = "#d8e8fd"

# ── Timing — wspólny dla obu trybów ───────────────────────────────────
#   step_ms × steps = całkowity czas glow
#   40 ms × 50 kroków = 2 000 ms = 2 s  (breath)
#   40 ms × 38-50 kroków = 1.5-2 s      (fire — losowe)
_GLOW_STEP_MS   = 40

_BREATH_STEPS   = 50          # stały dla breath  →  2.0 s
_FIRE_STEPS_MIN = 38          # min dla fire       →  1.5 s
_FIRE_STEPS_MAX = 50          # max dla fire       →  2.0 s

# Jak często zapalać nowy hex
_BREATH_INT_MS  = 800         # co 800 ms nowy hex w breath
_FIRE_INT_MIN   = 150         # min ms między nowymi iskrami (fire)
_FIRE_INT_MAX   = 500         # max ms między nowymi iskrami (fire)

# Ile % hexów może jednocześnie świecić
_BREATH_GLOW_PCT = 0.04       # 4% — subtelne
_FIRE_GLOW_PCT   = 0.09       # 9% — wyraźne


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

@functools.lru_cache(maxsize=512)
def _lerp_hex(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return (f"#{int(r1 + (r2-r1)*t):02x}"
            f"{int(g1 + (g2-g1)*t):02x}"
            f"{int(b1 + (b2-b1)*t):02x}")


def _glow_curve(step: int, steps_total: int, mode: str) -> float:
    """
    Krzywa jasności dla animacji glow.

    breath: symetryczny sin-wave, łagodne wejście i zejście.
    fire:   szybkie zapalenie (30% czasu), wolne gaśnięcie (70% czasu).
    """
    t = step / max(steps_total, 1)
    if mode == "fire":
        if t <= 0.30:
            return math.sin(math.pi / 2 * (t / 0.30))
        else:
            return math.cos(math.pi / 2 * ((t - 0.30) / 0.70))
    else:
        return math.sin(math.pi * t)


def _calc_glow_max(hex_count: int, base: int, mode: str) -> int:
    """Dynamicznie wyznacza max jednoczesnych glow na podstawie rozmiaru siatki."""
    if hex_count == 0:
        return base
    pct = _FIRE_GLOW_PCT if mode == "fire" else _BREATH_GLOW_PCT
    dynamic = int(hex_count * pct)
    return max(base, min(base * 8, dynamic))


@functools.lru_cache(maxsize=512)
def _hex_pts(cx: float, cy: float, size: float) -> tuple:
    """Wierzchołki flat-top hexagonu."""
    pts = []
    for i in range(6):
        a = math.radians(60 * i)
        pts.append(cx + size * math.cos(a))
        pts.append(cy + size * math.sin(a))
    return tuple(pts)


def _get_accent() -> str:
    """Czyta kolor akcentu z PrefsManager."""
    try:
        return PrefsManager().get_accent()
    except Exception:
        return (_DARK_GLOW_FB if ctk.get_appearance_mode() == "Dark"
                else _LIGHT_GLOW_FB)


def _hex_base_col() -> str:
    return _DARK_HEX if ctk.get_appearance_mode() == "Dark" else _LIGHT_HEX


# ══════════════════════════════════════════════════════════════════════
# apply_hex_to_canvas — rysuje hex bezpośrednio na istniejącym canvas
# ══════════════════════════════════════════════════════════════════════

def apply_hex_to_canvas(
    canvas: tk.Canvas,
    hex_size: int = 36,
    glow_max: int = 4,
    glow_interval_ms: int = 800,
    glow_mode: str = "breath",
    hidden_grid: bool = False,
) -> None:
    """
    Rysuje siatkę heksagonów bezpośrednio na podanym canvas.
    Hex items są zawsze poniżej zawartości (tag_lower).
    hidden_grid=True — siatka niewidoczna (outline=tło), tylko glow widoczny.
    """
    TAG   = "_hex"
    # Ensure canvas has no highlight border that could bleed through other widgets.
    try:
        canvas.configure(highlightthickness=0)
    except Exception:
        pass
    state = {
        "hex_ids":  [],
        "centers":  {},          # iid → (cx, cy)
        "glowing":  {},          # iid → steps_total
        "sched_id": None,
        "active":   True,
        "last_wh":  (-1, -1),
        "eff_max":  glow_max,    # aktualizowane po _draw
        "base_col": _hex_base_col(),  # aktualizowane w _draw
    }

    def _alive() -> bool:
        if not state["active"]:
            return False
        try:
            return bool(canvas.winfo_exists())
        except tk.TclError:
            return False

    # ── Scrollregion fix ──────────────────────────────────────────────
    def _fix_scrollregion():
        if not _alive():
            return
        try:
            all_items = canvas.find_all()
            content = [i for i in all_items if TAG not in canvas.gettags(i)]
            vw = max(canvas.winfo_width(),  1)
            vh = max(canvas.winfo_height(), 1)
            if content:
                x1, y1, x2, y2 = canvas.bbox(*content)
                canvas.configure(scrollregion=(
                    0, 0, max(int(x2), vw), max(int(y2), vh),
                ))
            else:
                canvas.configure(scrollregion=(0, 0, vw, vh))
        except Exception:
            pass

    def _bind_inner_frame():
        if not _alive():
            return
        try:
            for item in canvas.find_all():
                if canvas.type(item) == "window":
                    inner = canvas.nametowidget(canvas.itemcget(item, "window"))
                    inner.bind("<Configure>",
                               lambda e: canvas.after(1, _fix_scrollregion),
                               add="+")
        except Exception:
            pass

    # ── Rysowanie ─────────────────────────────────────────────────────
    def _draw(event=None):
        if not _alive():
            return
        try:
            w = canvas.winfo_width()
            h = canvas.winfo_height()
        except tk.TclError:
            return
        if w <= 1 or h <= 1:
            return
        if (w, h) == state["last_wh"]:
            return
        state["last_wh"] = (w, h)

        draw_h = h + hex_size * 4
        canvas.delete(TAG)
        state["hex_ids"].clear()
        state["centers"].clear()
        state["glowing"].clear()

        size     = hex_size
        col_step = size * 1.5
        row_step = size * math.sqrt(3)
        # hidden_grid: outline = bg (niewidoczna siatka, tylko glow świeci)
        bg_col   = canvas.cget("bg")
        hcol     = bg_col if hidden_grid else _hex_base_col()
        state["base_col"] = hcol

        cols = int(w / col_step) + 3
        rows = int(draw_h / row_step) + 3

        for col in range(-1, cols):
            cx    = col * col_step
            y_off = (row_step / 2) if (col % 2) else 0.0
            for row in range(-1, rows):
                cy  = row * row_step + y_off
                iid = canvas.create_polygon(
                    _hex_pts(cx, cy, size - 2),
                    outline=hcol, fill="", width=2, tags=TAG
                )
                state["hex_ids"].append(iid)
                state["centers"][iid] = (cx, cy)

        canvas.tag_lower(TAG)
        canvas.after(1, _fix_scrollregion)

    # ── Animacja glow ─────────────────────────────────────────────────
    def _next_interval() -> int:
        if glow_mode == "fire":
            return random.randint(_FIRE_INT_MIN, _FIRE_INT_MAX)
        return _BREATH_INT_MS

    def _schedule_glow():
        if not state["active"]:
            return
        state["sched_id"] = canvas.after(_next_interval(), _try_glow)

    def _get_visible_ids() -> list:
        """Zwraca ID hexów widocznych w aktualnym viewport canvasa."""
        centers = state["centers"]
        if not centers:
            return state["hex_ids"]
        try:
            yt, yb  = canvas.yview()
            sr      = str(canvas.cget("scrollregion")).split()
            total_h = float(sr[3]) if len(sr) >= 4 else canvas.winfo_height()
            vw      = canvas.winfo_width()
            margin  = hex_size * 2
            # abs_min zapobiega glow na granicy wewnętrznej ramki i pustego viewportu
            abs_min = float(hex_size * 6)
            y_min   = max(abs_min, yt * total_h - margin)
            y_max   = yb * total_h + margin
            return [
                iid for iid, (cx, cy) in centers.items()
                if y_min <= cy <= y_max and -margin <= cx <= vw + margin
            ]
        except Exception:
            return state["hex_ids"]

    def _try_glow():
        if not _alive():
            return
        candidates = _get_visible_ids()
        if candidates:
            pct     = _FIRE_GLOW_PCT if glow_mode == "fire" else _BREATH_GLOW_PCT
            eff_max = max(glow_max, min(glow_max * 8, int(len(candidates) * pct)))
            if len(state["glowing"]) < eff_max:
                calm = [i for i in candidates if i not in state["glowing"]]
                if calm:
                    iid   = random.choice(calm)
                    steps = (random.randint(_FIRE_STEPS_MIN, _FIRE_STEPS_MAX)
                             if glow_mode == "fire" else _BREATH_STEPS)
                    intensity = random.uniform(0.6, 1.0) if glow_mode == "fire" else 1.0
                    state["glowing"][iid] = steps
                    _glow_step(iid, 0, steps, intensity)
        _schedule_glow()

    def _glow_step(iid: int, step: int, steps_total: int, intensity: float):
        if not _alive():
            state["glowing"].pop(iid, None)
            return
        base = state.get("base_col", _hex_base_col())
        t   = _glow_curve(step, steps_total, glow_mode) * intensity
        col = _lerp_hex(base, _get_accent(), t)
        try:
            canvas.itemconfig(iid, outline=col)
        except tk.TclError:
            state["glowing"].pop(iid, None)
            return
        if step < steps_total:
            canvas.after(_GLOW_STEP_MS, lambda: _glow_step(iid, step + 1, steps_total, intensity))
        else:
            try:
                canvas.itemconfig(iid, outline=base)
            except tk.TclError:
                pass
            state["glowing"].pop(iid, None)

    def _on_destroy(event=None):
        state["active"] = False
        if state["sched_id"] is not None:
            try:
                canvas.after_cancel(state["sched_id"])
            except Exception:
                pass
        try:
            ctk.AppearanceModeTracker.remove(_on_appearance_change)
        except Exception:
            pass

    def _on_appearance_change(mode: str) -> None:
        """Wywoływane przez CTk AppearanceModeTracker przy zmianie trybu Dark/Light."""
        if not _alive():
            return
        # Wymuś pełne przerysowanie siatki (reset last_wh) z nowym kolorem tła
        state["last_wh"] = (-1, -1)
        canvas.after_idle(_draw)

    def _stop_animation():
        state["active"] = False
        if state["sched_id"] is not None:
            try:
                canvas.after_cancel(state["sched_id"])
            except Exception:
                pass

    def _update_accent(new_accent: str) -> None:
        """Wymusza przerysowanie siatki z nowym akcentem z PrefsManager."""
        if not _alive():
            return
        # Resetuj last_wh — _draw odczyta świeży kolor z _hex_base_col() / _get_accent()
        state["last_wh"] = (-1, -1)
        canvas.after_idle(_draw)

    # Przypisz update_accent do canvas jako atrybut dla zewnętrznych wywołań.
    canvas._hex_update_accent = _update_accent

    # ── Podpięcie ─────────────────────────────────────────────────────
    canvas.bind("<Configure>", lambda e: _draw(), add="+")
    canvas.bind("<Destroy>",   _on_destroy, add="+")
    canvas.bind("<Destroy>",   lambda e: _stop_animation(), add="+")
    canvas.after(120, _draw)
    canvas.after(120 + _next_interval(), _schedule_glow)
    canvas.after(300, _bind_inner_frame)
    try:
        ctk.AppearanceModeTracker.add(_on_appearance_change, canvas)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════
# HexBackground — osobny widget canvas (okno logowania i podobne)
# ══════════════════════════════════════════════════════════════════════

class HexBackground(tk.Canvas):
    """
    Osobny canvas z siatką heksagonów i animacją glow.

    glow_mode:
        "breath" — ~2s glow, symetryczny sin-wave (domyślne)
        "fire"   — szybkie zapalenie, wolne gaśnięcie, więcej komórek
    hidden_grid:
        True — siatka niewidoczna (outline = tło), widać tylko animowany glow.
               Przydatne gdy hex jest pod widgetami (scroll_frame).
    """

    def __init__(
        self,
        parent,
        hex_size: int = 36,
        animate: bool = True,
        glow_max: int = 4,
        glow_interval_ms: int = 800,
        glow_mode: str = "breath",
        bg_color: str | None = None,
        hidden_grid: bool = False,
        **kw,
    ):
        is_dark = ctk.get_appearance_mode() == "Dark"
        if bg_color is None:
            bg_color = _DARK_BG if is_dark else _LIGHT_BG

        self._hidden_grid = hidden_grid
        # Gdy hidden_grid=True siatka jest niewidoczna — outline = bg, tylko glow widoczny
        self._hex_col_val = bg_color if hidden_grid else (_DARK_HEX if is_dark else _LIGHT_HEX)

        super().__init__(parent, bg=bg_color, highlightthickness=0, bd=0, **kw)

        self._hex_size  = hex_size
        self._animate   = animate
        self._base_max  = glow_max
        self._eff_max   = glow_max   # aktualizowane po _rebuild
        self._glow_int  = glow_interval_ms
        self._glow_mode = glow_mode

        self._hex_ids:     list[int]               = []
        self._hex_centers: dict[int, tuple]        = {}   # iid → (cx, cy)
        self._glowing:     dict[int, int]          = {}   # iid → steps_total
        self._sched_id:    int | None              = None
        self._resize_job:  int | None              = None
        self._last_size:   tuple                   = (-1, -1)
        # Opcjonalne: canvas viewportu (CTkScrollableFrame._parent_canvas).
        # Gdy ustawiony, glow jest losowany tylko spośród widocznych hexów.
        self._viewport_canvas: tk.Canvas | None    = None
        self._safe_y_getter = None         # zachowane dla kompatybilności (nieużywane)
        self._card_regions: list  = []     # [(y_top_excl, y_bot_excl), ...] — regiony kart do wykluczenia z glow

        self.bind("<Configure>", self._on_configure)
        self.bind("<Destroy>", lambda e: self.stop_animation(), add="+")

        # Rejestracja w CTk AppearanceModeTracker — automatyczny rebuild przy zmianie motywu
        try:
            ctk.AppearanceModeTracker.add(self._on_appearance_change, self)
        except Exception:
            pass

    # ── Budowanie siatki ──────────────────────────────────────────────

    def _on_configure(self, event) -> None:
        new = (event.width, event.height)
        if new == self._last_size or new[0] <= 1:
            return
        self._last_size = new
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._do_resize)

    def _do_resize(self) -> None:
        self._resize_job = None
        self._rebuild()

    def _rebuild(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return

        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1 or h <= 1:
            return

        is_dark = ctk.get_appearance_mode() == "Dark"
        # Update canvas background to match current appearance mode.
        # bg is set once in __init__; must be refreshed on dark↔light switch.
        if not self._hidden_grid:
            new_bg = _DARK_BG if is_dark else _LIGHT_BG
            try:
                self.configure(bg=new_bg)
            except tk.TclError:
                pass

        if self._hidden_grid:
            self._hex_col_val = self.cget("bg")
        else:
            self._hex_col_val = _DARK_HEX if is_dark else _LIGHT_HEX

        self.delete("all")
        self._hex_ids.clear()
        self._hex_centers.clear()
        self._glowing.clear()

        size     = self._hex_size
        col_step = size * 1.5
        row_step = size * math.sqrt(3)

        for col in range(-1, int(w / col_step) + 3):
            cx    = col * col_step
            y_off = (row_step / 2) if (col % 2) else 0.0
            for row in range(-1, int(h / row_step) + 3):
                cy  = row * row_step + y_off
                iid = self.create_polygon(
                    _hex_pts(cx, cy, size - 2),
                    outline=self._hex_col_val, fill="", width=2,
                )
                self._hex_ids.append(iid)
                self._hex_centers[iid] = (cx, cy)

        self._eff_max = _calc_glow_max(len(self._hex_ids), self._base_max, self._glow_mode)

        if self._animate and self._hex_ids:
            self._schedule_glow()

    # ── Animacja glow ─────────────────────────────────────────────────

    def _next_interval(self) -> int:
        if self._glow_mode == "fire":
            return random.randint(_FIRE_INT_MIN, _FIRE_INT_MAX)
        return _BREATH_INT_MS

    def _schedule_glow(self) -> None:
        if self._sched_id is not None:
            try:
                self.after_cancel(self._sched_id)
            except Exception:
                pass
        self._sched_id = self.after(self._next_interval(), self._try_glow)

    def _get_visible_hex_ids(self) -> list:
        """
        Zwraca ID hexów widocznych w aktualnym viewport i nie zachodzących na karty.
        Używa _card_regions (cache kart) — precyzyjniejsze niż safe_y.
        """
        if not self._hex_centers or self._viewport_canvas is None:
            return self._hex_ids
        try:
            vc = self._viewport_canvas
            yt, yb = vc.yview()
            sr = str(vc.cget("scrollregion")).split()
            total_h = float(sr[3]) if len(sr) >= 4 else vc.winfo_height()
            vw      = vc.winfo_width()
            margin  = self._hex_size * 2
            y_min   = yt * total_h - margin
            y_max   = yb * total_h + margin

            # Filtr viewport
            candidates = [
                iid for iid, (cx, cy) in self._hex_centers.items()
                if y_min <= cy <= y_max and -margin <= cx <= vw + margin
            ]

            # Filtr kart — wyklucz hexagony zachodzące na dowolną kartę
            regions = self._card_regions
            if regions:
                half = self._hex_size * math.sqrt(3) / 2
                safe = []
                for iid in candidates:
                    cy = self._hex_centers[iid][1]
                    if not any(top < cy + half and bot > cy - half for top, bot in regions):
                        safe.append(iid)
                return safe

            return candidates
        except Exception:
            return self._hex_ids

    def _try_glow(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return

        candidates = self._get_visible_hex_ids()
        if candidates:
            # Eff_max dynamicznie na podstawie liczby widocznych hexów
            pct     = _FIRE_GLOW_PCT if self._glow_mode == "fire" else _BREATH_GLOW_PCT
            eff_max = max(self._base_max,
                          min(self._base_max * 8, int(len(candidates) * pct)))
            if len(self._glowing) < eff_max:
                calm = [i for i in candidates if i not in self._glowing]
                if calm:
                    iid   = random.choice(calm)
                    steps = (random.randint(_FIRE_STEPS_MIN, _FIRE_STEPS_MAX)
                             if self._glow_mode == "fire" else _BREATH_STEPS)
                    intensity = random.uniform(0.6, 1.0) if self._glow_mode == "fire" else 1.0
                    self._glowing[iid] = steps
                    self._glow_step(iid, 0, steps, intensity)
        self._schedule_glow()

    def _glow_step(self, iid: int, step: int, steps_total: int, intensity: float) -> None:
        try:
            if not self.winfo_exists():
                self._glowing.pop(iid, None)
                return
        except tk.TclError:
            self._glowing.pop(iid, None)
            return

        t   = _glow_curve(step, steps_total, self._glow_mode) * intensity
        col = _lerp_hex(self._hex_col_val, _get_accent(), t)
        try:
            self.itemconfig(iid, outline=col)
        except tk.TclError:
            self._glowing.pop(iid, None)
            return

        if step < steps_total:
            self.after(_GLOW_STEP_MS, lambda: self._glow_step(iid, step + 1, steps_total, intensity))
        else:
            try:
                self.itemconfig(iid, outline=self._hex_col_val)
            except tk.TclError:
                pass
            self._glowing.pop(iid, None)

    def _on_appearance_change(self, mode: str) -> None:
        """Wywoływane przez CTk AppearanceModeTracker przy zmianie trybu. Wymusza rebuild."""
        try:
            if self.winfo_exists():
                self._last_size = (-1, -1)
                self.after_idle(self._rebuild)
        except Exception:
            pass

    def update_accent(self, new_accent: str | None = None) -> None:
        """
        Aktualizuje kolor outline hexagonów na żywo po zmianie akcentu.
        new_accent — nowy kolor akcentu (str hex, np. '#4F8EF7').
                     Gdy None, odczytuje z PrefsManager.
        Nie wymaga pełnego rebuild — szybka aktualizacja itemconfig.
        """
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        # Wymuś pełny rebuild żeby od razu odświeżyć grid z nowym akcentem
        self._last_size = (-1, -1)
        self._rebuild()

    def update_theme(self) -> None:
        """
        Wymusza odświeżenie kolorów tła i siatki zgodnie z aktualnym trybem
        (Dark/Light) i kolorem akcentu z PrefsManager.
        Wywołaj po programowej zmianie motywu (apply_theme w main_window).
        """
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self._last_size = (-1, -1)
        self._rebuild()

    def stop_animation(self) -> None:
        """Zatrzymuje animację glow. Bezpieczne do wywołania w <Destroy>."""
        self._animate = False
        if self._sched_id is not None:
            try:
                self.after_cancel(self._sched_id)
            except Exception:
                pass
            self._sched_id = None

    def destroy(self) -> None:
        self.stop_animation()
        self._glowing.clear()
        self._hex_centers.clear()
        try:
            ctk.AppearanceModeTracker.remove(self._on_appearance_change)
        except Exception:
            pass
        try:
            super().destroy()
        except tk.TclError:
            pass


# ══════════════════════════════════════════════════════════════════════
# HexOverlay — hex canvas PONAD widgetami (Win32 colorkey transparency)
# ══════════════════════════════════════════════════════════════════════

# Kolor tła nakładki — staje się przezroczysty via Win32 colorkey.
# Musi być kolorem NIEUŻYWANYM przez UI (nie akcent, nie tło, nie teksty).
_OVERLAY_BG      = "#010203"
_OVERLAY_COLORREF = 0x030201   # Win32 COLORREF: 0x00BBGGRR → B=3,G=2,R=1


class HexOverlay(HexBackground):
    """
    Transparentna nakładka z hexagonami rysowana PONAD wszystkimi widgetami.

    Technika: Win32 WS_EX_LAYERED + LWA_COLORKEY usuwa kolor #010203 z canvas,
    czyniąc tło przezroczystym — widać przez nie karty/widgety poniżej.
    Hex outlines rysowane są innymi kolorami (akcent, szary) i pozostają widoczne.
    WS_EX_TRANSPARENT sprawia, że kliknięcia myszą przechodzą do widgetów pod spodem.

    Wymagania: Windows 8+ (WS_EX_LAYERED na child windows).
    """

    def __init__(self, parent, **kw):
        kw["bg_color"] = _OVERLAY_BG
        super().__init__(parent, **kw)
        self.after(80, self._apply_win32_transparency)

    # ── _rebuild: overlay — polygony bazowo niewidoczne (colorkey) ────────
    def _rebuild(self) -> None:
        super()._rebuild()
        # Ograniczamy do base_max (nie skalujemy PCT — overlay jest viewport-sized).
        self._eff_max = self._base_max
        # Bazowy kolor = _OVERLAY_BG = colorkey Win32 → polygon staje się
        # przezroczysty (transparentny). Widoczny TYLKO podczas glow (accent).
        self._hex_col_val = _OVERLAY_BG
        try:
            for iid in self._hex_ids:
                # fill + outline = colorkey → oba przezroczyste
                self.itemconfig(iid, outline=_OVERLAY_BG, fill=_OVERLAY_BG)
        except Exception:
            pass

    # ── _glow_step: zmienia fill I outline (widoczny wypełniony hex) ──────
    def _glow_step(self, iid: int, step: int, steps_total: int, intensity: float) -> None:
        try:
            if not self.winfo_exists():
                self._glowing.pop(iid, None)
                return
        except tk.TclError:
            self._glowing.pop(iid, None)
            return

        t   = _glow_curve(step, steps_total, self._glow_mode) * intensity
        col = _lerp_hex(_OVERLAY_BG, _get_accent(), t)
        try:
            # Wypełniony hex pojawia się jako accent-kolor ponad kartami
            self.itemconfig(iid, outline=col, fill=col)
        except tk.TclError:
            self._glowing.pop(iid, None)
            return

        if step < steps_total:
            self.after(_GLOW_STEP_MS, lambda: self._glow_step(iid, step + 1, steps_total, intensity))
        else:
            try:
                # Powrót do przezroczystości (colorkey)
                self.itemconfig(iid, outline=_OVERLAY_BG, fill=_OVERLAY_BG)
            except tk.TclError:
                pass
            self._glowing.pop(iid, None)

    # ── _try_glow: normalna intensywność (hex jest tylko podczas glow) ────
    def _try_glow(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if self._hex_ids and len(self._glowing) < self._eff_max:
            calm = [i for i in self._hex_ids if i not in self._glowing]
            if calm:
                iid = random.choice(calm)
                steps = (random.randint(_FIRE_STEPS_MIN, _FIRE_STEPS_MAX)
                         if self._glow_mode == "fire" else _BREATH_STEPS)
                intensity = random.uniform(0.65, 1.0)
                self._glowing[iid] = steps
                self._glow_step(iid, 0, steps, intensity)
        self._schedule_glow()

    def _apply_win32_transparency(self) -> None:
        try:
            import ctypes
            hwnd = self.winfo_id()
            GWL_EXSTYLE       = -20
            WS_EX_LAYERED     = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            LWA_COLORKEY      = 0x00000001

            ex = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT
            )
            ctypes.windll.user32.SetLayeredWindowAttributes(
                hwnd, _OVERLAY_COLORREF, 255, LWA_COLORKEY
            )
        except Exception:
            pass


def apply_hex_overlay(
    container,
    over_widget,
    hex_size: int = 36,
    glow_max: int = 3,
    glow_interval_ms: int = 1400,
    glow_mode: str = "fire",
) -> "HexOverlay":
    """
    Tworzy HexOverlay i pozycjonuje go DOKŁADNIE nad `over_widget`.
    `container` to rodzic `over_widget` (widget, w którym over_widget jest spakowany).

    Hex jest widoczny PONAD kartami/widgetami bez przycinania.
    Kliknięcia przechodzą przez overlay do widgetów poniżej.
    """
    overlay = HexOverlay(
        container,
        hex_size=hex_size,
        animate=True,
        glow_max=glow_max,
        glow_interval_ms=glow_interval_ms,
        glow_mode=glow_mode,
    )

    def _reposition(event=None):
        try:
            x = over_widget.winfo_x()
            y = over_widget.winfo_y()
            w = over_widget.winfo_width()
            h = over_widget.winfo_height()
            if w > 1 and h > 1:
                overlay.place(x=x, y=y, width=w, height=h)
                overlay.lift()   # zostaje na wierzchu z-order
        except Exception:
            pass

    over_widget.bind("<Configure>", _reposition, add="+")
    container.after(300, _reposition)   # pierwsze pozycjonowanie po layout-resolve
    return overlay


# ══════════════════════════════════════════════════════════════════════
# apply_hex_to_scrollable — hex wewnątrz CTkScrollableFrame
# ══════════════════════════════════════════════════════════════════════

def apply_hex_to_scrollable(
    scroll_frame,
    hex_size: int = 36,
    glow_max: int = 4,
    glow_interval_ms: int = 800,
    glow_mode: str = "breath",
) -> "HexBackground":
    """
    Umieszcza HexBackground wewnątrz CTkScrollableFrame (widoczny między wierszami)
    ORAZ rysuje hex bezpośrednio na _parent_canvas (widoczny w pustym viewport
    poniżej treści). Dual-layer — razem pokrywają cały obszar bez przerw.
    """
    is_dark = ctk.get_appearance_mode() == "Dark"
    try:
        bg_color = scroll_frame._parent_canvas.cget("bg")
    except Exception:
        bg_color = _DARK_BG if is_dark else _LIGHT_BG

    # Warstwa 1 — wewnątrz scroll_frame (między kartami / wierszami treści)
    hex_bg = HexBackground(
        scroll_frame,
        hex_size=hex_size,
        animate=True,
        glow_max=glow_max,
        glow_interval_ms=glow_interval_ms,
        glow_mode=glow_mode,
        bg_color=bg_color,
    )
    hex_bg.place(x=0, y=0, relwidth=1.0, relheight=1.0)
    try:
        hex_bg.lower()
    except Exception:
        try:
            scroll_frame.tk.call("lower", hex_bg._w)
        except Exception:
            pass

    # Podłącz viewport canvas — _try_glow będzie losować tylko z widocznych hexów
    try:
        hex_bg._viewport_canvas = scroll_frame._parent_canvas
    except Exception:
        pass

    # Opcja 11: cache regionów kart odświeżany przez <Configure> wewnętrznej ramki.
    # Precyzyjniejsze niż safe_y — wyklucza dokładnie te hexagony które zachodzą na kartę.
    def _refresh_card_regions(event=None):
        try:
            # CTkScrollableFrame itself IS the inner scrollable frame —
            # there is no separate _scrollable_frame attribute.
            inner = scroll_frame
            half  = hex_size * math.sqrt(3) / 2
            regions = []
            for c in inner.winfo_children():
                if isinstance(c, HexBackground):
                    continue
                h = c.winfo_height()
                y = c.winfo_y()
                if h < 10 or y < 0:
                    continue
                regions.append((float(y - half), float(y + h + half)))
            hex_bg._card_regions = regions
        except Exception:
            pass

    try:
        scroll_frame.bind("<Configure>", _refresh_card_regions, add="+")
    except Exception:
        pass
    # Inicjalne wypełnienie po wyrenderowaniu (2 próby — animacja kart może opóźniać winfo_height)
    hex_bg.after(300, _refresh_card_regions)
    hex_bg.after(900, _refresh_card_regions)
    # Referencja dla zewnętrznych wywołań (np. po przeładowaniu listy haseł)
    hex_bg._refresh_card_regions = _refresh_card_regions

    # Warstwa 2 — na _parent_canvas (pusty viewport poniżej treści)
    try:
        apply_hex_to_canvas(
            scroll_frame._parent_canvas,
            hex_size=hex_size,
            glow_max=glow_max,
            glow_interval_ms=glow_interval_ms,
            glow_mode=glow_mode,
        )
    except Exception:
        pass

    return hex_bg


# ══════════════════════════════════════════════════════════════════════
# apply_hex_to_window — hex jako tło całego okna CTk/CTkToplevel
# ══════════════════════════════════════════════════════════════════════

def apply_hex_to_window(
    window,
    hex_size: int = 36,
    glow_max: int = 3,
    glow_interval_ms: int = 800,
    glow_mode: str = "breath",
) -> "HexBackground":
    """
    Umieszcza HexBackground jako tło całego okna (CTk lub CTkToplevel).
    """
    is_dark  = ctk.get_appearance_mode() == "Dark"
    bg_color = _DARK_BG if is_dark else _LIGHT_BG
    hex_bg = HexBackground(
        window,
        hex_size=hex_size,
        animate=True,
        glow_max=glow_max,
        glow_interval_ms=glow_interval_ms,
        glow_mode=glow_mode,
        bg_color=bg_color,
    )
    # Overhang = hex_size // 2 — canvas wychodzi poza krawędź okna, dzięki czemu
    # wzorzec hexów jest kompletny przy każdym brzegu (żaden hex nie jest przycinany
    # dokładnie na granicy widocznego obszaru).
    oh = hex_size // 2
    hex_bg.place(x=-oh, y=-oh, relwidth=1.0, width=oh * 2, relheight=1.0, height=oh * 2)
    try:
        window.tk.call("lower", hex_bg._w)
    except Exception:
        pass
    return hex_bg
