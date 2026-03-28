"""
animations.py — Reużywalne animacje UI dla AegisVault
======================================================
Wszystkie animacje są non-blocking (oparte o after()).

API:
    shake(widget)                         — trzęsie oknem poziomo (błąd)
    pulse_label(label, sizes, interval)   — pulsuje etykietą przez zmianę fonta
    slide_fade_in(toplevel)               — slide-down + fade-in dla dialogów
    bind_hover_smooth(frame, nc, hc)      — płynny hover-color na CTkFrame
    ContextMenu(parent, x, y, items)      — stylizowane menu kontekstowe (PPM)
"""

import math
import time
import tkinter as tk
import customtkinter as ctk

from utils.easing import (
    smoothstep as _smoothstep,
    ease_out_cubic as _ease_out,
    ease_in_cubic as _ease_in,
    ease_out_back as _ease_back,
    DURATION_MICRO, DURATION_SHORT, DURATION_MEDIUM, DURATION_LONG,
)


# ── Helpers ───────────────────────────────────────────────────────────

def _resolve_color(color) -> str:
    """Zamienia (light, dark) tuple na aktualny kolor motywu."""
    if isinstance(color, tuple):
        return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]
    return color


def _parse_hex(c: str) -> tuple[int, int, int]:
    """Parsuje kolor #rrggbb do krotki (r, g, b). Wywoływać raz przy starcie animacji."""
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def _lerp_rgb(r1, g1, b1, r2, g2, b2, t: float) -> str:
    """Interpolacja liniowa na gotowych int-ach RGB — szybsza niż parsowanie co klatkę."""
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _lerp_color(c1: str, c2: str, t: float) -> str:
    """Interpolacja liniowa między dwoma kolorami hex (#rrggbb)."""
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = _parse_hex(c1)
    r2, g2, b2 = _parse_hex(c2)
    return _lerp_rgb(r1, g1, b1, r2, g2, b2, t)


# ── shake ─────────────────────────────────────────────────────────────

def shake(widget, amplitude: int = 7, count: int = 5, interval_ms: int = 32):
    """Trzęsie oknem (CTk / CTkToplevel) poziomo — feedback błędu.

    Parametry:
        amplitude   — maks. przesunięcie w pikselach
        count       — liczba wahnięć (w każdą stronę)
        interval_ms — czas jednego kroku animacji
    """
    try:
        widget.update_idletasks()
        ox = widget.winfo_rootx()
        oy = widget.winfo_rooty()
        ow = widget.winfo_width()
        oh = widget.winfo_height()
    except tk.TclError:
        return

    offsets = [
        int(amplitude * math.sin(i * math.pi / 2) * (1 - i / (count * 2)))
        for i in range(count * 2 + 1)
    ] + [0]

    def _step(idx: int = 0):
        if idx >= len(offsets):
            try:
                widget.geometry(f"{ow}x{oh}+{ox}+{oy}")
            except tk.TclError:
                pass
            return
        try:
            widget.geometry(f"{ow}x{oh}+{ox + offsets[idx]}+{oy}")
            widget.after(interval_ms, lambda: _step(idx + 1))
        except tk.TclError:
            pass

    _step()


# ── pulse_label ───────────────────────────────────────────────────────

def pulse_label(label: ctk.CTkLabel,
                sizes: list[int] | None = None,
                interval_ms: int = 55):
    """Pulsuje etykietą przez zmianę rozmiaru fonta (np. ikona przy starcie).

    Domyślna sekwencja: lekkie powiększenie → powrót.
    """
    if sizes is None:
        sizes = [48, 52, 56, 54, 50, 46, 48]

    # Pre-allocate fonty — unikamy tworzenia nowego obiektu w każdej klatce
    fonts = [ctk.CTkFont(size=s) for s in sizes]

    def _tick(idx: int = 0):
        if idx >= len(fonts):
            return
        try:
            label.configure(font=fonts[idx])
            label.after(interval_ms, lambda: _tick(idx + 1))
        except tk.TclError:
            pass

    _tick()


# ── slide_fade_in ─────────────────────────────────────────────────────

def slide_fade_in(toplevel, slide_px: int = 14, duration_ms: int = DURATION_SHORT, steps: int = 10):
    """Slide-down + fade-in dla CTkToplevel / CTk (np. dialogi).

    Okno startuje z alpha=0 i przesunięciem -slide_px w osi Y,
    potem płynnie przesuwa się na właściwą pozycję i staje się widoczne.
    Jeśli -alpha niedostępne (VM/RDP), wykonuje tylko slide bez fade.
    """
    try:
        toplevel.update_idletasks()
        tx = toplevel.winfo_x()
        ty = toplevel.winfo_y()
        tw = toplevel.winfo_width()
        th = toplevel.winfo_height()
    except tk.TclError:
        return

    step_ms = max(1, duration_ms // steps)
    alpha_supported = True

    def _tick(step: int = 0):
        if step > steps:
            return
        try:
            t     = _ease_out(step / steps)
            cur_y = ty - int(slide_px * (1 - t))
            toplevel.geometry(f"{tw}x{th}+{tx}+{cur_y}")
            if alpha_supported:
                toplevel.wm_attributes("-alpha", min(t * 1.4, 1.0))  # fade szybszy niż slide
            if step < steps:
                toplevel.after(step_ms, lambda: _tick(step + 1))
        except tk.TclError:
            pass

    try:
        toplevel.wm_attributes("-alpha", 0.0)
        toplevel.geometry(f"{tw}x{th}+{tx}+{ty - slide_px}")
        toplevel.after(8, lambda: _tick(0))
    except tk.TclError:
        # Fallback: brak obsługi alpha (np. Remote Desktop) — tylko slide
        alpha_supported = False
        toplevel.geometry(f"{tw}x{th}+{tx}+{ty - slide_px}")
        toplevel.after(8, lambda: _tick(0))


# ── bind_hover_smooth ─────────────────────────────────────────────────

def bind_hover_smooth(frame: ctk.CTkFrame,
                      normal_color,
                      hover_color,
                      steps: int = 5,
                      interval_ms: int = 12):
    """Dodaje płynny efekt hover (color transition) do CTkFrame.
    Używa AnimationScheduler (jeden 60fps loop) zamiast N osobnych after().
    """
    duration_ms = steps * interval_ms  # backward-compat: 5×12=60ms

    state = {
        "hovering": False,
        "t":        0.0,   # 0.0 = normal, 1.0 = hover
        "task_id":  None,
        "nc_rgb":   (0, 0, 0),
        "hc_rgb":   (0, 0, 0),
    }

    def _cancel():
        tid = state["task_id"]
        if tid is not None:
            try:
                get_scheduler(frame.winfo_toplevel()).cancel(tid)
            except Exception:
                pass
            state["task_id"] = None

    def _animate(dt_ms: float) -> bool:
        if state["hovering"]:
            state["t"] = min(state["t"] + dt_ms / duration_ms, 1.0)
        else:
            state["t"] = max(state["t"] - dt_ms / duration_ms, 0.0)

        t = _ease_out(state["t"]) if state["hovering"] else 1.0 - _ease_in(1.0 - state["t"])
        try:
            r1, g1, b1 = state["nc_rgb"]
            r2, g2, b2 = state["hc_rgb"]
            frame.configure(fg_color=_lerp_rgb(r1, g1, b1, r2, g2, b2, t))
        except tk.TclError:
            state["task_id"] = None
            return False

        done = (state["t"] >= 1.0 and state["hovering"]) or (state["t"] <= 0.0 and not state["hovering"])
        if done:
            state["task_id"] = None
        return not done

    def _trigger():
        _cancel()
        try:
            state["nc_rgb"] = _parse_hex(_resolve_color(normal_color))
            state["hc_rgb"] = _parse_hex(_resolve_color(hover_color))
        except (ValueError, IndexError):
            return
        try:
            state["task_id"] = get_scheduler(frame.winfo_toplevel()).add(_animate)
        except Exception:
            # fallback: old after() chain
            _fallback_animate()

    def _fallback_animate(step: int = 0):
        steps_fb = steps
        if state["hovering"]:
            cur_step = min(step + 1, steps_fb)
            t = _ease_out(cur_step / steps_fb)
        else:
            cur_step = max(step - 1, 0)
            t = 1.0 - _ease_in(1.0 - cur_step / steps_fb)
        try:
            r1, g1, b1 = state["nc_rgb"]
            r2, g2, b2 = state["hc_rgb"]
            frame.configure(fg_color=_lerp_rgb(r1, g1, b1, r2, g2, b2, t))
            if 0 < cur_step < steps_fb:
                frame.after(interval_ms, lambda: _fallback_animate(cur_step))
        except tk.TclError:
            pass

    def _on_enter(_e):
        state["hovering"] = True
        _trigger()

    def _on_leave(_e):
        try:
            fx = frame.winfo_rootx()
            fy = frame.winfo_rooty()
            fw = frame.winfo_width()
            fh = frame.winfo_height()
            mx = frame.winfo_pointerx()
            my = frame.winfo_pointery()
            if fx <= mx <= fx + fw and fy <= my <= fy + fh:
                return
        except tk.TclError:
            pass
        state["hovering"] = False
        _trigger()

    def _bind_recursive(widget):
        widget.bind("<Enter>", _on_enter, add="+")
        widget.bind("<Leave>", _on_leave, add="+")
        for child in widget.winfo_children():
            _bind_recursive(child)

    _bind_recursive(frame)


# ── animate_color ─────────────────────────────────────────────────────

def animate_color(widget,
                  from_color: str,
                  to_color:   str,
                  configure_fn,
                  steps:       int = 14,
                  interval_ms: int = 16):
    """Animuje płynną zmianę koloru poprzez interpolację RGB.

    Parametry:
        widget        — widget który dostarcza scheduler (after())
        from_color    — kolor startowy (#rrggbb)
        to_color      — kolor docelowy (#rrggbb)
        configure_fn  — callable(color: str) wywoływana każdą klatką,
                        np. lambda c: btn.configure(fg_color=c)
        steps         — liczba klatek animacji
        interval_ms   — czas między klatkami

    Przykład:
        animate_color(btn, "#4F8EF7", "#38A169",
                      lambda c: btn.configure(fg_color=c))
    """
    r1, g1, b1 = _parse_hex(from_color)
    r2, g2, b2 = _parse_hex(to_color)

    def _tick(step: int = 0):
        if step > steps:
            return
        try:
            t     = _smoothstep(step / steps)
            color = _lerp_rgb(r1, g1, b1, r2, g2, b2, t)
            configure_fn(color)
            if step < steps:
                widget.after(interval_ms, lambda: _tick(step + 1))
        except tk.TclError:
            pass

    _tick()


# ── ContextMenu ───────────────────────────────────────────────────────

class ContextMenu:
    """Stylizowane menu kontekstowe (prawy przycisk myszy).

    Użycie:
        ContextMenu(parent, event.x_root, event.y_root, [
            {"text": "➕ Dodaj",  "command": callback},
            None,                                          # separator
            {"text": "🗑 Usuń",  "command": cb2, "destructive": True},
        ])

    Menu pojawia się przy kursorze, zamyka się po kliknięciu
    poza nim lub wybraniu opcji. Fade-in ~80ms.
    """

    def __init__(self, parent, x: int, y: int, items: list):
        self._alive = True

        is_dark = ctk.get_appearance_mode() == "Dark"
        bg      = "#252525" if is_dark else "#ffffff"
        hover   = "#363636" if is_dark else "#f0f4ff"
        border  = "#3a3a3a" if is_dark else "#d0d0d0"
        fg      = "#f0f0f0" if is_dark else "#1a1a1a"

        self._win = tk.Toplevel(parent)
        self._win.overrideredirect(True)
        self._win.wm_attributes("-topmost", True)
        self._win.wm_attributes("-alpha", 0.0)
        self._win.geometry("1x1+-2000+-2000")   # off-screen do czasu ustalenia rozmiaru
        self._win.configure(bg=border)

        inner = tk.Frame(self._win, bg=bg)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        for item in items:
            if item is None:
                tk.Frame(inner, height=1, bg=border).pack(fill="x", padx=6, pady=3)
                continue

            text        = item.get("text", "")
            cmd         = item.get("command")
            destructive = item.get("destructive", False)
            item_fg     = "#e05252" if destructive else fg

            lbl = tk.Label(
                inner, text=text, bg=bg, fg=item_fg,
                font=("Segoe UI", 12), anchor="w",
                padx=14, pady=7, cursor="hand2"
            )
            lbl.pack(fill="x")
            lbl.bind("<Enter>", lambda e, w=lbl: w.configure(bg=hover))
            lbl.bind("<Leave>", lambda e, w=lbl: w.configure(bg=bg))
            lbl.bind("<Button-1>", lambda e, c=cmd: self._run(c))

        # Oblicz rozmiar i ustaw pozycję
        self._win.update_idletasks()
        w  = self._win.winfo_reqwidth()
        h  = self._win.winfo_reqheight()
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        cx = min(x, sw - w - 4)
        cy = min(y, sh - h - 4)
        self._win.geometry(f"{w}x{h}+{cx}+{cy}")

        # Zamknij po utracie focusa
        self._win.bind("<FocusOut>", lambda e: self._win.after(60, self.close))
        self._win.after(30, self._win.focus_force)

        # Fade-in
        self._win.after(10, self._fade_in)

    def _fade_in(self, alpha: float = 0.0):
        if not self._alive:
            return
        try:
            alpha = min(alpha + 0.25, 1.0)
            self._win.wm_attributes("-alpha", alpha)
            if alpha < 1.0:
                self._win.after(12, lambda: self._fade_in(alpha))
        except tk.TclError:
            pass

    def _run(self, cmd):
        self.close()
        if cmd:
            cmd()

    def close(self):
        if self._alive:
            self._alive = False
            try:
                self._win.destroy()
            except tk.TclError:
                pass


# ── animate_strength_bar ──────────────────────────────────────────────

def animate_strength_bar(bar_widget, target_color: str, delay_ms: int = 0,
                         duration_ms: int = DURATION_LONG, steps: int = 16):
    """Animuje kolor paska siły hasła z szarego (#555555) → target_color.

    Wywołuj po pack() na CTkFrame będącym paskiem siły.
    delay_ms synchronizuje z slide_in_row (opóźnienie tego samego wiersza).
    Używa AnimationScheduler (jeden loop 60fps) zamiast N niezależnych after().
    """
    start_color = "#555555"
    r1, g1, b1 = _parse_hex(start_color)
    r2, g2, b2 = _parse_hex(target_color)
    destroyed = [False]
    bar_widget.bind("<Destroy>", lambda _e: destroyed.__setitem__(0, True), add="+")

    def _start():
        elapsed = [0.0]

        def _fn(dt_ms: float) -> bool:
            if destroyed[0]:
                return False
            elapsed[0] += dt_ms
            t = min(elapsed[0] / duration_ms, 1.0)
            try:
                color = _lerp_rgb(r1, g1, b1, r2, g2, b2, _smoothstep(t))
                bar_widget.configure(fg_color=color)
                if t >= 1.0:
                    bar_widget.configure(fg_color=target_color)
                    return False
                return True
            except tk.TclError:
                return False

        try:
            get_scheduler(bar_widget.winfo_toplevel()).add(_fn)
        except Exception:
            # Fallback gdy brak toplevel
            step_ms = max(1, duration_ms // steps)

            def _tick(step: int = 0):
                if destroyed[0] or step > steps:
                    if not destroyed[0]:
                        try:
                            bar_widget.configure(fg_color=target_color)
                        except tk.TclError:
                            pass
                    return
                try:
                    t = _smoothstep(step / steps)
                    bar_widget.configure(fg_color=_lerp_rgb(r1, g1, b1, r2, g2, b2, t))
                    bar_widget.after(step_ms, lambda: _tick(step + 1))
                except tk.TclError:
                    pass

            _tick()

    if delay_ms > 0:
        bar_widget.after(delay_ms, _start)
    else:
        _start()


# ── slide_in_row ───────────────────────────────────────────────────────

def slide_in_row(widget, target_h: int, delay_ms: int = 0,
                 duration_ms: int = DURATION_MEDIUM, steps: int = 12):
    """Animuje CTkFrame (wiersz hasła) od height=0 do target_h.

    Używaj po pack() — widget musi być już zapakowany.
    delay_ms pozwala kaskadować wiersze (max 250ms łącznie).
    Używa AnimationScheduler (jeden loop 60fps) zamiast N niezależnych after().
    """
    destroyed = [False]
    widget.bind("<Destroy>", lambda _e: destroyed.__setitem__(0, True), add="+")

    def _start():
        try:
            widget.configure(height=0)
        except tk.TclError:
            return

        elapsed = [0.0]

        def _fn(dt_ms: float) -> bool:
            if destroyed[0]:
                return False
            elapsed[0] += dt_ms
            t = min(elapsed[0] / duration_ms, 1.0)
            try:
                widget.configure(height=max(1, int(target_h * _ease_out(t))))
                if t >= 1.0:
                    widget.configure(height=target_h)
                    return False
                return True
            except tk.TclError:
                return False

        try:
            get_scheduler(widget.winfo_toplevel()).add(_fn)
        except Exception:
            # Fallback gdy brak toplevel (widget nie osadzony)
            step_ms = max(1, duration_ms // steps)

            def _tick(step: int = 0):
                if destroyed[0]:
                    return
                if step > steps:
                    try:
                        widget.configure(height=target_h)
                    except tk.TclError:
                        pass
                    return
                try:
                    t = _ease_out(step / steps)
                    widget.configure(height=max(1, int(target_h * t)))
                    widget.after(step_ms, lambda: _tick(step + 1))
                except tk.TclError:
                    pass

            widget.after(0, _tick)

    if delay_ms > 0:
        widget.after(delay_ms, _start)
    else:
        _start()


# ── ripple_copy ────────────────────────────────────────────────────────

def ripple_copy(widget, duration_ms: int = 180):
    """Efekt ripple (rosnący okrąg) na przycisku — feedback kliknięcia Kopiuj.

    Wywołaj po kliknięciu Kopiuj — tworzy Canvas overlay i animuje okrąg.
    """
    try:
        widget.update_idletasks()
        w = widget.winfo_width()
        h = widget.winfo_height()
        if w < 2 or h < 2:
            return
    except tk.TclError:
        return

    # Pobierz kolor tła widgetu
    try:
        bg = widget.cget("fg_color")
        if isinstance(bg, (list, tuple)):
            bg = bg[1] if ctk.get_appearance_mode() == "Dark" else bg[0]
        if not bg or not str(bg).startswith("#"):
            bg = "#4F8EF7"
    except Exception:
        bg = "#4F8EF7"

    try:
        bg_rgb = _parse_hex(bg)
    except Exception:
        return

    cv = tk.Canvas(widget, highlightthickness=0, bd=0, bg=bg)
    cv.place(x=0, y=0, relwidth=1.0, relheight=1.0)
    cv.lift()

    cx, cy = w // 2, h // 2
    max_r = int(math.sqrt((w / 2) ** 2 + (h / 2) ** 2)) + 4

    destroyed = [False]
    cv.bind("<Destroy>", lambda _e: destroyed.__setitem__(0, True))

    elapsed = [0.0]
    # Kolor ripple = biały (255,255,255), bleeds do bg
    wr, wg, wb = 255, 255, 255
    br, bgc, bb = bg_rgb

    def _fn(dt_ms: float) -> bool:
        if destroyed[0]:
            return False
        elapsed[0] += dt_ms
        t = min(elapsed[0] / duration_ms, 1.0)
        eased = _ease_out(t)
        r = max(1, int(max_r * eased))
        # Kolor: zaczyna od jasnego, zanika do bg
        fade_t = t  # 0=jasny, 1=bg_color
        color = _lerp_rgb(wr, wg, wb, br, bgc, bb, fade_t * 0.85)
        cv.delete("all")
        try:
            cv.create_oval(cx - r, cy - r, cx + r, cy + r,
                           outline=color, width=max(1, int(3 * (1 - t))), fill="")
        except tk.TclError:
            return False
        if t >= 1.0:
            try:
                cv.destroy()
            except tk.TclError:
                pass
            return False
        return True

    try:
        get_scheduler(widget.winfo_toplevel()).add(_fn)
    except Exception:
        # Fallback: prosta wersja po czasie
        widget.after(duration_ms + 50, lambda: cv.destroy() if not destroyed[0] else None)


# ── AnimationScheduler ────────────────────────────────────────────────

class AnimationScheduler:
    """Jeden after(16) loop na root window. Wszystkie animacje rejestrują się tutaj.

    Zamiast każda animacja miała własny after() chain, rejestrują się tutaj
    jako fn(dt_ms) -> bool (True = kontynuuj, False = gotowe).
    Scheduler wywołuje wszystkie aktywne funkcje w jednej iteracji event-loop.
    """

    def __init__(self, root):
        self._root = root
        self._tasks: dict[int, callable] = {}
        self._running = False
        self._last_t: float | None = None
        self._next_id = 0

    def add(self, fn) -> int:
        """Rejestruje animację fn(dt_ms: float) -> bool. Zwraca handle id."""
        task_id = self._next_id
        self._next_id += 1
        self._tasks[task_id] = fn
        if not self._running:
            self._start()
        return task_id

    def cancel(self, task_id: int):
        self._tasks.pop(task_id, None)

    def pause(self):
        self._running = False

    def resume(self):
        if not self._running and self._tasks:
            self._start()

    def _start(self):
        self._running = True
        self._last_t = time.time()
        self._root.after(16, self._tick)

    def _tick(self):
        if not self._running:
            return
        now = time.time()
        dt_ms = (now - self._last_t) * 1000
        self._last_t = now

        done = []
        for task_id, fn in list(self._tasks.items()):
            try:
                if not fn(dt_ms):
                    done.append(task_id)
            except tk.TclError:
                done.append(task_id)

        for task_id in done:
            self._tasks.pop(task_id, None)

        if self._tasks and self._running:
            self._root.after(16, self._tick)
        else:
            self._running = False


_schedulers: dict[int, AnimationScheduler] = {}


def get_scheduler(root) -> AnimationScheduler:
    """Zwraca singleton AnimationScheduler dla danego root window."""
    key = id(root)
    if key not in _schedulers:
        _schedulers[key] = AnimationScheduler(root)
        # Usuń ze słownika gdy root zostanie zniszczony
        root.bind("<Destroy>", lambda e: _schedulers.pop(key, None), add="+")
    return _schedulers[key]


# ── crossfade_list ─────────────────────────────────────────────────────

def crossfade_list(scroll_frame, callback, delay_ms: int = 50):
    """Overlay na scroll_frame: ukrywa stary content → callback (rebuild) → overlay znika.

    Tworzy tk.Canvas overlay dopasowany kolorem do tła scroll_frame,
    po `delay_ms` ms wywołuje callback (który przebudowuje listę z slide_in_row),
    a następnie natychmiast usuwa overlay — slide_in_row tworzy efekt reveal.
    """
    is_dark = ctk.get_appearance_mode() == "Dark"
    bg = "#252525" if is_dark else "#f0f0f0"

    overlay = tk.Canvas(scroll_frame, bg=bg, highlightthickness=0, bd=0)
    overlay.place(x=0, y=0, relwidth=1, relheight=1)
    try:
        overlay.lift()
    except tk.TclError:
        pass

    def _run():
        try:
            callback()
        except Exception:
            pass
        try:
            overlay.destroy()
        except tk.TclError:
            pass

    try:
        scroll_frame.after(delay_ms, _run)
    except tk.TclError:
        callback()
