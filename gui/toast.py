"""
toast.py - Niemodalne powiadomienia (toasty) dla AegisVault
============================================================
Małe popupy w prawym dolnym rogu okna, które same znikają.
Nie blokują aplikacji — w przeciwieństwie do show_error/show_info.

Użycie:
    toast = ToastManager(root_window)
    toast.show("Skopiowano do schowka!", "success")
    toast.show("Błąd połączenia", "error", duration_ms=4000)

Fix Windows glitch:
    NIE używamy withdraw()/deiconify() z overrideredirect — to powoduje
    migotanie i wpis w pasku zadań. Zamiast tego: alpha=0 od startu,
    geometry ustawiona PRZED deiconify (tu: geometry off-screen),
    potem przesunięcie + fade-in.
"""

import tkinter as tk
import customtkinter as ctk

from utils.easing import ease_out_cubic as _ease_out, ease_in_cubic as _ease_in

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
    "info":    "#0F52BA",
}

_TOAST_W   = 320
_TOAST_H   = 60
_MARGIN    = 18
_SLIDE_PX  = 15   # ile pikseli przesuwa się podczas slide-up z dołu

# Parametry animacji show (slide-up + fade-in)
_IN_MS    = 150   # czas trwania animacji show
_IN_STEPS = 10    # liczba kroków

# Parametry animacji dismiss (slide-down + fade-out)
_OUT_MS    = 120
_OUT_STEPS = 8


class _Toast(tk.Toplevel):
    """Pojedynczy toast.

    Używa tk.Toplevel + overrideredirect(True).
    Aby uniknąć glitcha na Windows (wpis w pasku zadań / migotanie)
    NIE wywołujemy withdraw()/deiconify(). Okno startuje z alpha=0
    i pozycją poza ekranem, a potem jest przesuwane + fade-in jednocześnie.
    """

    def __init__(self, parent, message: str, kind: str,
                 duration_ms: int, stack_offset: int = 0):
        super().__init__(parent)
        self._alive        = True
        self._parent       = parent
        self._duration_ms  = duration_ms
        self._stack_offset = stack_offset
        self._target_x     = 0
        self._target_y     = 0
        self._alpha_ok     = True   # czy -alpha jest obsługiwane

        # overrideredirect PRZED ustawieniem alpha — kolejność ma znaczenie
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)

        # Geometry PRZED deiconify/alpha — okno startuje poza ekranem
        self.geometry(f"{_TOAST_W}x{_TOAST_H}+-2000+-2000")

        try:
            self.wm_attributes("-alpha", 0.0)
        except tk.TclError:
            self._alpha_ok = False

        color = _COLORS.get(kind, "#0F52BA")
        icon  = _ICONS.get(kind, "ℹ")

        is_dark = ctk.get_appearance_mode() == "Dark"
        bg      = "#1e1e1e" if is_dark else "#ffffff"
        fg      = "#f0f0f0" if is_dark else "#1a1a1a"
        border  = "#3a3a3a" if is_dark else "#d0d0d0"

        self.configure(bg=bg)
        self.resizable(False, False)

        # Zewnętrzna ramka (border)
        outer = tk.Frame(self, bg=border, padx=1, pady=1)
        outer.pack(fill="both", expand=True)

        inner = tk.Frame(outer, bg=bg)
        inner.pack(fill="both", expand=True)

        # Kolorowy pasek po lewej
        tk.Frame(inner, width=5, bg=color).pack(side="left", fill="y")

        # Ikona
        tk.Label(
            inner, text=icon, bg=bg, fg=color,
            font=("Segoe UI", 14, "bold"), width=2,
        ).pack(side="left", padx=(6, 0))

        # Tekst
        tk.Label(
            inner, text=message, bg=bg, fg=fg,
            font=("Segoe UI", 11),
            anchor="w", justify="left",
            wraplength=_TOAST_W - 70,
        ).pack(side="left", fill="x", expand=True, padx=(4, 10))

        # Poczekaj aż Tk przetworzy geometrię, potem pokaż
        self.after(30, self._place_and_show)

    # ── pozycjonowanie ────────────────────────────────────────────────

    def _calc_target(self) -> tuple[int, int] | None:
        """Oblicza docelową pozycję (x, y) w pikselach ekranu."""
        try:
            self._parent.update_idletasks()
            px = self._parent.winfo_rootx()
            py = self._parent.winfo_rooty()
            pw = self._parent.winfo_width()
            ph = self._parent.winfo_height()

            # Jeśli okno nie jest widoczne (zminimalizowane) → użyj rozmiaru ekranu
            if pw < 10 or ph < 10:
                px = self._parent.winfo_screenwidth() - _TOAST_W - _MARGIN - 40
                py = 0
                ph = self._parent.winfo_screenheight()

            x = px + pw - _TOAST_W - _MARGIN
            y = py + ph - _TOAST_H - _MARGIN - self._stack_offset
            return x, y
        except tk.TclError:
            return None

    def _place_and_show(self):
        pos = self._calc_target()
        if pos is None:
            return
        self._target_x, self._target_y = pos

        # Geometry ustawiona PRZED animacją — start z offsetem +15px w dół
        self.geometry(
            f"{_TOAST_W}x{_TOAST_H}"
            f"+{self._target_x}+{self._target_y + _SLIDE_PX}"
        )
        self._animate_in()
        self.after(self._duration_ms, self._animate_out)

    def move_up(self):
        """Przesuwa toast wyżej gdy nowy toast pojawi się poniżej."""
        pos = self._calc_target()
        if pos is None:
            return
        self._target_x, self._target_y = pos
        try:
            self.geometry(f"{_TOAST_W}x{_TOAST_H}+{pos[0]}+{pos[1]}")
        except tk.TclError:
            pass

    # ── animacje ──────────────────────────────────────────────────────

    def _animate_in(self, step: int = 0):
        """Slide-up z dołu + fade-in jednocześnie (150ms, ease_out_cubic).
        ease_out_cubic: szybki start → płynne wyhamowanie = naturalny 'wjazd'.
        """
        if not self._alive:
            return
        step_ms = max(1, _IN_MS // _IN_STEPS)
        try:
            t      = _ease_out(step / _IN_STEPS)
            cur_y  = self._target_y + int(_SLIDE_PX * (1 - t))
            self.geometry(
                f"{_TOAST_W}x{_TOAST_H}+{self._target_x}+{cur_y}"
            )
            if self._alpha_ok:
                try:
                    self.wm_attributes("-alpha", min(t * 1.5, 1.0))  # fade szybszy niż slide
                except tk.TclError:
                    self._alpha_ok = False
            if step < _IN_STEPS:
                self.after(step_ms, lambda: self._animate_in(step + 1))
        except tk.TclError:
            pass

    def _animate_out(self, step: int = 0):
        """Slide-down + fade-out jednocześnie (120ms, ease_in_cubic).
        ease_in_cubic: wolny start → szybkie znikanie = toast 'wciągany' w dół.
        destroy() wywoływane dopiero po zakończeniu animacji.
        """
        if not self._alive:
            return
        step_ms = max(1, _OUT_MS // _OUT_STEPS)
        try:
            t      = _ease_in(step / _OUT_STEPS)
            alpha  = 1.0 - t
            cur_y  = self._target_y + int(_SLIDE_PX * t)
            self.geometry(
                f"{_TOAST_W}x{_TOAST_H}+{self._target_x}+{cur_y}"
            )
            if self._alpha_ok:
                try:
                    self.wm_attributes("-alpha", max(alpha, 0.0))
                except tk.TclError:
                    self._alpha_ok = False
            if step < _OUT_STEPS:
                self.after(step_ms, lambda: self._animate_out(step + 1))
            else:
                self._alive = False
                self.destroy()
        except tk.TclError:
            pass


class ToastManager:
    """Zarządza toastami dla danego okna głównego.
    Obsługuje kolejkowanie — do 3 toastów naraz (stack pionowy)."""

    def __init__(self, root: ctk.CTk):
        self._root  = root
        self._stack: list[_Toast] = []

    def show(self, message: str, kind: str = "success", duration_ms: int = 2500) -> None:
        """Wyświetla toast w prawym dolnym rogu okna."""
        # Usuń martwe toasty (_alive=False oznacza że widget jest już niszczony)
        self._stack = [t for t in self._stack if t._alive]

        # Max 3 równoczesne
        if len(self._stack) >= 3:
            oldest = self._stack.pop(0)
            try:
                oldest._alive = False
                oldest.destroy()
            except tk.TclError:
                pass

        # Przesuń istniejące wyżej
        for t in self._stack:
            t._stack_offset += _TOAST_H + 8
            t.move_up()

        offset = len(self._stack) * (_TOAST_H + 8)
        toast  = _Toast(self._root, message, kind, duration_ms, stack_offset=offset)
        self._stack.append(toast)
