"""
gradient.py — GradientCanvas + AnimatedGradientCanvas

GradientCanvas        — statyczny gradient między dwoma kolorami.
AnimatedGradientCanvas — gradient z animacją (bez migotania — itemconfig zamiast delete/recreate):
    anim_mode="breathe" — alpha akcentu tętni sinusoidalnie (ambient glow)
    anim_mode="slide"   — pasmo akcentu przesuwa się wzdłuż gradientu (niebieski→czarny→niebieski...)
    anim_mode="sweep"   — gaussowski rozbłysk przesuwa się wzdłuż gradientu (shimmer)

Użycie:
    from gui.gradient import GradientCanvas, AnimatedGradientCanvas

    # Statyczny
    g = GradientCanvas(parent, color_from="#4F8EF7", color_to="#1a1a1a", direction="h")
    g.pack(fill="x")

    # Animowany — pasek separatora
    ag = AnimatedGradientCanvas(parent, accent="#4F8EF7", base="#1a1a1a",
                                anim_mode="slide", n_bands=1,
                                direction="h", steps=96, height=2)
    ag.pack(fill="x")
    ag.start_animation()

    # Animowany — ambient tło (oddycha)
    ag2 = AnimatedGradientCanvas(parent, accent="#4F8EF7", base="#1a1a1a",
                                 anim_mode="breathe", alpha_min=0.04, alpha_max=0.14,
                                 direction="v", steps=48, height=80)
    ag2.pack(fill="x")
    ag2.start_animation()

    # Przy zamknięciu okna:
    ag.stop_animation()
    # Przy zmianie motywu:
    ag.update_accent(new_accent, new_base)
"""

import tkinter as tk
import math

# Zestaw "bezpiecznych" kolorów — CTK/tk może zwracać nazwy zamiast hex
_NAMED = {
    "black": "#000000", "white": "#ffffff",
    "red": "#ff0000", "green": "#008000", "blue": "#0000ff",
    "gray": "#808080", "grey": "#808080",
    "systemButtonFace": "#f0f0f0",
}


def _resolve(widget: tk.Misc, color: str) -> str:
    """Zamienia dowolny kolor tk (nazwę lub hex) na #rrggbb."""
    color = color.strip()
    if color.startswith("#") and len(color) == 7:
        return color
    try:
        r, g, b = widget.winfo_rgb(color)
        return f"#{r >> 8:02x}{g >> 8:02x}{b >> 8:02x}"
    except tk.TclError:
        return _NAMED.get(color.lower(), "#1a1a1a")


def _hex_lerp(c1: str, c2: str, t: float) -> str:
    """Interpolacja liniowa (lerp) między dwoma kolorami hex (#rrggbb)."""
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


class GradientCanvas(tk.Canvas):
    """Canvas rysujący płynny gradient między color_from a color_to.

    Parametry:
        color_from  — kolor startowy (hex #rrggbb)
        color_to    — kolor końcowy  (hex #rrggbb)
        direction   — "h" poziomy (lewo→prawo) | "v" pionowy (góra→dół)
        steps       — liczba pasków (64 = płynny, 32 = szybszy)

    Metody:
        update_colors(color_from, color_to) — zmień kolory i przerysuj
        set_overlay_text(text, fill, font)  — tekst na środku gradientu
    """

    def __init__(
        self,
        parent,
        color_from: str,
        color_to: str,
        direction: str = "h",
        steps: int = 64,
        **kw,
    ):
        # Ustaw bg natychmiast — bez tego tkinter pokazuje systemowy kolor
        # (ciemny na Win11) zanim _on_configure zdąży ustawić właściwy
        _initial_bg = color_to if (color_to.startswith("#") and len(color_to) == 7) else "#f5f5f5"
        super().__init__(parent, highlightthickness=0, borderwidth=0, bg=_initial_bg, **kw)
        self._c1    = color_from
        self._c2    = color_to
        self._dir   = direction
        self._steps = steps

        self._text: str       = ""
        self._text_fill: str  = "#ffffff"
        self._text_font: tuple = ("Segoe UI", 11)

        # Pre-alokowane itemy canvas (brak delete/recreate → brak migotania)
        self._rect_ids: list  = []
        self._text_id         = None
        self._last_size: tuple = (-1, -1)

        self.bind("<Configure>", self._on_configure)

    # ── Inicjalizacja przy pierwszym wyświetleniu ──────────────────────────

    def _on_configure(self, event=None) -> None:
        c1 = _resolve(self, self._c1)
        c2 = _resolve(self, self._c2)
        self._c1 = c1
        self._c2 = c2
        self.configure(bg=c2)
        self.unbind("<Configure>")
        self.bind("<Configure>", self._redraw)
        self._redraw()

    # ── Rysowanie bez migotania ────────────────────────────────────────────

    def _redraw(self, _=None) -> None:
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return

        steps = self._steps

        # Stwórz itemy przy pierwszym rysowaniu (tylko raz przez życie widgetu)
        if not self._rect_ids:
            self._rect_ids = [
                self.create_rectangle(0, 0, 1, 1, outline="")
                for _ in range(steps)
            ]
            self._last_size = (-1, -1)   # wymuś aktualizację coords
            # Tekst musi być nad prostokątami
            if self._text_id:
                self.tag_raise(self._text_id)

        # Zaktualizuj współrzędne tylko gdy rozmiar się zmienił
        if (w, h) != self._last_size:
            for i in range(steps):
                if self._dir == "h":
                    x0 = round(i * w / steps)
                    x1 = round((i + 1) * w / steps)
                    self.coords(self._rect_ids[i], x0, 0, x1, h)
                else:
                    y0 = round(i * h / steps)
                    y1 = round((i + 1) * h / steps)
                    self.coords(self._rect_ids[i], 0, y0, w, y1)
            self._last_size = (w, h)
            if self._text_id:
                self.coords(self._text_id, w // 2, h // 2)
                self.tag_raise(self._text_id)

        # Zaktualizuj kolory
        for i in range(steps):
            t = i / max(steps - 1, 1)
            self.itemconfig(self._rect_ids[i], fill=_hex_lerp(self._c1, self._c2, t))

        # Stwórz tekst jeśli potrzebny i jeszcze nie istnieje
        if self._text and not self._text_id:
            self._text_id = self.create_text(
                w // 2, h // 2,
                text=self._text, fill=self._text_fill,
                font=self._text_font, anchor="center",
            )

    # ── API publiczne ──────────────────────────────────────────────────────

    def set_overlay_text(
        self,
        text: str,
        fill: str = "#ffffff",
        font: tuple | None = None,
    ) -> None:
        self._text      = text
        self._text_fill = fill
        self._text_font = font or ("Segoe UI", 11)
        if self._text_id:
            self.delete(self._text_id)
            self._text_id = None
        self._redraw()

    def update_colors(
        self,
        color_from: str | None = None,
        color_to: str | None = None,
    ) -> None:
        """Zmień jeden lub oba kolory gradientu i przerysuj."""
        if color_from is not None:
            self._c1 = _resolve(self, color_from)
        if color_to is not None:
            self._c2 = _resolve(self, color_to)
            self.configure(bg=self._c2)
        self._redraw()


# ─────────────────────────────────────────────────────────────────────────────
# AnimatedGradientCanvas
# ─────────────────────────────────────────────────────────────────────────────

class AnimatedGradientCanvas(GradientCanvas):
    """GradientCanvas z animacją — bez migotania (itemconfig zamiast delete/recreate).

    anim_mode="breathe"  — kolor akcentu tętni sinusoidalnie (ambient glow).
    anim_mode="slide"    — pasmo akcentu przesuwa się wzdłuż gradientu.
                           Efekt: niebieski → czarny → niebieski → czarny...
    anim_mode="sweep"    — gaussowski rozbłysk akcentu przesuwa się wzdłuż gradientu.

    Parametry konstruktora:
        accent      — czysty kolor akcentu (#rrggbb)
        base        — kolor tła/bazy (#rrggbb)
        anim_mode   — "breathe" | "slide" | "sweep"
        alpha_min   — minimalna intensywność akcentu (0.0–1.0, tylko breathe)
        alpha_max   — maksymalna intensywność akcentu (0.0–1.0, tylko breathe)
        period_ms   — czas jednego pełnego cyklu animacji w milisekundach
        fps         — liczba klatek animacji na sekundę
        n_bands     — liczba pasm slide/sweep widocznych jednocześnie (domyślnie 1)
        direction, steps, **kw — przekazywane do GradientCanvas
    """

    def __init__(
        self,
        parent,
        accent: str,
        base: str,
        anim_mode: str = "breathe",
        alpha_min: float = 0.05,
        alpha_max: float = 0.15,
        period_ms: int = 4000,
        fps: int = 15,
        n_bands: int = 1,
        reverse: bool = False,
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
        self._anim_id    = None
        self._paused     = False

        mid = (alpha_min + alpha_max) / 2
        if reverse:
            # Dla odwróconego trybu: c1=base (ciemny start), c2=accent-tinted (jasny koniec)
            c_from = base
            c_to   = _hex_lerp(base, accent, mid)
            super().__init__(parent, color_from=c_from, color_to=c_to, **kw)
        else:
            c_from = _hex_lerp(base, accent, mid)
            super().__init__(parent, color_from=c_from, color_to=base, **kw)

        # Auto-pause przy minimalizacji okna (add="+" — nie nadpisuje istniejących bindingów)
        root = self.winfo_toplevel()
        root.bind("<Unmap>", lambda e: self.pause() if e.widget is root else None, add="+")
        root.bind("<Map>", lambda e: self.resume() if e.widget is root else None, add="+")

    # ── Publiczne API ─────────────────────────────────────────────────────────

    def start_animation(self) -> None:
        """Uruchamia animację (idempotentne — wielokrotne wywołanie jest bezpieczne)."""
        if self._anim_id is None:
            self._tick()

    def stop_animation(self) -> None:
        """Zatrzymuje animację i anuluje zaplanowane wywołania after()."""
        if self._anim_id is not None:
            try:
                self.after_cancel(self._anim_id)
            except tk.TclError:
                pass
            self._anim_id = None

    def destroy(self) -> None:
        """Zatrzymuje animację przed zniszczeniem widgetu — zapobiega błędom 'invalid command'."""
        self._paused = True    # blokuj resume() przez binding <Map>
        self.stop_animation()  # anuluj pending after() zanim widget zniknie
        try:
            super().destroy()
        except tk.TclError:
            pass

    def pause(self) -> None:
        """Wstrzymuje animację i zapamiętuje stan (do wznowienia przez resume())."""
        if not self._paused:
            self._paused = True
            self.stop_animation()

    def resume(self) -> None:
        """Wznawia animację jeśli była wstrzymana przez pause()."""
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if self._paused:
            self._paused = False
            self.start_animation()

    def update_accent(self, accent: str, base: str) -> None:
        """Aktualizuje kolory akcentu i bazy przy zmianie motywu."""
        self._accent_hex = accent
        self._base_hex   = base
        self._c2         = base
        self.configure(bg=base)

    # ── Wewnętrzna pętla animacji ─────────────────────────────────────────────

    def _tick(self) -> None:
        # Guard: widget mógł zostać zniszczony zanim after() zdążył odpalić
        try:
            if not self.winfo_exists():
                self._anim_id = None
                return
        except tk.TclError:
            self._anim_id = None
            return

        dt = (2 * math.pi) / (self._period_ms / (1000.0 / self._fps))
        self._phase = (self._phase + dt) % (2 * math.pi)

        if self._anim_mode == "breathe":
            self._tick_breathe()
        elif self._anim_mode == "slide":
            self._tick_slide()
        else:  # "sweep"
            self._tick_sweep()

        interval = max(16, 1000 // self._fps)
        self._anim_id = self.after(interval, self._tick)

    def _tick_breathe(self) -> None:
        """Animacja oddychania: intensywność akcentu tętni sinusoidalnie.
        Używa itemconfig — zero migotania nawet przy wysokim fps.
        reverse=False: c1 (start) animowany, c2 (koniec) = base  (glow na początku)
        reverse=True:  c1 (start) = base,    c2 (koniec) animowany (glow na końcu — efekt płomienia)
        """
        alpha = self._alpha_min + (self._alpha_max - self._alpha_min) * (
            0.5 + 0.5 * math.sin(self._phase)
        )
        if self._reverse:
            self._c1 = self._base_hex
            self._c2 = _hex_lerp(self._base_hex, self._accent_hex, alpha)
            self.configure(bg=self._c2)
        else:
            self._c1 = _hex_lerp(self._base_hex, self._accent_hex, alpha)
        self._redraw()

    def _tick_slide(self) -> None:
        """Animacja slide: pasmo akcentu przesuwa się od lewej do prawej (lub góry do dołu).
        Efekt: niebieski → czarny → niebieski przesuwa się cyklicznie.
        n_bands kontroluje ile pasm jest widocznych jednocześnie."""
        # Upewnij się że itemy istnieją i mają aktualne coords
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return
        if not self._rect_ids or (w, h) != self._last_size:
            self._redraw()   # inicjalizuje/aktualizuje itemy i coords
            if not self._rect_ids:
                return

        slide = self._phase / (2 * math.pi)   # 0.0 → 1.0 przez cały cykl

        for i in range(self._steps):
            t = i / max(self._steps - 1, 1)
            if self._reverse:
                t = 1.0 - t   # odwróć kierunek przemieszczania
            # Przesuń pozycję o slide (zawinięcie modulo → pętla bez skoku)
            t_shifted = (t - slide) % 1.0
            # Sinusoidalne pasma: pełen cykl accent→base→accent co 1/n_bands
            wave = 0.5 + 0.5 * math.sin(t_shifted * self._n_bands * 2 * math.pi)
            self.itemconfig(self._rect_ids[i],
                            fill=_hex_lerp(self._base_hex, self._accent_hex, wave))

    def _tick_sweep(self) -> None:
        """Animacja sweep: gaussowski rozbłysk akcentu przesuwa się wzdłuż gradientu."""
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return
        if not self._rect_ids or (w, h) != self._last_size:
            self._redraw()
            if not self._rect_ids:
                return

        sweep_pos = self._phase / (2 * math.pi)
        sigma_sq  = 2 * 0.09 * 0.09   # szerokość rozbłysku = 9% długości paska

        for i in range(self._steps):
            t = i / max(self._steps - 1, 1)
            if self._reverse:
                t = 1.0 - t
            base_color = _hex_lerp(self._accent_hex, self._base_hex, t)
            dist = abs(t - sweep_pos)
            if dist > 0.5:
                dist = 1.0 - dist
            glow  = math.exp(-(dist * dist) / sigma_sq)
            final = _hex_lerp(base_color, self._accent_hex, glow * 0.55)
            self.itemconfig(self._rect_ids[i], fill=final)
