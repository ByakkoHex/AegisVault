"""
update_dialog.py - Dialogi aktualizacji AegisVault
===================================================
UpdateNotification — popup po zalogowaniu ("Hej, jest nowa wersja!")
UpdateDropdown     — panel-lista otwierany z ikonki w topbarze
"""

import webbrowser
import tkinter as tk
import customtkinter as ctk

ACCENT       = "#0F52BA"
ACCENT_HOVER = "#0C4398"
DARK_CARD    = "#1e1e1e"
DARK_BG      = "#1a1a1a"
LIGHT_CARD   = "#ffffff"
ORANGE       = "#f0a500"
ORANGE_HOVER = "#d4920a"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Popup po zalogowaniu
# ─────────────────────────────────────────────────────────────────────────────

class UpdateNotification(ctk.CTkToplevel):
    """Przyjazna karta 'Hej! Dostępna jest nowa wersja' pokazywana po zalogowaniu."""

    def __init__(self, parent, update_info: dict):
        super().__init__(parent)
        self.geometry("+5000+5000")          # off-screen: CTk auto-deiconify flash niewidoczny
        self.wm_attributes("-alpha", 0.0)   # alpha=0 na starcie; slide_fade_in ujawni okno
        self._info = update_info

        self.title("")
        self.geometry("460x390")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus_force()

        # Nie nadpisuj pozycji +5000+5000 — slide_fade_in wyśrodkuje okno off-screen.
        # self.geometry() z samym rozmiarem nie zmienia pozycji.
        self.geometry("460x390")

        self._build()
        from gui.animations import slide_fade_in
        self.after(20, lambda: slide_fade_in(self, slide_px=4, duration_ms=60, steps=12))

    def _build(self):
        # ── Nagłówek ──────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=(ORANGE, ORANGE), corner_radius=0, height=62)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text=f"🎉  Hej! Dostępna jest wersja {self._info['version']}",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#ffffff",
        ).pack(expand=True)

        # ── Treść ─────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=14)

        ctk.CTkLabel(
            body,
            text=f"Aktualna wersja: {self._info['current']}   →   Nowa: {self._info['version']}",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(anchor="w")

        ctk.CTkLabel(
            body, text="Co nowego:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", pady=(12, 4))

        changelog_box = ctk.CTkTextbox(
            body, height=150, corner_radius=8,
            fg_color=("gray95", "#252525"),
            border_width=1, border_color=("gray80", "#333"),
            font=ctk.CTkFont(size=11),
            wrap="word",
        )
        changelog_box.pack(fill="x")
        changelog_box.insert("1.0", self._info.get("changelog", "Brak informacji."))
        changelog_box.configure(state="disabled")

        # ── Przyciski ─────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(body, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(14, 0))

        ctk.CTkButton(
            btn_frame, text="⬇  Pobierz teraz",
            height=40, fg_color=(ORANGE, ORANGE),
            hover_color=(ORANGE_HOVER, ORANGE_HOVER),
            text_color="#ffffff",
            corner_radius=10, font=ctk.CTkFont(size=13, weight="bold"),
            command=self._download,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="Później",
            height=40,
            fg_color=("gray88", "#2a2a2a"),
            hover_color=("gray78", "#383838"),
            text_color=("gray20", "gray80"),
            corner_radius=10, font=ctk.CTkFont(size=13),
            command=self.destroy,
        ).pack(side="left")

    def _download(self):
        url = self._info.get("download_url", "")
        if url:
            webbrowser.open(url)
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Dropdown panel z topbaru
# ─────────────────────────────────────────────────────────────────────────────

class UpdateDropdown(tk.Toplevel):
    """Borderless panel-lista otwierany z ikonki w topbarze."""

    WIDTH = 320

    def __init__(self, parent, update_info: dict, anchor_widget):
        super().__init__(parent)
        self._info = update_info

        self.overrideredirect(True)
        self.attributes("-topmost", True)

        _dark = ctk.get_appearance_mode() == "Dark"
        self._colors = {
            "bg":     DARK_CARD   if _dark else "#f9f9f9",
            "border": "#3a3a3a"   if _dark else "#d0d0d0",
            "fg":     "#e8e8e8"   if _dark else "#1a1a1a",
            "gray":   "#888888",
            "btn_later_bg": "#3a3a3a" if _dark else "#e4e4e4",
            "btn_later_fg": "#cccccc" if _dark else "#333333",
        }

        self.configure(bg=self._colors["border"])
        self._build()
        self.update_idletasks()
        self._position(anchor_widget)

        # Zamknij przy kliknięciu poza panelem
        self.bind("<FocusOut>", lambda e: self.after(150, self._check_focus))
        self.focus_force()

    # ── Budowniczy ────────────────────────────────────────────────

    def _build(self):
        c = self._colors

        # 1px border via outer frame
        outer = tk.Frame(self, bg=c["border"], padx=1, pady=1)
        outer.pack(fill="both", expand=True)

        wrap = tk.Frame(outer, bg=c["bg"])
        wrap.pack(fill="both", expand=True)

        # Nagłówek z kolorem pomarańczowym
        hdr = tk.Frame(wrap, bg=ORANGE, height=38)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(
            hdr,
            text=f"⬆  Aktualizacja {self._info['version']}",
            bg=ORANGE, fg="#ffffff",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=12)

        tk.Button(
            hdr, text="✕",
            bg=ORANGE, fg="#ffffff",
            relief="flat", bd=0,
            font=("Segoe UI", 9),
            activebackground=ORANGE_HOVER, activeforeground="#ffffff",
            cursor="hand2",
            command=self.destroy,
        ).pack(side="right", padx=8)

        # Wersje
        ver_row = tk.Frame(wrap, bg=c["bg"], padx=14, pady=8)
        ver_row.pack(fill="x")

        tk.Label(
            ver_row,
            text=f"Twoja wersja:  {self._info['current']}",
            bg=c["bg"], fg=c["gray"],
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        tk.Label(
            ver_row,
            text=f"Nowa wersja:  {self._info['version']}",
            bg=c["bg"], fg=ORANGE,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(2, 0))

        # Separator
        tk.Frame(wrap, bg=c["border"], height=1).pack(fill="x", padx=14)

        # Changelog
        cl_frame = tk.Frame(wrap, bg=c["bg"], padx=14, pady=8)
        cl_frame.pack(fill="x")

        tk.Label(
            cl_frame, text="Co nowego:",
            bg=c["bg"], fg=c["fg"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))

        changelog = self._info.get("changelog", "Brak informacji.")
        if len(changelog) > 320:
            changelog = changelog[:320].rstrip() + "…"

        tk.Label(
            cl_frame,
            text=changelog,
            bg=c["bg"], fg=c["gray"],
            font=("Segoe UI", 9),
            wraplength=self.WIDTH - 28,
            justify="left",
        ).pack(anchor="w")

        # Separator
        tk.Frame(wrap, bg=c["border"], height=1).pack(fill="x", padx=14)

        # Przyciski
        btn_row = tk.Frame(wrap, bg=c["bg"], padx=14, pady=10)
        btn_row.pack(fill="x")

        tk.Button(
            btn_row, text="⬇  Pobierz",
            bg=ORANGE, fg="#ffffff",
            relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"),
            padx=14, pady=5,
            cursor="hand2",
            activebackground=ORANGE_HOVER, activeforeground="#ffffff",
            command=self._download,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_row, text="Później",
            bg=c["btn_later_bg"], fg=c["btn_later_fg"],
            relief="flat", bd=0,
            font=("Segoe UI", 10),
            padx=14, pady=5,
            cursor="hand2",
            activebackground=c["border"],
            command=self.destroy,
        ).pack(side="left")

    # ── Pomocnicze ────────────────────────────────────────────────

    def _position(self, anchor):
        """Pozycjonuje panel poniżej anchor widgetu, nie wychodząc poza ekran."""
        self.update_idletasks()
        anchor.update_idletasks()
        ax = anchor.winfo_rootx()
        ay = anchor.winfo_rooty() + anchor.winfo_height() + 4
        sw = self.winfo_screenwidth()
        w  = self.winfo_reqwidth() or self.WIDTH
        x  = min(ax, sw - w - 8)
        self.geometry(f"+{x}+{ay}")

    def _check_focus(self):
        try:
            if self.focus_displayof() is None:
                self.destroy()
        except Exception:
            pass

    def _download(self):
        url = self._info.get("download_url", "")
        if url:
            webbrowser.open(url)
        self.destroy()
