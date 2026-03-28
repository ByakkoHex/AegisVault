"""
dialogs.py - Stylizowane okna dialogowe dla AegisVault
Zastępuje domyślne okna messagebox systemu Windows.
"""

import customtkinter as ctk
from gui.animations import slide_fade_in
from gui.gradient import AnimatedGradientCanvas

ACCENT       = "#4F8EF7"
ACCENT_HOVER = "#3a7ae0"
BTN_RED      = "#e05252"
BTN_RED_HOVER= "#c43e3e"
BTN_GRAY     = "#3a3a3a"
BTN_GRAY_HVR = "#4a4a4a"

ICONS = {
    "error":   "✖",
    "info":    "ℹ",
    "warning": "⚠",
    "question":"?",
    "success": "✔",
}

COLOR_ICON = {
    "error":   "#e05252",
    "info":    "#4F8EF7",
    "warning": "#f0a500",
    "question":"#4F8EF7",
    "success": "#4caf50",
}


class _BaseDialog(ctk.CTkToplevel):
    """Bazowe okno dialogowe."""

    def __init__(self, parent, title: str, message: str, kind: str = "info"):
        super().__init__(parent)
        self.result = None

        self.title(title)
        self.resizable(False, False)
        self.grab_set()           # modal
        self.lift()
        self.focus_force()

        # wyśrodkuj względem rodzica
        self._center(parent)

        self._build(title, message, kind)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())

        # Animacja otwarcia
        self.after(10, lambda: slide_fade_in(self, slide_px=12, duration_ms=140))

    def _center(self, parent):
        self.update_idletasks()
        if parent and parent.winfo_exists():
            px = parent.winfo_rootx() + parent.winfo_width() // 2
            py = parent.winfo_rooty() + parent.winfo_height() // 2
        else:
            px, py = 640, 400
        w, h = 420, 240
        self.geometry(f"{w}x{h}+{px - w//2}+{py - h//2}")

    def _build(self, title: str, message: str, kind: str):
        icon   = ICONS.get(kind, "ℹ")
        icolor = COLOR_ICON.get(kind, ACCENT)

        outer = ctk.CTkFrame(self, corner_radius=0)
        outer.pack(fill="both", expand=True)

        # nagłówek z kolorowym paskiem po lewej
        header = ctk.CTkFrame(outer, fg_color=icolor, corner_radius=0, width=4)
        header.pack(side="left", fill="y")

        content = ctk.CTkFrame(outer, fg_color="transparent", corner_radius=0)
        content.pack(side="left", fill="both", expand=True, padx=20, pady=20)

        # ikona + tytuł
        top_row = ctk.CTkFrame(content, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            top_row, text=icon, font=("Segoe UI", 22, "bold"),
            text_color=icolor, width=32
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            top_row, text=title,
            font=("Segoe UI", 14, "bold"),
            anchor="w"
        ).pack(side="left", fill="x", expand=True)

        import customtkinter as _ctk
        _dlg_base = "#1e1e1e" if _ctk.get_appearance_mode() == "Dark" else "#f5f5f5"
        _sep = AnimatedGradientCanvas(
            content,
            accent=icolor,
            base=_dlg_base,
            anim_mode="slide",
            period_ms=5000,
            fps=20,
            n_bands=1,
            direction="h",
            steps=64,
            height=2,
        )
        _sep.pack(fill="x")
        _sep.start_animation()

        # treść
        ctk.CTkLabel(
            content, text=message,
            font=("Segoe UI", 12),
            anchor="w", justify="left",
            wraplength=340
        ).pack(fill="x", pady=(0, 16))

        self._build_buttons(content, icolor)

    def _build_buttons(self, parent, accent_color):
        """Nadpisz w podklasach."""
        pass

    def _on_close(self):
        self.result = False
        self.destroy()

    def wait(self):
        self.wait_window()
        return self.result


class _InfoDialog(_BaseDialog):
    def _build_buttons(self, parent, accent_color):
        ctk.CTkButton(
            parent, text="OK", width=90,
            fg_color=accent_color,
            hover_color=ACCENT_HOVER if accent_color == ACCENT else accent_color,
            command=self._ok
        ).pack(anchor="e")

    def _ok(self):
        self.result = True
        self.destroy()


class _YesNoDialog(_BaseDialog):
    def __init__(self, parent, title, message, kind="question",
                 yes_text="Tak", no_text="Nie", destructive=False):
        self._yes_text = yes_text
        self._no_text  = no_text
        self._destructive = destructive
        super().__init__(parent, title, message, kind)
        self.bind("<Return>", lambda e: self._yes())

    def _build_buttons(self, parent, accent_color):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(anchor="e")

        yes_fg    = BTN_RED      if self._destructive else ACCENT
        yes_hover = BTN_RED_HOVER if self._destructive else ACCENT_HOVER

        ctk.CTkButton(
            row, text=self._no_text, width=80,
            fg_color=BTN_GRAY, hover_color=BTN_GRAY_HVR,
            command=self._no
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            row, text=self._yes_text, width=80,
            fg_color=yes_fg, hover_color=yes_hover,
            command=self._yes
        ).pack(side="left")

    def _yes(self):
        self.result = True
        self.destroy()

    def _no(self):
        self.result = False
        self.destroy()


# ──────────────────────────────────────────────
# Publiczne API (zbliżone do tkinter.messagebox)
# ──────────────────────────────────────────────

def show_error(title: str, message: str, parent=None) -> None:
    _InfoDialog(parent, title, message, kind="error").wait()


def show_info(title: str, message: str, parent=None) -> None:
    _InfoDialog(parent, title, message, kind="info").wait()


def show_success(title: str, message: str, parent=None) -> None:
    _InfoDialog(parent, title, message, kind="success").wait()


def show_warning(title: str, message: str, parent=None) -> None:
    _InfoDialog(parent, title, message, kind="warning").wait()


def ask_yes_no(title: str, message: str, parent=None,
               yes_text="Tak", no_text="Nie", destructive=False) -> bool:
    """Zwraca True jeśli użytkownik kliknął 'Tak'."""
    return _YesNoDialog(
        parent, title, message, kind="question",
        yes_text=yes_text, no_text=no_text,
        destructive=destructive
    ).wait()
