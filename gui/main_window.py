"""
main_window.py - Główne okno aplikacji AegisVault
==================================================
Funkcje:
- Kategorie z filtrowaniem (domyślne + własne użytkownika)
- Auto-lock po bezczynności (5 min)
- Schowek z odliczaniem (30s)
- Eksport/Import zaszyfrowanego backupu + import z innych menedżerów
- Tray icon (minimalizacja do paska zadań)
- Skróty klawiszowe
- Data ważności hasła + badge
- Kosz (soft-delete, 30 dni)
- HIBP sprawdzanie wycieków
"""

import sys
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
import pyperclip
import threading
import time
import os
from datetime import datetime, date, timezone
from PIL import Image

from database.db_manager import DatabaseManager
from core.crypto import CryptoManager, generate_password
import random
import string
import webbrowser
from database.models import Password, DEFAULT_CATEGORIES, CustomCategory
from utils.password_strength import check_strength, _build_checklist
from utils.sync_client import SyncClient
from gui.dialogs import show_error, show_info, show_success, ask_yes_no
from gui.toast import ToastManager
from gui.animations import bind_hover_smooth, slide_fade_in, slide_in_row, animate_strength_bar, ContextMenu, animate_color, crossfade_list, get_scheduler
from utils.easing import ease_out_cubic as _ease_out, ease_in_cubic as _ease_in, ease_out_back as _ease_back
from gui.gradient import GradientCanvas, AnimatedGradientCanvas
from gui.score_ring import AnimatedScoreRing
from gui.hex_background import HexBackground, apply_hex_to_canvas, apply_hex_to_window, apply_hex_to_scrollable, apply_hex_overlay
from utils.prefs_manager import PrefsManager, THEMES
from utils import security_score as _sec_score
from utils.updater import check_for_update
import utils.windows_hello as wh

_prefs = PrefsManager()
ACCENT       = _prefs.get_accent()
ACCENT_HOVER = _prefs.get_accent_hover()

DARK_BG      = "#1a1a1a"
DARK_CARD    = "#1e1e1e"
DARK_ROW     = "#2a2a2a"
LIGHT_BG     = "#f5f5f5"
LIGHT_CARD   = "#ffffff"
LIGHT_ROW    = "#ffffff"

AUTO_LOCK_SECONDS = 300
CLIPBOARD_SECONDS = 30


def _blend_accent(accent: str, base: str, alpha: float) -> str:
    """Miesza kolor akcentu z kolorem tła (alpha=0→base, alpha=1→accent).
    Używane do generowania subtelnych hover-tintów zgodnych z motywem.
    """
    def _parse(c):
        c = c.lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)

    ar, ag, ab = _parse(accent)
    br, bg, bb = _parse(base)
    r = int(br + (ar - br) * alpha)
    g = int(bg + (ag - bg) * alpha)
    b = int(bb + (ab - bb) * alpha)
    return f"#{r:02x}{g:02x}{b:02x}"

def _luminance(c: str) -> float:
    """Względna luminancja koloru hex (0=czarny, 1=biały, wg sRGB)."""
    def _lin(v: int) -> float:
        s = v / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _resolve_menu_color(accent: str) -> str:
    """Zwraca accent lub jego rozjaśnioną wersję, zależnie od luminancji.
    Używane do tekstu nakładkowego na gradiencie headerów.
    """
    lum = _luminance(accent)
    # Jeśli akcent jest za ciemny (< 0.15) podnieś jasność by był czytelny
    if lum < 0.15:
        return _blend_accent("#ffffff", accent, 0.55)
    return accent


def _gbg() -> str:
    """Gradient endpoint background — ciemne/jasne tło zależnie od trybu."""
    return DARK_BG if ctk.get_appearance_mode() == "Dark" else LIGHT_BG


def _gcard() -> str:
    """Gradient endpoint card — ciemna/jasna karta zależnie od trybu."""
    return DARK_CARD if ctk.get_appearance_mode() == "Dark" else LIGHT_CARD


def _color_distance(c1: str, c2: str) -> float:
    """Euklidesowa odległość między dwoma kolorami hex w przestrzeni RGB (0–441)."""
    def _p(c):
        c = c.lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    r1, g1, b1 = _p(c1)
    r2, g2, b2 = _p(c2)
    return ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5


def _score_color(score: int, accent: str) -> str:
    """Zwraca kolor tekstu dla danego score (zielony/pomarańczowy/czerwony).

    Jeśli kolor pokrywa się z akcentem (dystans < 110), rozjaśnia go o 40%
    w kierunku bieli, żeby nie wtapiał się w tło topbara.
    """
    if score >= 80:
        raw = "#4caf50"
    elif score >= 50:
        raw = "#f0a500"
    else:
        raw = "#e05252"

    if _color_distance(raw, accent) < 110:
        # Blend w kierunku bieli — zachowuje barwę, zwiększa jasność
        raw = _blend_accent("#ffffff", raw, 0.38)
    return raw


CATEGORIES = {
    "Wszystkie":    {"icon": "📋", "color": None},
    "Social Media": {"icon": "💬", "color": "#E53E3E"},
    "Praca":        {"icon": "💼", "color": "#D69E2E"},
    "Bankowość":    {"icon": "🏦", "color": "#38A169"},
    "Rozrywka":     {"icon": "🎮", "color": "#805AD5"},
    "Inne":         {"icon": "📁", "color": "#718096"},
    "Wygasające":   {"icon": "⏰", "color": None},
}
# Wygodne aliasy używane jako parametry domyślne
DEFAULT_CATEGORY_COLORS = {k: v["color"] for k, v in CATEGORIES.items() if v["color"]}


# ──────────────────────────────────────────────
# FORMULARZ DODAWANIA / EDYCJI
# ──────────────────────────────────────────────

class PasswordFormWindow(ctk.CTkToplevel):
    def __init__(self, parent, db, crypto, user, entry=None):
        super().__init__(parent)
        self.geometry("+5000+5000")   # off-screen: CTk auto-deiconify flash niewidoczny
        self.wm_attributes("-alpha", 0.0)
        self.db     = db
        self.crypto = crypto
        self.user   = user
        self.entry  = entry
        self.result = False
        self._strength_job = None  # debounce handle

        self.title("Edytuj hasło" if entry else "Dodaj nowe hasło")
        self.geometry("460x720")
        self.minsize(460, 560)
        self.resizable(False, True)
        self.grab_set()
        self.focus()
        self._build_ui()

        if entry:
            self.entry_title.insert(0, entry.title or "")
            self.entry_username.insert(0, entry.username or "")
            self.entry_url.insert(0, entry.url or "")
            self.entry_notes.insert("1.0", entry.notes or "")
            self.entry_password.insert(0, db.decrypt_password(entry, crypto))
            if entry.category:
                self.category_var.set(entry.category)
            if entry.expires_at:
                self.entry_expires.insert(0, entry.expires_at.strftime("%Y-%m-%d"))

        self.after(20, self._reveal)

    def _build_ui(self):
        apply_hex_to_window(self)
        ctk.CTkLabel(
            self,
            text="✏️ Edytuj hasło" if self.entry else "➕ Dodaj hasło",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(pady=(22, 6))

        # Animowany separator pod tytułem
        self._title_sep = AnimatedGradientCanvas(
            self,
            accent=ACCENT,
            base=_gcard(),
            anim_mode="slide",
            period_ms=6000,
            fps=20,
            n_bands=1,
            direction="h",
            steps=96,
            height=2,
        )
        self._title_sep.pack(fill="x", padx=20, pady=(0, 10))
        self._title_sep.start_animation()

        outer = ctk.CTkFrame(self, corner_radius=16, fg_color=("gray92", "#1e1e1e"))
        outer.pack(padx=20, fill="both", expand=True, pady=(0, 16))

        frame = ctk.CTkScrollableFrame(outer, corner_radius=0, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        apply_hex_to_canvas(frame._parent_canvas, hex_size=36, glow_max=2, glow_interval_ms=1800)

        self._field(frame, "Nazwa serwisu", "np. Gmail, GitHub...", False, "entry_title")
        self._field(frame, "Login / Email", "Login lub email...", False, "entry_username")

        # Hasło + pokaż
        ctk.CTkLabel(frame, text="Hasło", anchor="w", font=ctk.CTkFont(size=12)).pack(
            padx=16, pady=(12, 2), fill="x"
        )
        pwd_row = ctk.CTkFrame(frame, fg_color="transparent")
        pwd_row.pack(padx=16, fill="x")

        self.entry_password = ctk.CTkEntry(
            pwd_row, placeholder_text="Hasło...", show="•", height=42, corner_radius=10
        )
        self.entry_password.pack(side="left", fill="x", expand=True)

        self.show_pwd = False
        ctk.CTkButton(
            pwd_row, text="👁", width=42, height=42,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"), corner_radius=10,
            command=self._toggle_password
        ).pack(side="left", padx=(6, 0))

        # Generator + HIBP w jednym wierszu
        action_row = ctk.CTkFrame(frame, fg_color="transparent")
        action_row.pack(padx=16, pady=(8, 0), fill="x")

        ctk.CTkButton(
            action_row, text="⚡ Generuj", height=32,
            fg_color=("#ddeeff", "#1a3a5c"), hover_color=("#cce0ff", "#1e4a70"),
            text_color=(ACCENT, "#7ab8f5"), corner_radius=10,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._generate_password
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        ctk.CTkButton(
            action_row, text="🔍 Sprawdź wyciek", height=32,
            fg_color=("#fff3e0", "#2a1a00"), hover_color=("#ffe0b2", "#3a2800"),
            text_color=("#e65100", "#ffb74d"), corner_radius=10,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._check_hibp
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))

        # Status HIBP
        self._hibp_label = ctk.CTkLabel(
            frame, text="", font=ctk.CTkFont(size=11), anchor="w"
        )
        self._hibp_label.pack(padx=16, fill="x")

        # Easter egg — ukryty napis przy haśle "AEZAKMI"
        self._aezakmi_label = ctk.CTkLabel(
            frame, text="",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color=ACCENT, anchor="w",
        )
        self._aezakmi_label.pack(padx=16, fill="x")

        # Wskaźnik siły
        self.strength_bar = ctk.CTkProgressBar(frame, height=6, corner_radius=3)
        self.strength_bar.pack(padx=16, pady=(6, 0), fill="x")
        self.strength_bar.set(0)

        self.strength_label = ctk.CTkLabel(frame, text="", font=ctk.CTkFont(size=11), anchor="w")
        self.strength_label.pack(padx=16, fill="x")

        # Checklist
        checklist_frame = ctk.CTkFrame(frame, fg_color=("gray88", "#252525"), corner_radius=8)
        checklist_frame.pack(padx=16, pady=(4, 0), fill="x")

        self._checklist_rows = []
        for item in _build_checklist(""):
            lbl = ctk.CTkLabel(
                checklist_frame, text=f"❌  {item['text']}",
                font=ctk.CTkFont(size=11), text_color="gray50", anchor="w"
            )
            lbl.pack(padx=10, pady=1, fill="x")
            self._checklist_rows.append(lbl)

        self.entry_password.bind("<KeyRelease>", lambda e: (self._update_strength(), self._check_aezakmi()))

        self._field(frame, "URL (opcjonalnie)", "https://...", False, "entry_url")

        # Kategoria
        cat_header = ctk.CTkFrame(frame, fg_color="transparent")
        cat_header.pack(padx=16, pady=(12, 2), fill="x")
        ctk.CTkLabel(cat_header, text="Kategoria", anchor="w",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkButton(
            cat_header, text="＋ Nowa", width=70, height=22,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"),
            hover_color=("gray85", "#2a2a2a"),
            text_color=("gray40", "gray60"),
            font=ctk.CTkFont(size=11), corner_radius=6,
            command=self._new_category_from_form
        ).pack(side="right")

        self.category_var = ctk.StringVar(value="Inne")
        all_cats = self.db.get_all_categories(self.user)
        self._category_menu = ctk.CTkOptionMenu(
            frame, values=all_cats,
            variable=self.category_var, height=38, corner_radius=10
        )
        self._category_menu.pack(padx=16, fill="x")

        # Data ważności
        ctk.CTkLabel(frame, text="Data ważności (opcjonalnie, RRRR-MM-DD)",
                     anchor="w", font=ctk.CTkFont(size=12)).pack(
            padx=16, pady=(12, 2), fill="x"
        )
        self.entry_expires = ctk.CTkEntry(
            frame, placeholder_text="np. 2025-12-31",
            height=38, corner_radius=10
        )
        self.entry_expires.pack(padx=16, fill="x")

        # Notatki
        ctk.CTkLabel(frame, text="Notatki (opcjonalnie)", anchor="w", font=ctk.CTkFont(size=12)).pack(
            padx=16, pady=(12, 2), fill="x"
        )
        self.entry_notes = ctk.CTkTextbox(
            frame, height=55, corner_radius=10,
            fg_color=("gray95", "#2e2e2e"),
            text_color=("gray10", "gray92"),
            border_color=("gray70", "#444444"), border_width=1,
        )
        self.entry_notes.pack(padx=16, fill="x")

        # Historia (tylko edycja)
        if self.entry:
            hist = self.db.get_history(self.entry)
            if hist:
                self._build_history_section(frame, hist)

        # Przyciski
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(padx=16, pady=(12, 16), fill="x")

        ctk.CTkButton(
            btn_row, text="Anuluj", height=42,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"), hover_color=("gray85", "#2a2a2a"),
            text_color=("gray20", "gray80"), corner_radius=10,
            command=self.destroy
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            btn_row, text="💾  Zapisz", height=42,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_save
        ).pack(side="left", fill="x", expand=True, padx=(6, 0))

    def _build_history_section(self, parent, hist):
        header_row = ctk.CTkFrame(parent, fg_color="transparent")
        header_row.pack(padx=16, pady=(14, 4), fill="x")

        ctk.CTkLabel(
            header_row, text="Historia haseł",
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w"
        ).pack(side="left")

        ctk.CTkLabel(
            header_row,
            text=f"{len(hist)}/10 wersji",
            font=ctk.CTkFont(size=11), text_color="gray", anchor="e"
        ).pack(side="right")

        hist_frame = ctk.CTkFrame(parent, fg_color=("gray88", "#252525"), corner_radius=8)
        hist_frame.pack(padx=16, fill="x")

        self._hist_visible: dict[int, bool] = {}

        for idx, h in enumerate(hist):
            # Separator między wierszami
            if idx > 0:
                sep = ctk.CTkFrame(hist_frame, height=1, fg_color=("gray75", "#333333"))
                sep.pack(fill="x", padx=8)

            row = ctk.CTkFrame(hist_frame, fg_color="transparent", height=1)
            row.pack(fill="x", padx=8, pady=6)

            # Lewa kolumna: numer + data
            left = ctk.CTkFrame(row, fg_color="transparent", height=1)
            left.pack(side="left", fill="x", expand=True)

            date_str = h.changed_at.strftime("%d.%m.%Y  %H:%M") if h.changed_at else "?"
            ctk.CTkLabel(
                left, text=f"#{idx + 1}  🕐 {date_str}",
                font=ctk.CTkFont(size=11), text_color=("gray40", "gray60"), anchor="w"
            ).pack(anchor="w")

            # Podgląd hasła (maskowany)
            try:
                plain = self.crypto.decrypt(h.encrypted_password)
            except Exception:
                plain = ""

            masked = "•" * min(len(plain), 16) if plain else "—"
            pwd_var = ctk.StringVar(value=masked)
            self._hist_visible[h.id] = False

            pwd_lbl = ctk.CTkLabel(
                left, textvariable=pwd_var,
                font=ctk.CTkFont(size=12, family="Courier"), anchor="w",
                text_color=("gray20", "gray85")
            )
            pwd_lbl.pack(anchor="w")

            # Prawa kolumna: przyciski
            right = ctk.CTkFrame(row, fg_color="transparent", height=1)
            right.pack(side="right")

            def _toggle_vis(h=h, plain=plain, masked=masked, var=pwd_var):
                self._hist_visible[h.id] = not self._hist_visible[h.id]
                var.set(plain if self._hist_visible[h.id] else masked)

            ctk.CTkButton(
                right, text="👁", width=32, height=28,
                fg_color="transparent", border_width=1,
                border_color=("gray70", "gray50"),
                font=ctk.CTkFont(size=12), corner_radius=8,
                command=_toggle_vis
            ).pack(side="left", padx=(0, 4))

            ctk.CTkButton(
                right, text="Przywróć", width=76, height=28,
                fg_color="transparent", border_width=1,
                border_color=(ACCENT, ACCENT),
                text_color=(ACCENT, ACCENT),
                hover_color=("#ddeeff", "#1a3a5c"),
                font=ctk.CTkFont(size=11), corner_radius=8,
                command=lambda h=h: self._restore_history(h)
            ).pack(side="left")

    def _restore_history(self, hist_entry):
        if ask_yes_no("Przywróć", "Przywrócić to hasło z historii? Aktualne zostanie zachowane w historii.",
                      parent=self, yes_text="Przywróć"):
            self.db.restore_from_history(self.entry, hist_entry)
            self.entry_password.delete(0, "end")
            self.entry_password.insert(0, self.db.decrypt_password(self.entry, self.crypto))
            self._do_update_strength()
            show_success("Przywrócono", "Hasło zostało przywrócone z historii.", parent=self)

    def _new_category_from_form(self):
        """Otwiera dialog nowej kategorii i po dodaniu odświeża dropdown."""
        def _on_created(name, icon):
            cats = self.db.get_all_categories(self.user)
            self._category_menu.configure(values=cats)
            self.category_var.set(name)
        _CategoryDialog(self, self.db, self.user,
                        accent=ACCENT, accent_hover=ACCENT_HOVER,
                        on_created=_on_created)

    def _reveal(self):
        # Oblicz docelową pozycję (centrum rodzica)
        cx, cy = None, None
        try:
            par = self.master
            if par and par.winfo_exists():
                pw, ph = par.winfo_width(), par.winfo_height()
                px, py = par.winfo_rootx(), par.winfo_rooty()
                ww = self.winfo_reqwidth() or 460
                wh = self.winfo_reqheight() or 720
                cx = px + (pw - ww) // 2
                cy = py + (ph - wh) // 2
        except tk.TclError:
            pass
        # Okno startuje na +5000+5000 — deiconify flash alpha=1.0 jest off-screen
        self.deiconify()
        # alpha=0 natychmiast po deiconify (Windows resetuje alpha przy show)
        try:
            self.wm_attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        # Przesuń na właściwą pozycję przy alpha=0 (ruch jest niewidoczny)
        if cx is not None:
            try:
                self.geometry(f"+{cx}+{cy}")
            except tk.TclError:
                pass
        self.update_idletasks()
        def _fade(step=0, steps=5):
            if not self.winfo_exists():
                return
            try:
                self.wm_attributes("-alpha", (step + 1) / steps)
            except tk.TclError:
                pass
            if step + 1 < steps:
                self.after(6, lambda: _fade(step + 1, steps))
            else:
                try:
                    self.wm_attributes("-alpha", 1.0)
                except tk.TclError:
                    pass
        _fade()

    def _field(self, parent, label, placeholder, secret, attr):
        ctk.CTkLabel(parent, text=label, anchor="w", font=ctk.CTkFont(size=12)).pack(
            padx=16, pady=(12, 2), fill="x"
        )
        entry = ctk.CTkEntry(parent, placeholder_text=placeholder,
                             show="•" if secret else "", height=42, corner_radius=10)
        entry.pack(padx=16, fill="x")
        setattr(self, attr, entry)

    def _toggle_password(self):
        self.show_pwd = not self.show_pwd
        self.entry_password.configure(show="" if self.show_pwd else "•")

    def _update_strength(self):
        # Debounce: anuluj poprzedni job, uruchom po 150ms od ostatniego klawisza
        if self._strength_job is not None:
            try:
                self.after_cancel(self._strength_job)
            except tk.TclError:
                pass
        self._strength_job = self.after(150, self._do_update_strength)

    def _do_update_strength(self):
        self._strength_job = None
        pwd = self.entry_password.get()
        result = check_strength(pwd)
        self.strength_bar.set(result["percent"] / 100)
        self.strength_bar.configure(progress_color=result["color"])
        if result["label"]:
            self.strength_label.configure(
                text=f"{result['label']}   •   Entropia: {result['entropy']} bit",
                text_color=result["color"]
            )
        else:
            self.strength_label.configure(text="")
        for item, row in zip(result["checklist"], self._checklist_rows):
            icon  = "✅" if item["met"] else "❌"
            color = "#38a169" if item["met"] else ("gray50" if not pwd else "#e53e3e")
            row.configure(text=f"{icon}  {item['text']}", text_color=color)

    def _check_aezakmi(self):
        pwd = self.entry_password.get()
        if pwd.upper() == "AEZAKMI":
            self._aezakmi_label.configure(
                text="Tego organy ścigania nie sprawdzają, sam pisałem ten kod :D"
            )
        else:
            self._aezakmi_label.configure(text="")

    def _generate_password(self):
        pwd = generate_password(length=20)
        self.entry_password.delete(0, "end")
        self.entry_password.insert(0, pwd)
        self.entry_password.configure(show="")
        self.show_pwd = True
        self._do_update_strength()
        pyperclip.copy(pwd)
        show_success("Generator", f"Wygenerowano i skopiowano do schowka!\n\n{pwd}", parent=self)

    def _check_hibp(self):
        pwd = self.entry_password.get()
        if not pwd:
            self._hibp_label.configure(text="Najpierw wpisz hasło.", text_color="gray")
            return
        self._hibp_label.configure(text="⏳ Sprawdzanie...", text_color="gray")

        def run():
            from utils.hibp import check_password
            breached, count = check_password(pwd)
            if count == -1:
                msg, color = "⚠️ Brak połączenia z HIBP.", "#f0a500"
            elif breached:
                msg   = f"🚨 Hasło wyciekło {count:,} razy! Zmień je natychmiast."
                color = "#e05252"
            else:
                msg, color = "✅ Hasło nie zostało znalezione w wyciekach.", "#4caf50"
            self.after(0, lambda: self._hibp_label.configure(text=msg, text_color=color))

        threading.Thread(target=run, daemon=True).start()

    def _parse_expires(self) -> datetime | None:
        raw = self.entry_expires.get().strip()
        if not raw:
            return None
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        raise ValueError(f"Nierozpoznany format daty: '{raw}'  (użyj RRRR-MM-DD)")

    def _on_save(self):
        title    = self.entry_title.get().strip()
        username = self.entry_username.get().strip()
        password = self.entry_password.get()
        url      = self.entry_url.get().strip()
        notes    = self.entry_notes.get("1.0", "end").strip()
        category = self.category_var.get()

        if not title:
            show_error("Błąd", "Nazwa serwisu jest wymagana!", parent=self)
            return
        if not password:
            show_error("Błąd", "Hasło jest wymagane!", parent=self)
            return

        try:
            expires = self._parse_expires()
        except ValueError as e:
            show_error("Błąd daty", str(e), parent=self)
            return

        if self.entry:
            self.db.update_password(
                self.entry, self.crypto,
                title=title, username=username, plaintext_password=password,
                url=url, notes=notes, category=category, expires_at=expires
            )
        else:
            self.db.add_password(
                self.user, self.crypto,
                title=title, username=username, plaintext_password=password,
                url=url, notes=notes, category=category, expires_at=expires
            )
        self.result = True
        self.destroy()

    def destroy(self):
        try:
            self._title_sep.stop_animation()
        except Exception:
            pass
        super().destroy()


# ──────────────────────────────────────────────
# DIALOG NOWEJ KATEGORII (z pickerem emoji)
# ──────────────────────────────────────────────

_EMOJI_PICKER = [
    "🏠", "💼", "🏦", "🎮", "🎵", "📱", "💻", "🛒",
    "✈️", "🏋️", "📚", "🔐", "🌐", "💰", "🎯", "🎨",
    "🔧", "🏥", "🍕", "🚗", "👤", "❤️", "⭐", "🔑",
    "📧", "🛡️", "🎁", "📷", "🎓", "🏆", "🌿", "🔬",
    "🎬", "🏡", "💡", "🗂️", "📊", "🧩", "🚀", "🎪",
]

_CAT_PRESET_COLORS = [
    "#E53E3E",  # czerwony
    "#DD6B20",  # pomarańczowy
    "#D69E2E",  # żółty
    "#38A169",  # zielony
    "#3182CE",  # niebieski
    "#0F52BA",  # accent blue
    "#805AD5",  # fioletowy
    "#D53F8C",  # różowy
    "#2D3748",  # ciemnoszary
    "#718096",  # szary
]


class _CategoryDialog(ctk.CTkToplevel):
    """Dialog tworzenia nowej kategorii — picker emoji + kolor + live preview."""

    def __init__(self, parent, db, user, accent: str, accent_hover: str,
                 on_created=None):
        super().__init__(parent)
        self.geometry("+5000+5000")   # off-screen: CTk auto-deiconify flash niewidoczny
        self.wm_attributes("-alpha", 0.0)
        self.db           = db
        self.user         = user
        self.accent       = accent
        self.accent_hover = accent_hover
        self.on_created   = on_created

        self._selected_icon  = _EMOJI_PICKER[0]
        self._selected_color = _CAT_PRESET_COLORS[5]   # accent blue domyślnie
        self._emoji_btns: list[ctk.CTkButton] = []
        self._color_btns: list[ctk.CTkButton] = []

        self.transient(parent)
        self.title("Nowa kategoria")
        self.geometry("430x530")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.after(50, self._init_grab_and_build)

    # ── Inicjalizacja opóźniona (fix Windows/CTk blank window + grab) ──

    def _init_grab_and_build(self):
        self.lift()
        self.grab_set()
        self._build_ui()
        self.after(250, self._focus_entry)
        self.after(20, self._reveal)

    def _reveal(self):
        cx, cy = None, None
        try:
            par = self.master
            if par and par.winfo_exists():
                pw, ph = par.winfo_width(), par.winfo_height()
                px, py = par.winfo_rootx(), par.winfo_rooty()
                ww = self.winfo_reqwidth() or 430
                wh = self.winfo_reqheight() or 530
                cx = px + (pw - ww) // 2
                cy = py + (ph - wh) // 2
        except tk.TclError:
            pass
        # Okno startuje na +5000+5000 — deiconify flash alpha=1.0 jest off-screen
        self.deiconify()
        try:
            self.wm_attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        if cx is not None:
            try:
                self.geometry(f"+{cx}+{cy}")
            except tk.TclError:
                pass
        self.update_idletasks()
        def _fade(step=0, steps=5):
            if not self.winfo_exists():
                return
            try:
                self.wm_attributes("-alpha", (step + 1) / steps)
            except tk.TclError:
                pass
            if step + 1 < steps:
                self.after(6, lambda: _fade(step + 1, steps))
            else:
                try:
                    self.wm_attributes("-alpha", 1.0)
                except tk.TclError:
                    pass
        _fade()

    def _focus_entry(self):
        if hasattr(self, "_entry"):
            self._entry.focus_set()

    # ── UI ────────────────────────────────────────────────────────────

    def _build_ui(self):
        apply_hex_to_window(self)
        ctk.CTkLabel(
            self, text="➕ Nowa kategoria",
            font=ctk.CTkFont(size=17, weight="bold")
        ).pack(pady=(20, 4))

        self._title_sep = AnimatedGradientCanvas(
            self,
            accent=self.accent,
            base=_gcard(),
            anim_mode="slide",
            period_ms=6000,
            fps=20,
            n_bands=1,
            direction="h",
            steps=64,
            height=2,
        )
        self._title_sep.pack(fill="x", padx=18, pady=(0, 8))
        self._title_sep.start_animation()

        outer = ctk.CTkFrame(self, corner_radius=14)
        outer.pack(padx=18, fill="both", expand=True, pady=(0, 16))

        sc = ctk.CTkScrollableFrame(outer, corner_radius=0, fg_color="transparent")
        sc.pack(fill="both", expand=True)
        apply_hex_to_canvas(sc._parent_canvas, hex_size=36, glow_max=2, glow_interval_ms=1800)

        # ── Podgląd ──────────────────────────────────────────────────
        ctk.CTkLabel(sc, text="Podgląd", anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="gray").pack(padx=14, pady=(14, 4), fill="x")

        self._preview_lbl = ctk.CTkLabel(
            sc,
            text=f"{self._selected_icon}  Nowa kategoria",
            fg_color=self._selected_color,
            corner_radius=10,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="white",
            height=40,
        )
        self._preview_lbl.pack(padx=14, fill="x")

        # ── Emoji ─────────────────────────────────────────────────────
        ctk.CTkLabel(sc, text="Ikona", anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="gray").pack(padx=14, pady=(14, 4), fill="x")

        grid = ctk.CTkFrame(sc, fg_color=("gray88", "#252525"), corner_radius=10)
        grid.pack(padx=14, fill="x")

        COLS = 8
        for idx, emoji in enumerate(_EMOJI_PICKER):
            r, c = divmod(idx, COLS)
            btn = ctk.CTkButton(
                grid, text=emoji, width=36, height=32,
                fg_color="transparent",
                hover_color=("gray75", "#3a3a3a"),
                font=ctk.CTkFont(size=15), corner_radius=6,
                command=lambda e=emoji, i=idx: self._pick_emoji(e, i)
            )
            btn.grid(row=r, column=c, padx=1, pady=1)
            self._emoji_btns.append(btn)

        # Podświetl domyślny (pierwszy)
        self._emoji_btns[0].configure(fg_color=(self.accent, self.accent))

        # ── Kolory ────────────────────────────────────────────────────
        ctk.CTkLabel(sc, text="Kolor", anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="gray").pack(padx=14, pady=(14, 4), fill="x")

        color_row = ctk.CTkFrame(sc, fg_color=("gray88", "#252525"), corner_radius=10)
        color_row.pack(padx=14, fill="x")

        for i, color in enumerate(_CAT_PRESET_COLORS):
            btn = ctk.CTkButton(
                color_row, text="", width=32, height=32,
                fg_color=color, hover_color=color,
                corner_radius=16,
                border_width=3,
                border_color=color,
                command=lambda c=color, idx=i: self._pick_color(c, idx)
            )
            btn.pack(side="left", padx=(6 if i == 0 else 3, 3), pady=9)
            self._color_btns.append(btn)

        # Podświetl domyślny kolor (accent blue = index 5)
        self._color_btns[5].configure(border_color=("gray20", "white"))

        # ── Nazwa ─────────────────────────────────────────────────────
        ctk.CTkLabel(sc, text="Nazwa kategorii", anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="gray").pack(padx=14, pady=(14, 4), fill="x")

        self._entry = ctk.CTkEntry(
            sc, placeholder_text="np. Gaming, Projekty...",
            height=42, corner_radius=10
        )
        self._entry.pack(padx=14, fill="x")
        self._entry.focus()
        self._entry.bind("<KeyRelease>", lambda e: self._update_preview())
        self._entry.bind("<Return>",     lambda e: self._confirm())

        self._err_lbl = ctk.CTkLabel(
            sc, text="", font=ctk.CTkFont(size=11), text_color="#e05252", anchor="w"
        )
        self._err_lbl.pack(padx=14, pady=(4, 0), fill="x")

        # ── Przyciski ─────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(sc, fg_color="transparent")
        btn_row.pack(padx=14, pady=(12, 18), fill="x")

        ctk.CTkButton(
            btn_row, text="Anuluj", height=42,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"),
            hover_color=("gray85", "#2a2a2a"),
            text_color=("gray20", "gray80"),
            corner_radius=10,
            command=self.destroy
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            btn_row, text="➕ Dodaj kategorię", height=42,
            fg_color=self.accent, hover_color=self.accent_hover,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=10,
            command=self._confirm
        ).pack(side="left", fill="x", expand=True, padx=(6, 0))

    # ── Logika ────────────────────────────────────────────────────────

    def _pick_emoji(self, emoji: str, idx: int):
        self._selected_icon = emoji
        for i, btn in enumerate(self._emoji_btns):
            btn.configure(fg_color=(self.accent, self.accent) if i == idx else "transparent")
        self._update_preview()

    def _pick_color(self, color: str, idx: int):
        self._selected_color = color
        for i, btn in enumerate(self._color_btns):
            btn.configure(border_color=("gray20", "white") if i == idx else _CAT_PRESET_COLORS[i])
        self._update_preview()

    def _update_preview(self):
        name    = self._entry.get().strip() if hasattr(self, "_entry") else ""
        display = f"{self._selected_icon}  {name or 'Nowa kategoria'}"
        try:
            self._preview_lbl.configure(text=display, fg_color=self._selected_color)
        except tk.TclError:
            pass

    def _confirm(self):
        name = self._entry.get().strip()
        if not name:
            self._err_lbl.configure(text="Podaj nazwę kategorii.")
            return
        result = self.db.add_custom_category(
            self.user, name,
            color=self._selected_color,
            icon=self._selected_icon
        )
        if result is None:
            self._err_lbl.configure(text=f'Kategoria „{name}" już istnieje.')
            return
        self.destroy()
        if self.on_created:
            self.on_created(name, self._selected_icon)

    def destroy(self):
        try:
            self._title_sep.stop_animation()
        except Exception:
            pass
        super().destroy()


# ──────────────────────────────────────────────
# OKNO KOSZA
# ──────────────────────────────────────────────

class TrashWindow(ctk.CTkToplevel):
    def __init__(self, parent, db, crypto, user, on_refresh):
        super().__init__(parent)
        self.geometry("+5000+5000")   # off-screen: CTk auto-deiconify flash niewidoczny
        self.wm_attributes("-alpha", 0.0)
        self.db         = db
        self.crypto     = crypto
        self.user       = user
        self.on_refresh = on_refresh

        self.title("Kosz")
        self.geometry("580x500")
        self.resizable(False, True)
        self.grab_set()
        self.focus()
        self._build_ui()
        self.after(20, self._reveal)

    def _build_ui(self):
        apply_hex_to_window(self)
        _hdr_tint = _blend_accent(ACCENT, _gcard(), 0.18)
        hdr_outer = ctk.CTkFrame(self, fg_color=("gray92", _hdr_tint),
                                 corner_radius=0, height=62)
        hdr_outer.pack(fill="x")
        hdr_outer.pack_propagate(False)

        ctk.CTkLabel(hdr_outer, text="🗑️  Kosz",
                     font=ctk.CTkFont(size=19, weight="bold")).pack(
            side="left", padx=20, pady=14)

        ctk.CTkButton(
            hdr_outer, text="Wyczyść kosz", width=130, height=34,
            fg_color=("#ffdddd", "#4a1a1a"), hover_color=("#ffcccc", "#5a2020"),
            text_color=("#c0392b", "#ff8080"), corner_radius=8,
            command=self._purge_all
        ).pack(side="right", padx=20)

        self._title_sep = AnimatedGradientCanvas(
            self,
            accent=ACCENT,
            base=_gcard(),
            anim_mode="slide",
            period_ms=6000,
            fps=20,
            n_bands=1,
            direction="h",
            steps=128,
            height=2,
        )
        self._title_sep.pack(fill="x")
        self._title_sep.start_animation()

        ctk.CTkLabel(
            self, text="Hasła w koszu są trwale usuwane po 30 dniach.",
            font=ctk.CTkFont(size=11), text_color="gray"
        ).pack(padx=20, anchor="w", pady=(8, 4))

        self.scroll = ctk.CTkScrollableFrame(self, corner_radius=12,
                                              fg_color=(LIGHT_BG, DARK_BG))
        self.scroll.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        apply_hex_to_canvas(self.scroll._parent_canvas, hex_size=36, glow_max=2, glow_interval_ms=1800)
        self._load()

    def _reveal(self):
        cx, cy = None, None
        try:
            par = self.master
            if par and par.winfo_exists():
                pw, ph = par.winfo_width(), par.winfo_height()
                px, py = par.winfo_rootx(), par.winfo_rooty()
                ww = self.winfo_reqwidth() or 580
                wh = self.winfo_reqheight() or 500
                cx = px + (pw - ww) // 2
                cy = py + (ph - wh) // 2
        except tk.TclError:
            pass
        # Okno startuje na +5000+5000 — deiconify flash alpha=1.0 jest off-screen
        self.deiconify()
        try:
            self.wm_attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        if cx is not None:
            try:
                self.geometry(f"+{cx}+{cy}")
            except tk.TclError:
                pass
        self.update_idletasks()
        def _fade(step=0, steps=5):
            if not self.winfo_exists():
                return
            try:
                self.wm_attributes("-alpha", (step + 1) / steps)
            except tk.TclError:
                pass
            if step + 1 < steps:
                self.after(6, lambda: _fade(step + 1, steps))
            else:
                try:
                    self.wm_attributes("-alpha", 1.0)
                except tk.TclError:
                    pass
        _fade()

    def _load(self):
        for w in self.scroll.winfo_children():
            w.destroy()

        entries = self.db.get_trashed_passwords(self.user)
        if not entries:
            ctk.CTkLabel(self.scroll, text="Kosz jest pusty.",
                         font=ctk.CTkFont(size=13), text_color="gray").pack(pady=40)
            return

        for entry in entries:
            self._trash_row(entry)

    def _trash_row(self, entry):
        row = ctk.CTkFrame(self.scroll, corner_radius=10,
                           fg_color=(LIGHT_ROW, DARK_ROW))
        row.pack(fill="x", pady=3, padx=4)

        info = ctk.CTkFrame(row, fg_color="transparent", height=1)
        info.pack(side="left", fill="both", expand=True, padx=12, pady=8)

        ctk.CTkLabel(info, text=entry.title,
                     font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(fill="x")

        days_left = ""
        if entry.deleted_at:
            from database.db_manager import TRASH_DAYS
            removed = (datetime.now(timezone.utc) - entry.deleted_at).days
            left    = TRASH_DAYS - removed
            days_left = f"Usunięto: {entry.deleted_at.strftime('%d.%m.%Y')}  •  Pozostało {left} dni"
        ctk.CTkLabel(info, text=days_left, font=ctk.CTkFont(size=10),
                     text_color="gray", anchor="w").pack(fill="x")

        btns = ctk.CTkFrame(row, fg_color="transparent", height=1)
        btns.pack(side="right", padx=8, pady=8)

        ctk.CTkButton(
            btns, text="↩ Przywróć", width=90, height=30,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=8,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda e=entry: self._restore(e)
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btns, text="🗑 Usuń", width=72, height=30,
            fg_color=("#ffdddd", "#4a1a1a"), hover_color=("#ffcccc", "#5a2020"),
            text_color=("#c0392b", "#ff8080"), corner_radius=8,
            font=ctk.CTkFont(size=11),
            command=lambda e=entry: self._delete_permanent(e)
        ).pack(side="left", padx=2)

    def _restore(self, entry):
        self.db.restore_password(entry)
        self.on_refresh()
        self._load()

    def _delete_permanent(self, entry):
        if ask_yes_no("Usuń permanentnie",
                      f"Trwale usunąć '{entry.title}'? Tej operacji nie można cofnąć.",
                      parent=self, yes_text="Usuń", destructive=True):
            self.db.delete_password(entry)
            self._load()

    def _purge_all(self):
        entries = self.db.get_trashed_passwords(self.user)
        if not entries:
            return
        if ask_yes_no("Wyczyść kosz",
                      f"Trwale usunąć wszystkie {len(entries)} haseł w koszu?",
                      parent=self, yes_text="Wyczyść", destructive=True):
            for e in entries:
                self.db.delete_password(e)
            self._load()

    def destroy(self):
        try:
            self._title_sep.stop_animation()
        except Exception:
            pass
        super().destroy()


# ──────────────────────────────────────────────
# WSPÓLNA LOGIKA KOPIOWANIA
# ──────────────────────────────────────────────

def _do_copy(entry, db, crypto, on_copy=None):
    """Wspólna logika kopiowania hasła do schowka (używana przez PasswordRow i PasswordCard)."""
    try:
        plaintext = db.decrypt_password(entry, crypto)
        pyperclip.copy(plaintext)
        db.mark_used(entry)
        if on_copy:
            on_copy(entry.title)
    except Exception:
        pass


# ──────────────────────────────────────────────
# KARTA HASŁA (widok siatki)
# ──────────────────────────────────────────────

class PasswordCard(ctk.CTkFrame):
    """Kafelek hasła w widoku siatki (2 kolumny)."""

    def __init__(self, parent, entry, db, crypto, user, on_refresh, on_copy,
                 category_colors: dict = None, strength_color: str = "#718096",
                 strength_score: int = 2, is_favorite: int = 0):
        super().__init__(parent, corner_radius=16,
                         fg_color=(LIGHT_ROW, DARK_ROW),
                         border_width=1,
                         border_color=("#e8e8e8", "#3a3a3a"),
                         height=160)
        self.pack_propagate(False)
        self.entry          = entry
        self.db             = db
        self.crypto         = crypto
        self.user           = user
        self.on_refresh     = on_refresh
        self.on_copy        = on_copy
        self.cat_colors     = category_colors or DEFAULT_CATEGORY_COLORS
        self.strength_color = strength_color
        self.strength_score = strength_score
        self.is_favorite    = is_favorite
        self._copy_btn      = None
        self._build()
        self._bind_hover()

    def _build(self):
        cat_color = self.cat_colors.get(self.entry.category or "Inne", "#718096")
        initial   = (self.entry.title or "?")[0].upper()

        # Gwiazdka ulubionych — prawy górny róg
        fav_lbl = ctk.CTkLabel(
            self, text="★" if self.is_favorite else "",
            font=ctk.CTkFont(size=14), text_color="#f0a500",
        )
        fav_lbl.place(relx=1.0, rely=0.0, x=-10, y=8, anchor="ne")

        # Avatar
        avatar = ctk.CTkLabel(
            self, text=initial, width=60, height=60,
            fg_color=cat_color, corner_radius=12,
            font=ctk.CTkFont(size=22, weight="bold"), text_color="white"
        )
        avatar.place(relx=0.5, y=20, anchor="n")

        # Tytuł
        ctk.CTkLabel(
            self, text=self.entry.title,
            font=ctk.CTkFont(size=12, weight="bold"), anchor="center",
            wraplength=130
        ).place(relx=0.5, y=92, anchor="n")

        # Username
        if self.entry.username:
            ctk.CTkLabel(
                self, text=self.entry.username,
                font=ctk.CTkFont(size=10), text_color="gray", anchor="center",
                wraplength=130
            ).place(relx=0.5, y=114, anchor="n")

        # Pasek siły (3px, dół karty)
        _str_bar = tk.Canvas(
            self, height=3, bd=0, highlightthickness=0,
            bg=self.strength_color
        )
        _str_bar.place(relx=0, rely=1.0, x=10, y=-10, relwidth=1.0, width=-20, anchor="sw")

        # Przycisk Kopiuj (ukryty, pojawia się na hover)
        self._copy_btn = ctk.CTkButton(
            self, text="📋 Kopiuj", height=28, width=100,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            corner_radius=8, font=ctk.CTkFont(size=11, weight="bold"),
            command=self._copy
        )
        # Nie pakujemy — pojawi się na hover

    def _bind_hover(self):
        is_dark = ctk.get_appearance_mode() == "Dark"
        base    = DARK_ROW if is_dark else LIGHT_ROW
        hover_c = _blend_accent(ACCENT, base, 0.13)
        normal  = (LIGHT_ROW, DARK_ROW)
        bind_hover_smooth(self, normal_color=normal, hover_color=hover_c)

        def _enter(e):
            if self._copy_btn and self._copy_btn.winfo_exists():
                self._copy_btn.place(relx=0.5, rely=1.0, y=-12, anchor="s")

        def _leave(e):
            if self._copy_btn and self._copy_btn.winfo_exists():
                self._copy_btn.place_forget()

        self.bind("<Enter>", _enter)
        self.bind("<Leave>", _leave)

        # Border glow na hover: neutral → ACCENT
        is_dark = ctk.get_appearance_mode() == "Dark"
        neutral_border = "#e8e8e8" if not is_dark else "#3a3a3a"

        def _enter_border(e):
            try:
                animate_color(self, neutral_border, ACCENT,
                              lambda c: self.configure(border_color=c),
                              steps=8, interval_ms=12)
            except Exception:
                pass

        def _leave_border(e):
            try:
                animate_color(self, ACCENT, neutral_border,
                              lambda c: self.configure(border_color=c),
                              steps=8, interval_ms=12)
            except Exception:
                pass

        self.bind("<Enter>", _enter_border, add="+")
        self.bind("<Leave>", _leave_border, add="+")

        # Smooth scale: subtelna zmiana wysokości 160→166 na hover
        try:
            from utils.easing import smoothstep as _ss
        except ImportError:
            _ss = lambda t: t * t * (3 - 2 * t)

        _HEIGHT_NORMAL = 160
        _HEIGHT_HOVER  = 166
        _STEPS         = 8
        _INTERVAL_MS   = 12

        # Przechowujemy ID after() żeby móc anulować trwającą animację
        self._scale_after_id = None
        self._scale_destroyed = False

        def _cancel_scale():
            if self._scale_after_id is not None:
                try:
                    self.after_cancel(self._scale_after_id)
                except Exception:
                    pass
                self._scale_after_id = None

        def _animate_height(target_h: int, step: int = 0):
            if self._scale_destroyed:
                return
            try:
                if not self.winfo_exists():
                    return
            except Exception:
                return

            start_h = _HEIGHT_NORMAL if target_h == _HEIGHT_HOVER else _HEIGHT_HOVER
            t = _ss((step + 1) / _STEPS)
            new_h = int(start_h + (target_h - start_h) * t)
            try:
                self.configure(height=new_h)
            except Exception:
                return

            if step + 1 < _STEPS:
                self._scale_after_id = self.after(
                    _INTERVAL_MS,
                    lambda: _animate_height(target_h, step + 1)
                )
            else:
                self._scale_after_id = None

        def _enter_scale(e):
            _cancel_scale()
            _animate_height(_HEIGHT_HOVER)

        def _leave_scale(e):
            _cancel_scale()
            _animate_height(_HEIGHT_NORMAL)

        def _on_destroy(e):
            self._scale_destroyed = True
            _cancel_scale()

        self.bind("<Enter>", _enter_scale, add="+")
        self.bind("<Leave>", _leave_scale, add="+")
        self.bind("<Destroy>", _on_destroy, add="+")

    def _copy(self):
        try:
            from gui.animations import ripple_copy
            btn = getattr(self, "_copy_btn", None)
            if btn and btn.winfo_exists():
                ripple_copy(btn)
        except Exception:
            pass
        _do_copy(self.entry, self.db, self.crypto, self.on_copy)

    def update_accent(self, accent: str, accent_hover: str):
        """Aktualizuje kolor akcentu in-place — bez przebudowy wiersza."""
        btn = getattr(self, "_copy_btn", None)
        if btn and btn.winfo_exists():
            try:
                btn.configure(fg_color=accent, hover_color=accent_hover)
            except tk.TclError:
                pass

    def update_mode(self, is_dark: bool):
        """Aktualizuje kolory karty po zmianie trybu jasny/ciemny.

        Analogicznie jak PasswordRow — wymuszamy jawne configure() bo CTK
        może nie propagować tuple fg_color do dzieci CTkScrollableFrame.
        """
        border = "#3a3a3a" if is_dark else "#e8e8e8"
        card_bg = DARK_ROW if is_dark else LIGHT_ROW
        try:
            self.configure(
                fg_color=(LIGHT_ROW, DARK_ROW),
                border_color=border,
            )
        except tk.TclError:
            pass

        # Przelicz nowy kolor hover i zarejestruj
        hover = _blend_accent(ACCENT, card_bg, alpha=0.13)
        try:
            bind_hover_smooth(self, normal_color=(LIGHT_ROW, DARK_ROW), hover_color=hover)
        except Exception:
            pass


# ──────────────────────────────────────────────
# PODGLĄD HASŁA (dymek hover)
# ──────────────────────────────────────────────

class _PasswordPreview(tk.Toplevel):
    """Dymek podglądu hasła — pojawia się po ~700ms hover na wierszu.
    Pokazuje: username, URL, kategoria, notatki, data użycia, mini-pasek siły.
    """

    def __init__(self, anchor_widget, entry, db, crypto,
                 strength_color: str = None, strength_score: int = None):
        super().__init__(anchor_widget)
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self._alive = True

        # Start invisible, off-screen
        self.geometry(f"240x10+-2000+-2000")
        try:
            self.wm_attributes("-alpha", 0.0)
        except tk.TclError:
            pass

        is_dark = ctk.get_appearance_mode() == "Dark"
        bg     = "#202020" if is_dark else "#ffffff"
        fg     = "#e8e8e8" if is_dark else "#1a1a1a"
        sub_fg = "#a0a0a0" if is_dark else "#666666"
        border = "#3a3a3a" if is_dark else "#d0d0d0"
        accent = ACCENT

        self.configure(bg=border)
        outer = tk.Frame(self, bg=border, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=bg, padx=12, pady=10)
        inner.pack(fill="both", expand=True)

        # Title
        tk.Label(inner, text=entry.title, bg=bg, fg=fg,
                 font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x")

        # Thin separator
        tk.Frame(inner, height=1, bg=border).pack(fill="x", pady=(5, 8))

        # Helper to add a row
        def _row(icon, text, color=None):
            if not text:
                return
            f = tk.Frame(inner, bg=bg)
            f.pack(fill="x", pady=1)
            tk.Label(f, text=icon, bg=bg, fg=accent,
                     font=("Segoe UI", 10), width=2, anchor="w").pack(side="left")
            tk.Label(f, text=str(text)[:60], bg=bg, fg=color or fg,
                     font=("Segoe UI", 10), anchor="w").pack(side="left")

        _row("👤", entry.username or "—")
        if entry.url:
            _row("🌐", entry.url[:50] + ("…" if len(entry.url) > 50 else ""))
        _row("🏷", entry.category or "Inne")
        if entry.notes:
            notes = entry.notes[:55] + ("…" if len(entry.notes) > 55 else "")
            _row("📝", notes, color=sub_fg)
        if entry.last_used_at:
            _row("⏱", f"Ostatnio: {entry.last_used_at.strftime('%d.%m.%Y')}", color=sub_fg)

        # Mini strength bar — użyj pre-computed wartości jeśli dostępne
        try:
            if strength_color is not None and strength_score is not None:
                bar_color = strength_color
                frac = (strength_score + 1) / 5.0
            else:
                plain = db.decrypt_password(entry, crypto)
                sc = check_strength(plain)
                bar_color = sc["color"]
                frac = (sc["score"] + 1) / 5.0
            bar_row = tk.Frame(inner, bg=bg)
            bar_row.pack(fill="x", pady=(6, 0))
            tk.Label(bar_row, text="Siła:", bg=bg, fg=sub_fg,
                     font=("Segoe UI", 9)).pack(side="left")
            bar_cv = tk.Canvas(bar_row, height=4, width=110,
                               bg=border, highlightthickness=0)
            bar_cv.pack(side="left", padx=(6, 0))
            bar_cv.create_rectangle(0, 0, int(110 * frac), 4,
                                    fill=bar_color, outline="")
        except Exception:
            pass

        # Position and show after layout
        self.after(20, lambda: self._place(anchor_widget))

    def _place(self, anchor):
        if not self._alive:
            return
        try:
            self.update_idletasks()
            ax = anchor.winfo_rootx()
            ay = anchor.winfo_rooty()
            aw = anchor.winfo_width()
            ah = anchor.winfo_height()
            pw = self.winfo_reqwidth()
            ph = self.winfo_reqheight()
            sw = anchor.winfo_screenwidth()
            sh = anchor.winfo_screenheight()

            # Try right side first, then left
            x = ax + aw + 6
            if x + pw > sw:
                x = ax - pw - 6
            y = ay
            if y + ph > sh:
                y = sh - ph - 10

            self.geometry(f"{pw}x{ph}+{x}+{y}")
            self._fade_in()
        except tk.TclError:
            pass

    def _fade_in(self, step: int = 0):
        if not self._alive:
            return
        try:
            self.wm_attributes("-alpha", min(step / 6 * 0.93, 0.93))
            if step < 6:
                self.after(16, lambda: self._fade_in(step + 1))
        except tk.TclError:
            pass

    def close(self):
        self._alive = False
        try:
            self.destroy()
        except tk.TclError:
            pass


# ──────────────────────────────────────────────
# WIERSZ HASŁA
# ──────────────────────────────────────────────

class PasswordRow(ctk.CTkFrame):
    def __init__(self, parent, entry, db, crypto, user, on_refresh, on_copy,
                 category_colors: dict = None, compact: bool = False,
                 strength_color: str = "#718096", strength_score: int = 2,
                 is_favorite: int = 0, on_autotype=None, highlight_query: str = ""):
        is_dark = ctk.get_appearance_mode() == "Dark"
        _h = 36 if compact else 74
        super().__init__(parent, corner_radius=12,
                         fg_color=(LIGHT_ROW, DARK_ROW), border_width=1,
                         border_color=("#e8e8e8" if not is_dark else "#3a3a3a"),
                         height=_h)
        self.pack_propagate(False)
        self.entry           = entry
        self.db              = db
        self.crypto          = crypto
        self.user            = user
        self.on_refresh      = on_refresh
        self.on_copy         = on_copy
        self.category_colors = category_colors or DEFAULT_CATEGORY_COLORS
        self.compact         = compact
        self.strength_color  = strength_color
        self.strength_score  = strength_score
        self.is_favorite     = is_favorite
        self.on_autotype     = on_autotype
        self.highlight_query = highlight_query.lower()
        self._expanded       = False
        self._detail_frame   = None
        self._plain_pwd      = None
        self._collapsed_h    = _h
        self._build()
        self._apply_hover()
        self._bind_preview_hover()

    def _build(self):
        cat_color = self.category_colors.get(self.entry.category or "Inne", "#718096")
        initial   = (self.entry.title or "?")[0].upper()

        if self.compact:
            pad        = 3
            asz        = 26
            fsz        = 11
            btn_h      = 22
            bar_pady   = 5
        else:
            pad        = 8
            asz        = 38
            fsz        = 13
            btn_h      = 30
            bar_pady   = 8

        # ── Pasek siły hasła (lewy border — animowany kolor) ─────────
        self._str_bar = ctk.CTkFrame(
            self, width=4, corner_radius=2, fg_color="#555555"
        )
        self._str_bar.pack(side="left", fill="y", pady=bar_pady, padx=(6, 0))
        animate_strength_bar(self._str_bar, self.strength_color)

        avatar = ctk.CTkLabel(
            self, text=initial, width=asz, height=asz,
            fg_color=cat_color, corner_radius=8 if self.compact else 10,
            font=ctk.CTkFont(size=fsz + 2, weight="bold"), text_color="white"
        )
        avatar.pack(side="left", padx=(8, 0), pady=pad)
        avatar.bind("<Button-1>", self._toggle_expand)

        # ── Panel info ────────────────────────────────────────────────
        info = ctk.CTkFrame(self, fg_color="transparent", height=1)
        info.pack(side="left", fill="both", expand=True,
                  padx=(10, 4) if self.compact else 12, pady=pad)
        # Kliknięcie na info (tekst) lub avatar → accordion. NIE bindujemy self (cały wiersz),
        # bo to triggerowałoby też kliknięcia w przyciski i powodowało podwójne zdarzenia.
        info.bind("<Button-1>", self._toggle_expand)

        if self.compact:
            # Jedna linia: tytuł  ·  username (+ badge wygaśnięcia inline)
            single_row = ctk.CTkFrame(info, fg_color="transparent", height=1)
            single_row.pack(fill="x", anchor="w")

            self._make_title_widget(single_row, fsz)

            exp = self.entry.expiry_status
            if exp in ("expired", "soon"):
                days = max(0, (self.entry.expires_at - datetime.now(timezone.utc)).days) if self.entry.expires_at else 0
                self._make_expiry_badge(single_row, days, is_expired=(exp == "expired"))

            if self.entry.username:
                ctk.CTkLabel(single_row,
                             text=f"  ·  {self.entry.username}",
                             font=ctk.CTkFont(size=fsz - 1),
                             text_color="gray", anchor="w").pack(side="left")
        else:
            # Dwie linie: tytuł + username/url, plus badge kategorii
            title_row = ctk.CTkFrame(info, fg_color="transparent", height=1)
            title_row.pack(fill="x")

            self._make_title_widget(title_row, fsz)

            exp = self.entry.expiry_status
            if exp in ("expired", "soon"):
                days = max(0, (self.entry.expires_at - datetime.now(timezone.utc)).days) if self.entry.expires_at else 0
                self._make_expiry_badge(title_row, days, is_expired=(exp == "expired"))

            sub = self.entry.username or "—"
            if self.entry.url:
                sub += f"   •   {self.entry.url}"
            ctk.CTkLabel(info, text=sub, font=ctk.CTkFont(size=11),
                         text_color="gray", anchor="w").pack(fill="x")

            ctk.CTkLabel(
                info, text=f"  {self.entry.category or 'Inne'}  ",
                font=ctk.CTkFont(size=10),
                fg_color=cat_color, corner_radius=6, text_color="white"
            ).pack(anchor="w", pady=(2, 0))

        # ── Przyciski ─────────────────────────────────────────────────
        btns = ctk.CTkFrame(self, fg_color="transparent", height=1)
        btns.pack(side="right", padx=8 if self.compact else 10, pady=pad)

        # Gwiazdka ulubionych
        fav_active = bool(self.is_favorite)
        self._fav_btn = ctk.CTkButton(
            btns, text="★" if fav_active else "☆",
            width=btn_h + 2, height=btn_h,
            fg_color=(("#fff8e1", "#2a2200") if fav_active else ("gray88", "#2a2a2a")),
            hover_color=("gray80", "#383838"),
            text_color=("#f0a500" if fav_active else ("gray50", "gray50")),
            corner_radius=6, font=ctk.CTkFont(size=12 if self.compact else 14),
            command=self._toggle_favorite
        )
        self._fav_btn.pack(side="left", padx=(0, 2))

        if self.compact:
            # Tryb kompaktowy — same ikony, bez tekstu
            self._copy_btn = ctk.CTkButton(
                btns, text="📋", width=btn_h + 6, height=btn_h,
                fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=6,
                font=ctk.CTkFont(size=13), command=self._copy
            )
            self._copy_btn.pack(side="left", padx=1)
            self._user_btn = ctk.CTkButton(
                btns, text="👤", width=btn_h + 4, height=btn_h,
                fg_color=("gray85", "#2a3a2a"), hover_color=("gray75", "#3a4a3a"),
                text_color=("gray30", "#90c090"),
                corner_radius=6, font=ctk.CTkFont(size=12), command=self._copy_username
            )
            self._user_btn.pack(side="left", padx=1)
            ctk.CTkButton(
                btns, text="⌨", width=btn_h + 4, height=btn_h,
                fg_color=("gray85", "#2a3a2a"), hover_color=("gray75", "#3a4a3a"),
                text_color=("gray20", "#90c090"),
                corner_radius=6, font=ctk.CTkFont(size=12), command=self._autotype
            ).pack(side="left", padx=1)
            ctk.CTkButton(
                btns, text="✎", width=btn_h + 4, height=btn_h,
                fg_color=("gray85", "#333333"), hover_color=("gray75", "#444444"),
                text_color=("gray10", "gray90"),
                corner_radius=6, font=ctk.CTkFont(size=13), command=self._edit
            ).pack(side="left", padx=1)
            ctk.CTkButton(
                btns, text="🗑", width=btn_h + 4, height=btn_h,
                fg_color=("#ffdddd", "#4a1a1a"), hover_color=("#ffcccc", "#5a2020"),
                text_color=("#c0392b", "#ff8080"),
                corner_radius=6, font=ctk.CTkFont(size=13), command=self._trash
            ).pack(side="left", padx=1)
        else:
            # Tryb normalny — przyciski z tekstem
            self._copy_btn = ctk.CTkButton(
                btns, text="📋 Kopiuj", width=80, height=btn_h,
                fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=8,
                font=ctk.CTkFont(size=12, weight="bold"), command=self._copy
            )
            self._copy_btn.pack(side="left", padx=2)
            self._user_btn = ctk.CTkButton(
                btns, text="👤 Login", width=78, height=btn_h,
                fg_color=("gray85", "#2a3a2a"), hover_color=("gray75", "#3a4a3a"),
                text_color=("gray30", "#90c090"),
                corner_radius=8, font=ctk.CTkFont(size=12), command=self._copy_username
            )
            self._user_btn.pack(side="left", padx=2)
            ctk.CTkButton(
                btns, text="⌨ Auto-type", width=96, height=btn_h,
                fg_color=("gray85", "#2a3a2a"), hover_color=("gray75", "#3a4a3a"),
                text_color=("gray20", "#90c090"),
                corner_radius=8, font=ctk.CTkFont(size=12), command=self._autotype
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                btns, text="✏️ Edytuj", width=76, height=btn_h,
                fg_color=("gray85", "#333333"), hover_color=("gray75", "#444444"),
                text_color=("gray10", "gray90"),
                corner_radius=8, font=ctk.CTkFont(size=12), command=self._edit
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                btns, text="🗑️ Kosz", width=72, height=btn_h,
                fg_color=("#ffdddd", "#4a1a1a"), hover_color=("#ffcccc", "#5a2020"),
                text_color=("#c0392b", "#ff8080"),
                corner_radius=8, font=ctk.CTkFont(size=12), command=self._trash
            ).pack(side="left", padx=2)

        self._bind_strength_tooltip(self._str_bar)

    # ── Accordion expand/collapse ─────────────────────────────────

    def _toggle_expand(self, event=None):
        self._expanded = not self._expanded
        if self._expanded:
            self._show_detail()
        else:
            self._hide_detail()

    def _show_detail(self):
        # Decrypt and cache the password
        try:
            self._plain_pwd = self.db.decrypt_password(self.entry, self.crypto)
        except Exception:
            self._plain_pwd = ""

        # Build detail frame as SIBLING (child of scroll_frame, after self)
        # This avoids overflow bugs caused by pack_propagate(False) on PasswordRow.
        self._detail_frame = ctk.CTkFrame(
            self.master, fg_color=("gray92", "#252525"), corner_radius=8
        )
        self._detail_frame.pack(fill="x", padx=8, pady=(0, 4))
        self._detail_frame.pack_configure(after=self)

        # Blokuj propagację kliknięć z panelu szczegółów do PasswordRow
        self._detail_frame.bind("<Button-1>", lambda e: "break")

        # ── Password row ───────────────────────────────────────────
        pwd_row = ctk.CTkFrame(self._detail_frame, fg_color="transparent", height=1)
        pwd_row.pack(fill="x", padx=10, pady=(8, 2))

        ctk.CTkLabel(pwd_row, text="🔑", font=ctk.CTkFont(size=13)).pack(side="left")

        self._pwd_var = tk.StringVar(value="••••••••••••")
        self._pwd_shown = False
        pwd_lbl = ctk.CTkLabel(
            pwd_row, textvariable=self._pwd_var,
            font=ctk.CTkFont(size=12, family="Courier"),
            anchor="w"
        )
        pwd_lbl.pack(side="left", padx=(6, 8))

        def _toggle_pwd():
            self._pwd_shown = not self._pwd_shown
            if self._pwd_shown:
                self._pwd_var.set(self._plain_pwd or "")
                show_btn.configure(text="🙈 Ukryj")
            else:
                self._pwd_var.set("••••••••••••")
                show_btn.configure(text="👁 Pokaż")

        show_btn = ctk.CTkButton(
            pwd_row, text="👁 Pokaż",
            width=74, height=22,
            fg_color=("gray80", "#3a3a3a"),
            hover_color=("gray70", "#444444"),
            text_color=("gray10", "gray90"),
            corner_radius=6, font=ctk.CTkFont(size=11),
            command=_toggle_pwd
        )
        show_btn.pack(side="left")

        # ── URL row ────────────────────────────────────────────────
        if self.entry.url:
            url_row = ctk.CTkFrame(self._detail_frame, fg_color="transparent", height=1)
            url_row.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(url_row, text="🔗", font=ctk.CTkFont(size=13)).pack(side="left")
            url_lbl = ctk.CTkLabel(
                url_row, text=self.entry.url,
                font=ctk.CTkFont(size=11), text_color=ACCENT,
                anchor="w", cursor="hand2"
            )
            url_lbl.pack(side="left", padx=(6, 0))
            _url = self.entry.url
            url_lbl.bind("<Button-1>", lambda e, u=_url: webbrowser.open(u))

        # ── Notes row ─────────────────────────────────────────────
        if self.entry.notes:
            notes_row = ctk.CTkFrame(self._detail_frame, fg_color="transparent", height=1)
            notes_row.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(notes_row, text="📝", font=ctk.CTkFont(size=13)).pack(side="left")
            snippet = self.entry.notes[:100]
            ctk.CTkLabel(
                notes_row, text=snippet,
                font=ctk.CTkFont(size=11), text_color="gray",
                anchor="w", wraplength=380
            ).pack(side="left", padx=(6, 0))

        # ── Strength bar (canvas 6px tall) ─────────────────────────
        strength_row = ctk.CTkFrame(self._detail_frame, fg_color="transparent", height=1)
        strength_row.pack(fill="x", padx=10, pady=(4, 2))

        score     = self.strength_score
        bar_color = self.strength_color
        bar_total = 260
        bar_fill  = int(bar_total * score / 4) if score <= 4 else bar_total

        strength_canvas = tk.Canvas(
            strength_row, height=6, width=bar_total,
            bg=("#d0d0d0" if ctk.get_appearance_mode() != "Dark" else "#3a3a3a"),
            highlightthickness=0, bd=0
        )
        strength_canvas.pack(side="left", anchor="w")

        if bar_fill > 0:
            rect = strength_canvas.create_rectangle(0, 0, 0, 6, fill=bar_color, outline="")
            _elapsed_str = [0.0]
            _dur_str = 400.0
            _destroyed_str = [False]
            strength_canvas.bind("<Destroy>",
                                 lambda _e: _destroyed_str.__setitem__(0, True), add="+")

            def _str_fn(dt_ms: float) -> bool:
                if _destroyed_str[0]:
                    return False
                _elapsed_str[0] += dt_ms
                t = min(_elapsed_str[0] / _dur_str, 1.0)
                from utils.easing import smoothstep as _ss
                w = int(bar_fill * _ss(t))
                try:
                    strength_canvas.coords(rect, 0, 0, w, 6)
                    return t < 1.0
                except tk.TclError:
                    return False

            try:
                get_scheduler(strength_canvas.winfo_toplevel()).add(_str_fn)
            except Exception:
                strength_canvas.coords(rect, 0, 0, bar_fill, 6)

        # ── Dates row ─────────────────────────────────────────────
        dates_row = ctk.CTkFrame(self._detail_frame, fg_color="transparent", height=1)
        dates_row.pack(fill="x", padx=10, pady=(2, 8))

        try:
            created_str = self.entry.created_at.strftime("%d.%m.%Y")
        except Exception:
            created_str = "—"
        try:
            updated_str = self.entry.updated_at.strftime("%d.%m.%Y")
        except Exception:
            updated_str = "—"

        ctk.CTkLabel(
            dates_row,
            text=f"Dodano: {created_str}  ·  Zmieniono: {updated_str}",
            font=ctk.CTkFont(size=10), text_color="gray", anchor="w"
        ).pack(side="left")

        # Animacja expand (wysokość od 1 do docelowej)
        self._detail_frame.pack_propagate(False)
        self._detail_frame.configure(height=1)

        def _expand_detail():
            target_h = self._detail_frame.winfo_reqheight() if self._detail_frame and self._detail_frame.winfo_exists() else 0
            if target_h <= 1:
                if self._detail_frame and self._detail_frame.winfo_exists():
                    self._detail_frame.after(20, _expand_detail)
                return
            steps = 10
            duration_ms = 200
            step_ms = max(1, duration_ms // steps)

            def _tick(step=0):
                if not self._detail_frame or not self._detail_frame.winfo_exists():
                    return
                if step > steps:
                    try:
                        self._detail_frame.configure(height=target_h)
                        self._detail_frame.pack_propagate(True)
                    except tk.TclError:
                        pass
                    return
                try:
                    h = max(1, int(target_h * min(_ease_back(step / steps), 1.1)))
                    self._detail_frame.configure(height=h)
                    self._detail_frame.after(step_ms, lambda: _tick(step + 1))
                except tk.TclError:
                    pass

            _tick()

        self._detail_frame.after(10, _expand_detail)

    def _hide_detail(self):
        if self._detail_frame is None:
            return
        frame = self._detail_frame
        self._detail_frame = None
        self._expanded = False

        try:
            current_h = frame.winfo_height()
        except tk.TclError:
            return

        if current_h <= 1:
            try:
                frame.pack_forget()
                frame.destroy()
            except tk.TclError:
                pass
            return

        frame.pack_propagate(False)
        steps = 8
        step_ms = 18

        def _tick(step=0):
            if step > steps:
                try:
                    frame.pack_forget()
                    frame.destroy()
                except tk.TclError:
                    pass
                return
            try:
                # ease_in_cubic: wolne wejście → szybkie zamknięcie
                t = 1.0 - _ease_in(step / steps)
                frame.configure(height=max(1, int(current_h * t)))
                frame.after(step_ms, lambda: _tick(step + 1))
            except tk.TclError:
                pass

        _tick()

    def _apply_hover(self):
        """Płynny hover-highlight na wierszu hasła.

        Kolor hover jest generowany dynamicznie z aktualnego ACCENT-u
        (20% nasycenie na tle wiersza), dzięki czemu działa z każdym motywem.
        """
        is_dark = ctk.get_appearance_mode() == "Dark"
        normal  = (LIGHT_ROW, DARK_ROW)
        # Subtelny tint: blend 12% ACCENT z tłem wiersza
        base    = DARK_ROW if is_dark else LIGHT_ROW
        hover   = _blend_accent(ACCENT, base, alpha=0.13)
        bind_hover_smooth(self, normal_color=normal, hover_color=hover)

    def _toggle_favorite(self):
        new_state = self.db.toggle_favorite(self.entry)
        self.is_favorite = int(new_state)
        if new_state:
            self._fav_btn.configure(
                text="★",
                fg_color=("#fff8e1", "#2a2200"),
                text_color="#f0a500",
            )
            # Pulse gwiazdki przy aktywacji
            btn = self._fav_btn
            def _pulse_star(sizes=(14, 18, 22, 18, 14), step=0):
                if step >= len(sizes):
                    return
                try:
                    btn.configure(font=ctk.CTkFont(size=sizes[step]))
                    btn.after(40, lambda: _pulse_star(sizes, step + 1))
                except tk.TclError:
                    pass
            _pulse_star()
        else:
            self._fav_btn.configure(
                text="☆",
                fg_color=("gray88", "#2a2a2a"),
                text_color=("gray50", "gray50"),
            )
        self.on_refresh()

    def _flash_copy_btn(self):
        """Krótki flash przycisku przy kopiowaniu (visual feedback)."""
        btn = getattr(self, "_copy_btn", None)
        if not btn or not btn.winfo_exists():
            return
        flash_color = "#6aaa6a"
        original_color = ACCENT
        animate_color(btn, original_color, flash_color,
                      lambda c: btn.configure(fg_color=c),
                      steps=4, interval_ms=25)
        btn.after(100, lambda: animate_color(
            btn, flash_color, original_color,
            lambda c: btn.configure(fg_color=c),
            steps=6, interval_ms=20
        ))

    def _copy(self):
        self._flash_copy_btn()
        # Ripple effect na przycisku
        btn = getattr(self, "_copy_btn", None)
        try:
            from gui.animations import ripple_copy
            if btn and btn.winfo_exists():
                ripple_copy(btn)
        except (ImportError, Exception):
            pass
        _do_copy(self.entry, self.db, self.crypto, self.on_copy)

    def _copy_username(self):
        username = self.entry.username or ""
        if not username:
            return
        try:
            import pyperclip
            pyperclip.copy(username)
        except Exception:
            pass
        if self.on_copy:
            # Brief visual feedback — flash the button
            btn = getattr(self, "_user_btn", None)
            if btn and btn.winfo_exists():
                try:
                    from gui.animations import animate_color
                    is_dark = ctk.get_appearance_mode() == "Dark"
                    base = "#2a3a2a" if is_dark else "gray85"
                    animate_color(btn, base, "#4caf50",
                                  lambda c: btn.configure(fg_color=c),
                                  steps=4, interval_ms=25)
                    btn.after(100, lambda: animate_color(
                        btn, "#4caf50", base,
                        lambda c: btn.configure(fg_color=c),
                        steps=6, interval_ms=20,
                    ))
                except Exception:
                    pass

    def _autotype(self):
        if self.on_autotype:
            self.on_autotype(self.entry)

    def _edit(self):
        form = PasswordFormWindow(self, self.db, self.crypto, self.user, entry=self.entry)
        self.wait_window(form)
        if form.result:
            self.on_refresh()

    def _animate_remove(self, on_done=None):
        """Fade-out + collapse przed usunięciem z listy."""
        steps = 8
        step_ms = 18
        try:
            current_h = self.winfo_height()
        except tk.TclError:
            if on_done:
                on_done()
            return

        if current_h <= 1:
            try:
                self.pack_forget()
            except tk.TclError:
                pass
            if on_done:
                on_done()
            return

        self.pack_propagate(False)

        def _tick(step=0):
            if step > steps:
                try:
                    self.pack_forget()
                except tk.TclError:
                    pass
                if on_done:
                    on_done()
                return
            try:
                # ease_in_cubic: wolne wyjście → szybkie zniknięcie
                t = 1.0 - _ease_in(step / steps)
                self.configure(height=max(1, int(current_h * t)))
                self.after(step_ms, lambda: _tick(step + 1))
            except tk.TclError:
                if on_done:
                    on_done()

        _tick()

    def _trash(self):
        if ask_yes_no("Do kosza", f"Przenieść '{self.entry.title}' do kosza?",
                      parent=self, yes_text="Do kosza", destructive=True):
            self.db.trash_password(self.entry)
            self._animate_remove(on_done=self.on_refresh)

    def _make_title_widget(self, parent, fsz: int):
        """Tworzy widget tytułu z opcjonalnym podświetleniem dopasowania.

        Jeśli highlight_query nie jest puste i pasuje do tytułu,
        renderuje 3 CTkLabel: [przed][MATCH][po]. Inaczej — jeden label.
        """
        title = self.entry.title
        q = self.highlight_query

        if q and q in title.lower():
            # Znajdź pozycję dopasowania (case-insensitive)
            idx = title.lower().find(q)
            before = title[:idx]
            match  = title[idx:idx + len(q)]
            after  = title[idx + len(q):]

            container = ctk.CTkFrame(parent, fg_color="transparent", height=1)
            container.pack(side="left", fill="x")

            if before:
                ctk.CTkLabel(
                    container, text=before,
                    font=ctk.CTkFont(size=fsz, weight="bold"),
                    anchor="w",
                ).pack(side="left")

            ctk.CTkLabel(
                container, text=match,
                font=ctk.CTkFont(size=fsz, weight="bold"),
                text_color=(ACCENT, ACCENT),
                anchor="w",
            ).pack(side="left")

            if after:
                ctk.CTkLabel(
                    container, text=after,
                    font=ctk.CTkFont(size=fsz, weight="bold"),
                    anchor="w",
                ).pack(side="left")

            return container
        else:
            # Brak dopasowania — standardowy label
            lbl = ctk.CTkLabel(
                parent, text=title,
                font=ctk.CTkFont(size=fsz, weight="bold"),
                anchor="w",
            )
            lbl.pack(side="left")
            return lbl

    def _make_expiry_badge(self, parent_frame, days: int, is_expired: bool) -> "ctk.CTkFrame":
        """Tworzy małą odznakę z łukiem kołowym (16×16px) + tekst."""
        # Color
        if is_expired:
            color = "#e05252"
            label = "  ⛔"
        elif days <= 3:
            color = "#e05252"
            label = f"  {days}d"
        else:
            color = "#f0a500"
            label = f"  {days}d"

        # Container
        container = ctk.CTkFrame(parent_frame, fg_color="transparent", height=1)
        container.pack(side="left", padx=(4, 0))

        # Mały canvas (pierścień)
        is_dark = ctk.get_appearance_mode() == "Dark"
        cv_bg = "#1e1e1e" if is_dark else "#ffffff"
        cv = tk.Canvas(container, width=16, height=16, bg=cv_bg, highlightthickness=0)
        cv.pack(side="left")

        # Tło (szary pełny okrąg)
        cv.create_oval(1, 1, 15, 15, outline="#555555", width=2, fill="")

        # Łuk (kolorowy — proporcjonalny do dni)
        if is_expired:
            # Pełny czerwony okrąg
            cv.create_oval(1, 1, 15, 15, outline=color, width=2.5, fill="")
        else:
            # Łuk proporcjonalny: 7 dni = pełny, 0 dni = pusty
            fraction = max(0.0, min(days / 7.0, 1.0))
            extent = fraction * 359  # stop = extent degrees
            if extent > 0:
                cv.create_arc(1, 1, 15, 15, start=90, extent=-extent,
                              outline=color, width=2.5, style="arc")

        # Tekst
        ctk.CTkLabel(container, text=label, font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=color).pack(side="left")

        return container

    def _bind_strength_tooltip(self, bar_widget):
        """Pokazuje tooltip z checklistą siły hasła po 400ms hover na pasku siły."""
        self._str_tip_job = None
        self._str_tip_win = None

        def _cancel(e=None):
            if self._str_tip_job:
                self.after_cancel(self._str_tip_job)
                self._str_tip_job = None

        def _destroy_tip():
            if self._str_tip_win:
                try:
                    self._str_tip_win.destroy()
                except tk.TclError:
                    pass
                self._str_tip_win = None

        def _schedule(e=None):
            _cancel()
            self._str_tip_job = self.after(400, _show)

        def _hide(e=None):
            _cancel()
            _destroy_tip()

        def _show():
            if self._str_tip_win:
                try:
                    if self._str_tip_win.winfo_exists():
                        return
                except tk.TclError:
                    pass

            # Odszyfruj hasło i policz siłę w osobnym wątku
            import threading

            def _compute():
                try:
                    result = check_strength(self._plain_pwd or "")
                    checklist = result.get("checklist", [])
                    label = result.get("label", "")
                except Exception:
                    checklist = []
                    label = ""
                # Wróć na wątek UI
                try:
                    self.after(0, lambda: _build_tooltip(checklist, label))
                except tk.TclError:
                    pass

            threading.Thread(target=_compute, daemon=True).start()

        def _build_tooltip(checklist, label):
            # Sprawdź czy widget nadal istnieje
            try:
                if not bar_widget.winfo_exists():
                    return
            except tk.TclError:
                return

            _destroy_tip()

            is_dark = ctk.get_appearance_mode() == "Dark"
            bg      = "#1e1e1e" if is_dark else "#ffffff"
            fg      = "#e8e8e8" if is_dark else "#1a1a1a"
            sub_fg  = "#a0a0a0" if is_dark else "#666666"
            border  = "#3a3a3a" if is_dark else "#d0d0d0"

            tip = tk.Toplevel(self)
            tip.overrideredirect(True)
            tip.wm_attributes("-topmost", True)
            tip.geometry(f"10x10+-2000+-2000")
            try:
                tip.wm_attributes("-alpha", 0.0)
            except tk.TclError:
                pass

            self._str_tip_win = tip

            # Ramka zewnętrzna (border)
            outer = tk.Frame(tip, bg=border, padx=1, pady=1)
            outer.pack(fill="both", expand=True)

            inner = tk.Frame(outer, bg=bg, padx=12, pady=8)
            inner.pack(fill="both", expand=True)

            # Nagłówek
            header_row = tk.Frame(inner, bg=bg)
            header_row.pack(fill="x", pady=(0, 4))
            tk.Label(
                header_row, text="🔐 Siła hasła",
                bg=bg, fg=fg,
                font=("Segoe UI", 11, "bold"), anchor="w"
            ).pack(side="left")
            if label:
                # Kolor etykiety na bazie strength_color
                tk.Label(
                    header_row, text=f"  {label}",
                    bg=bg, fg=self.strength_color,
                    font=("Segoe UI", 10), anchor="w"
                ).pack(side="left")

            # Separator
            tk.Frame(inner, height=1, bg=border).pack(fill="x", pady=(0, 6))

            # Checklista
            if checklist:
                for item in checklist:
                    met  = item.get("met", False)
                    text = item.get("text", "")
                    icon = "✅" if met else "❌"
                    color = fg if met else sub_fg

                    row = tk.Frame(inner, bg=bg)
                    row.pack(fill="x", pady=1)
                    tk.Label(
                        row, text=icon,
                        bg=bg, font=("Segoe UI", 10),
                        width=2, anchor="w"
                    ).pack(side="left")
                    tk.Label(
                        row, text=text,
                        bg=bg, fg=color,
                        font=("Segoe UI", 10), anchor="w"
                    ).pack(side="left")
            else:
                tk.Label(
                    inner, text="Brak danych",
                    bg=bg, fg=sub_fg,
                    font=("Segoe UI", 10)
                ).pack(anchor="w")

            # Pozycjonuj i wygaś in
            tip.after(20, lambda: _place_and_fade(tip, bar_widget))

        def _place_and_fade(tip, anchor):
            try:
                if not tip.winfo_exists():
                    return
                tip.update_idletasks()
                ax = anchor.winfo_rootx()
                ay = anchor.winfo_rooty()
                aw = anchor.winfo_width()
                ah = anchor.winfo_height()
                pw = tip.winfo_reqwidth()
                ph = tip.winfo_reqheight()
                sw = anchor.winfo_screenwidth()
                sh = anchor.winfo_screenheight()

                # Preferuj po prawej stronie paska, potem po lewej
                x = ax + aw + 8
                if x + pw > sw:
                    x = ax - pw - 8
                y = ay + ah // 2 - ph // 2
                if y < 0:
                    y = 0
                if y + ph > sh:
                    y = sh - ph - 10

                tip.geometry(f"{pw}x{ph}+{x}+{y}")
                _fade_in(tip, 0)
            except tk.TclError:
                pass

        def _fade_in(tip, step):
            try:
                if not tip.winfo_exists():
                    return
                tip.wm_attributes("-alpha", min(step / 6 * 0.95, 0.95))
                if step < 6:
                    tip.after(16, lambda: _fade_in(tip, step + 1))
            except tk.TclError:
                pass

        # Bindujemy na pasku i na widgecie self (dla spójności z resztą hover)
        bar_widget.bind("<Enter>", _schedule, add="+")
        bar_widget.bind("<Leave>", _hide, add="+")
        bar_widget.bind("<Destroy>", lambda e: (_cancel(), _destroy_tip()), add="+")

    def _bind_preview_hover(self):
        """Łączy hover na wierszu z pokazaniem _PasswordPreview po 700ms."""
        self._preview_job  = None
        self._preview_win  = None

        def _schedule_show(e=None):
            _cancel_show()
            self._preview_job = self.after(700, _show)

        def _cancel_show(e=None):
            if self._preview_job:
                self.after_cancel(self._preview_job)
                self._preview_job = None

        def _show():
            if self._preview_win and self._preview_win.winfo_exists():
                return
            try:
                self._preview_win = _PasswordPreview(
                    self, self.entry, self.db, self.crypto,
                    strength_color=self.strength_color,
                    strength_score=self.strength_score,
                )
            except Exception:
                pass

        def _hide(e=None):
            _cancel_show()
            # Small delay — check if pointer is still over self
            self.after(80, _check_hide)

        def _check_hide():
            try:
                mx = self.winfo_pointerx()
                my = self.winfo_pointery()
                x1 = self.winfo_rootx()
                y1 = self.winfo_rooty()
                x2 = x1 + self.winfo_width()
                y2 = y1 + self.winfo_height()
                if not (x1 <= mx <= x2 and y1 <= my <= y2):
                    if self._preview_win:
                        self._preview_win.close()
                        self._preview_win = None
            except tk.TclError:
                pass

        self.bind("<Enter>", _schedule_show, add="+")
        self.bind("<Leave>", _hide, add="+")
        self.bind("<Destroy>", lambda e: (
            _cancel_show(),
            self._preview_win.close() if self._preview_win else None
        ), add="+")

    def update_accent(self, accent: str, accent_hover: str):
        """Aktualizuje kolor akcentu in-place — bez przebudowy wiersza."""
        btn = getattr(self, "_copy_btn", None)
        if btn and btn.winfo_exists():
            try:
                btn.configure(fg_color=accent, hover_color=accent_hover)
            except tk.TclError:
                pass

    def update_mode(self, is_dark: bool):
        """Aktualizuje kolory wiersza po zmianie trybu jasny/ciemny.

        CTK nie propaguje automatycznie tuple fg_color do dzieci CTkScrollableFrame,
        dlatego wymuszamy jawne configure() na samym wierszu i odświeżamy hover.
        """
        border = "#3a3a3a" if is_dark else "#e8e8e8"
        row_bg = DARK_ROW if is_dark else LIGHT_ROW
        try:
            # Wymuś ponowne zastosowanie fg_color — CTK może nie propagować tuple
            # do widgetów zagnieżdżonych w CTkScrollableFrame
            self.configure(
                fg_color=(LIGHT_ROW, DARK_ROW),
                border_color=border,
            )
        except tk.TclError:
            pass

        # Przelicz i zarejestruj nowy kolor hover (zależy od bg trybu)
        hover = _blend_accent(ACCENT, row_bg, alpha=0.13)
        try:
            bind_hover_smooth(self, normal_color=(LIGHT_ROW, DARK_ROW), hover_color=hover)
        except Exception:
            pass

        # Jeśli accordion jest rozwinięty — zaktualizuj tło strength_canvas
        if self._detail_frame and self._detail_frame.winfo_exists():
            canvas_bg = "#3a3a3a" if is_dark else "#d0d0d0"
            try:
                for child in self._detail_frame.winfo_children():
                    # Szukamy CTkFrame-strength_row, a w nim tk.Canvas
                    if isinstance(child, ctk.CTkFrame):
                        for grandchild in child.winfo_children():
                            if isinstance(grandchild, tk.Canvas):
                                try:
                                    grandchild.configure(bg=canvas_bg)
                                except tk.TclError:
                                    pass
            except Exception:
                pass


# ──────────────────────────────────────────────
# GŁÓWNE OKNO
# ──────────────────────────────────────────────

class MainWindow(ctk.CTk):
    def __init__(self, db, crypto, user):
        super().__init__()
        self.geometry("+10000+10000")    # natychmiast poza ekran — flash przy tworzeniu okna jest off-screen
        self.attributes("-alpha", 0.0)   # invisible during build — revealed via _fade_in_on_start()
        self.db     = db
        self.crypto = crypto
        self.user   = user

        self._user_menu         = None
        self._user_menu_shadow  = None
        self._user_menu_visible = False
        self._active_category   = "Wszystkie"
        self.sync_client        = SyncClient()
        self._tray              = None

        # Auto-lock
        self._last_activity = time.time()
        self._locked        = False
        self._lock_timer    = None

        # Schowek timer
        self._clipboard_timer        = None
        self._clipboard_label        = None
        self._clipboard_seconds_left = 0

        # Nagłówek kategorii
        self._cat_header_label = None
        self._cat_weak_label   = None

        # Nowe atrybuty
        self._prefs           = _prefs
        self._compact_mode    = self._prefs.get("compact_mode")
        self._grid_mode       = self._prefs.get("grid_mode")
        self._dashboard_mode  = False
        self._dashboard_frame = None
        self._toast           = None   # inicjalizowany po _build_ui()
        self._score_ver       = 0      # wersja dla race-condition protection
        self._score_ring      = None
        self._add_btn         = None
        self._analysis_btn    = None
        self._compact_btn       = None
        self._dash_btn          = None
        self._content_frame     = None
        self._list_view_frame   = None
        self._theme_toggle_btn  = None
        self._top_frame       = None   # referencja do topbara (live theme update)
        self._app_title_label = None   # "AegisVault" label w topbarze
        self._cat_indicators  = {}     # left-border wskaźniki kategorii (VS Code-style)
        self._top_separator   = None   # gradient separator pod topbarem
        self._content_grad    = None   # gradient tła głównej treści
        self._update_btn           = None   # przycisk aktualizacji (ukryty do czasu wykrycia)
        self._update_info          = None   # ostatnio wykryta info o wersji
        self._last_notified_version = None  # wersja, dla której już pokazano powiadomienie
        self._first_update_done    = False  # czy pierwsze sprawdzenie już minęło
        self._update_dropdown = None   # referencja do otwartego dropdown panelu
        self._logo_label      = None   # logo w topbarze (rekolorowane z akcentem)
        self._sync_dot_canvas = None   # Canvas z kropką statusu sync
        self._sync_connected  = None   # None=unknown, True=ok, False=offline
        self._sidebar_grad_top = None  # animowany gradient górny sidebara
        self._sidebar_grad_bot = None  # animowany gradient dolny sidebara
        self._sidebar_scroll   = None  # CTkFrame sidebara (statyczny)
        self._category_colors_cache  = None  # cache invalidowany w _refresh()
        self._categories_cache       = None  # cache get_all_categories()
        self._category_icons_cache2  = None  # cache get_category_icons()
        self._strength_cache: dict   = {}    # (entry_id, updated_at) -> (score, color)
        self._trash_sidebar_btn      = None  # przycisk Kosz w sidebarze
        self._current_panel          = None  # fullscreen in-app panel (dla show_panel fallback)
        self._settings_overlay       = None  # tk.Frame overlay — nakrywa CAŁY window (lift() pewne)
        self._settings_panel         = None  # SettingsPanel wewnątrz overlay
        self._settings_open          = False # czy settings jest aktualnie otwarte/animowane

        # Generator haseł (sidebar) — persystentny stan między rebuild
        self._gen_pwd     = ""
        self._gen_history: list[str] = []   # ostatnie 5 wygenerowanych haseł
        self._gen_hist_frame = None          # referencja do ramki historii w sidebarze
        self._gen_length  = tk.IntVar(value=16)
        self._gen_upper   = tk.BooleanVar(value=True)
        self._gen_digits  = tk.BooleanVar(value=True)
        self._gen_special = tk.BooleanVar(value=True)
        self._gen_label   = None   # referencja do labela z wygenerowanym hasłem
        self._gen_bar     = None   # referencja do Canvas siły

        self.title(f"AegisVault — {user.username}")
        self.geometry("960x660")
        self.minsize(800, 520)

        self._build_ui()
        self._load_passwords(animate=False)
        self._start_auto_lock()
        self._setup_tray()
        self._setup_shortcuts()

        # Po _build_ui() i _load_passwords()
        self._toast = ToastManager(self)
        self._compute_security_score()

        # Tracker ostatniego zewnętrznego okna (dla Auto-type)
        self._last_external_hwnd: int | None = None
        self._own_hwnd_cache:     int | None = None
        self._start_hwnd_tracker()

        # Auto-czyść stary kosz
        threading.Thread(target=lambda: self.db.purge_old_trash(self.user), daemon=True).start()

        # Sprawdź aktualizacje w tle
        threading.Thread(target=self._bg_check_update, daemon=True).start()

        # Pokaż changelog jeśli to pierwsze uruchomienie po aktualizacji
        self.after(800, self._maybe_show_changelog)

        # Auto-backup przy starcie (jeśli czas minął)
        self.after(4000, self._check_auto_backup)

        self.bind_all("<Button-1>", self._reset_activity)
        self.bind_all("<Key>",      self._reset_activity)
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Wyrenderuj UI niewidocznie (alpha=0.0) zanim zacznie się fade-in
        self.update_idletasks()

        # Reveal with a smooth fade-in (hides blank-screen flash on startup)
        self._fade_in_on_start()

        # Pre-create panelu ustawień w tle — 1.5s po starcie, gdy użytkownik
        # ogląda już listę haseł. Overlay jest poniżej z-order więc tworzenie
        # widgetów jest niewidoczne; nie blokuje startu aplikacji.
        self.after(1500, self._precreate_settings_panel)

    # ──────────────────────────────────────────────
    # FADE-IN ON START
    # ──────────────────────────────────────────────

    def _fade_in_on_start(self):
        """Reveal the window with a smooth fade-in.
        Delay 120 ms zapewnia że okno logowania zdąży zanikać przed pojawieniem się tego okna.
        """
        STEPS = 8
        DELAY = 15  # ms between steps
        START_DELAY = 120  # ms — czekaj na zanik okna logowania

        def _step(i: int):
            if i > STEPS:
                self.attributes("-alpha", 1.0)
                return
            self.attributes("-alpha", i / STEPS)
            self.after(DELAY, _step, i + 1)

        def _start():
            # Okno jest przy alpha=0 na +-10000 — przesuń na środek ekranu zanim
            # zacznie się fade-in (ruch jest niewidoczny przy alpha=0).
            try:
                sw = self.winfo_screenwidth()
                sh = self.winfo_screenheight()
                self.geometry(f"960x660+{max(0,(sw-960)//2)}+{max(0,(sh-660)//2)}")
            except Exception:
                self.geometry("960x660")
            _step(1)

        self.after(START_DELAY, _start)

    # ──────────────────────────────────────────────
    # TRAY
    # ──────────────────────────────────────────────

    def _setup_tray(self):
        try:
            from gui.tray import TrayIcon
            self._tray = TrayIcon(
                username=self.user.username,
                on_show=self._tray_show,
                on_lock=self._lock,
                on_quit=self._quit_app,
            )
            self._tray.start()
        except Exception:
            self._tray = None

    def _tray_show(self):
        self.after(0, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    def _on_window_close(self):
        if self._tray:
            self.withdraw()   # schowaj do trayu
        else:
            self._quit_app()

    def _quit_app(self):
        self._cleanup()

    # ──────────────────────────────────────────────
    # AKTUALIZACJE
    # ──────────────────────────────────────────────

    def _check_auto_backup(self):
        """Sprawdza czy należy wykonać auto-backup i wykonuje go jeśli tak (wątek tła)."""
        from utils.auto_backup import should_backup, do_backup
        import os
        if not should_backup(self._prefs):
            return

        def _worker():
            try:
                path = do_backup(self.db, self.crypto, self.user, self._prefs)
                if path and self._toast:
                    fname = os.path.basename(path)
                    self.after(0, lambda: self._toast.show(
                        f"💾  Auto-backup zapisany: {fname}", duration=4000
                    ))
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _maybe_show_changelog(self):
        """Pokazuje dialog 'Co nowego' jeśli wersja zmieniła się od ostatniego uruchomienia."""
        from version import APP_VERSION, APP_CHANGELOG
        from utils.prefs_manager import PrefsManager
        from gui.changelog_dialog import ChangelogDialog
        prefs = PrefsManager()
        last = prefs.get("last_seen_version")
        prefs.set("last_seen_version", APP_VERSION)
        if last and last != APP_VERSION:
            ChangelogDialog(self, APP_VERSION, APP_CHANGELOG, accent=ACCENT)

    _UPDATE_INTERVAL_MS = 4 * 60 * 60 * 1000  # 4 godziny

    def _bg_check_update(self):
        """Wątek tła — sprawdza GitHub Releases pod kątem nowej wersji."""
        info = check_for_update()
        try:
            if info:
                self.after(0, lambda: self._on_update_found(info))
            else:
                self.after(0, self._schedule_next_update_check)
        except tk.TclError:
            pass

    def _schedule_next_update_check(self):
        """Planuje kolejne sprawdzenie aktualizacji za 4 godziny."""
        self._first_update_done = True
        try:
            self.after(self._UPDATE_INTERVAL_MS,
                       lambda: threading.Thread(target=self._bg_check_update, daemon=True).start())
        except tk.TclError:
            pass

    def _on_update_found(self, info: dict):
        """Wywoływane w wątku GUI gdy wykryto nową wersję."""
        self._update_info = info
        new_ver = info.get("version", "")

        # Pokaż ikonkę aktualizacji w topbarze
        try:
            self._update_btn.pack(side="right", padx=(0, 8))
        except tk.TclError:
            pass

        # Powiadom tylko raz na daną wersję
        if new_ver != self._last_notified_version:
            self._last_notified_version = new_ver
            if not self._first_update_done:
                # Pierwsze sprawdzenie po logowaniu — popup
                self.after(1500, self._show_update_notification)
            else:
                # Wykrycie w tle (app działa) — toast nieinwazyjny
                try:
                    self._toast.show(
                        f"Dostępna nowa wersja {new_ver}!  Kliknij ⬆ aby pobrać.",
                        kind="info",
                        duration=8000,
                    )
                except Exception:
                    pass

        self._schedule_next_update_check()

    def _show_update_notification(self):
        """Pokazuje przyjazny popup 'Hej! Jest nowa wersja'."""
        from gui.update_dialog import UpdateNotification
        info = getattr(self, "_update_info", None)
        if info:
            UpdateNotification(self, info)

    def _open_update_dialog(self):
        """Toggleuje dropdown panel pod ikonką w topbarze."""
        from gui.update_dialog import UpdateDropdown
        info = getattr(self, "_update_info", None)
        if not info:
            return
        # Jeśli już otwarty — zamknij
        if self._update_dropdown and self._update_dropdown.winfo_exists():
            self._update_dropdown.destroy()
            self._update_dropdown = None
            return
        self._update_dropdown = UpdateDropdown(self, info, self._update_btn)

    # ──────────────────────────────────────────────
    # SKRÓTY KLAWISZOWE
    # ──────────────────────────────────────────────

    def _setup_shortcuts(self):
        self.bind_all("<Control-n>", lambda e: self._add_password())
        self.bind_all("<Control-N>", lambda e: self._add_password())
        self.bind_all("<Control-f>", lambda e: self._focus_search())
        self.bind_all("<Control-F>", lambda e: self._focus_search())
        self.bind_all("<Control-l>", lambda e: self._lock())
        self.bind_all("<Control-L>", lambda e: self._lock())
        # Ctrl+W tylko na głównym oknie — nie wyłapuje child Toplevels
        self.bind("<Control-w>", lambda e: self._ctrl_w())
        self.bind("<Control-W>", lambda e: self._ctrl_w())
        self.bind_all("<question>", lambda e: self._show_shortcuts_overlay()
            if not isinstance(self.focus_get(), (tk.Entry, ctk.CTkEntry)) else None)
        self.bind_all("<Control-t>", lambda e: self._autotype_selected())
        self.bind_all("<Control-T>", lambda e: self._autotype_selected())
        self.bind_all("<Control-d>", lambda e: self._do_duplicate()
            if not isinstance(self.focus_get(), (tk.Entry, ctk.CTkEntry)) else None)
        self.bind_all("<Control-D>", lambda e: self._do_duplicate()
            if not isinstance(self.focus_get(), (tk.Entry, ctk.CTkEntry)) else None)

    def _ctrl_w(self):
        action = _prefs.get("ctrl_w_action")
        if action == "close":
            self._quit_app()
        else:
            # "minimize" — do trayu jeśli dostępny, inaczej minimalizuj
            if self._tray:
                self.withdraw()
            else:
                self.iconify()

    def _focus_search(self):
        self.entry_search.focus_set()

    def _update_breadcrumb(self, category: str):
        """Pokazuje/chowa breadcrumb '> Kategoria' w topbarze."""
        if category == "Wszystkie":
            # Ukryj breadcrumb
            try:
                self._breadcrumb_sep.pack_forget()
                self._breadcrumb_lbl.pack_forget()
            except tk.TclError:
                pass
        else:
            # Pokaż breadcrumb z animacją
            try:
                self._breadcrumb_lbl.configure(text=category)
                if not self._breadcrumb_sep.winfo_ismapped():
                    self._breadcrumb_sep.pack(side="left")
                    self._breadcrumb_lbl.pack(side="left")
                    # Krótki fade-in przez zmianę text_color
                    self._breadcrumb_lbl.configure(text_color=("gray80", "gray40"))
                    self.after(30, lambda: self._breadcrumb_lbl.configure(
                        text_color=(ACCENT, ACCENT)
                    ))
                else:
                    self._breadcrumb_lbl.configure(text=category)
            except tk.TclError:
                pass

    def _show_shortcuts_overlay(self):
        """Overlay z listą skrótów klawiszowych (klawisz ?)."""
        # Unikaj duplikatów
        if hasattr(self, "_shortcuts_overlay") and self._shortcuts_overlay and \
           self._shortcuts_overlay.winfo_exists():
            return

        is_dark = ctk.get_appearance_mode() == "Dark"
        overlay_bg = "#000000" if is_dark else "#ffffff"

        overlay = tk.Toplevel(self)
        overlay.overrideredirect(True)
        overlay.wm_attributes("-topmost", True)
        try:
            overlay.wm_attributes("-alpha", 0.0)
        except tk.TclError:
            pass

        # Wymiary i pozycja — wycentruj na głównym oknie
        self.update_idletasks()
        wx, wy = self.winfo_rootx(), self.winfo_rooty()
        ww, wh = self.winfo_width(), self.winfo_height()
        ow, oh = 480, 380
        ox = wx + (ww - ow) // 2
        oy = wy + (wh - oh) // 2
        overlay.geometry(f"{ow}x{oh}+{ox}+{oy}")
        overlay.configure(bg=overlay_bg)
        self._shortcuts_overlay = overlay

        # Ramka
        frame = tk.Frame(overlay, bg="#1e1e1e" if is_dark else "#f8f8f8",
                         highlightbackground="#3a3a3a" if is_dark else "#d0d0d0",
                         highlightthickness=1)
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        # Nagłówek
        tk.Label(frame, text="⌨  Skróty klawiszowe",
                 bg="#1e1e1e" if is_dark else "#f8f8f8",
                 fg=ACCENT, font=("Segoe UI", 15, "bold"),
                 pady=16).pack()

        # Separator
        tk.Frame(frame, height=1,
                 bg="#3a3a3a" if is_dark else "#d0d0d0").pack(fill="x", padx=20)

        # Lista skrótów
        shortcuts = [
            ("Ctrl + N", "Dodaj nowe hasło"),
            ("Ctrl + F", "Szukaj haseł"),
            ("Ctrl + L", "Zablokuj aplikację"),
            ("Ctrl + W", "Minimalizuj / Zamknij"),
            ("Ctrl + T", "Auto-type zaznaczonego hasła"),
            ("Ctrl + D", "Duplikuj zaznaczone hasło"),
            ("?",        "Pokaż/ukryj ten ekran"),
            ("↑ / ↓",   "Nawigacja po liście"),
            ("Enter",    "Rozwiń wiersz (accordion)"),
            ("Escape",   "Zamknij overlay / dialog"),
        ]

        fg = "#f0f0f0" if is_dark else "#1a1a1a"
        bg = "#1e1e1e" if is_dark else "#f8f8f8"
        alt_bg = "#252525" if is_dark else "#f0f0f0"

        for i, (key, desc) in enumerate(shortcuts):
            row_bg = alt_bg if i % 2 == 0 else bg
            row = tk.Frame(frame, bg=row_bg)
            row.pack(fill="x", padx=20, pady=1)
            tk.Label(row, text=key, bg=row_bg, fg=ACCENT,
                     font=("Courier New", 12, "bold"),
                     width=14, anchor="w", padx=8, pady=6).pack(side="left")
            tk.Label(row, text=desc, bg=row_bg, fg=fg,
                     font=("Segoe UI", 12),
                     anchor="w").pack(side="left", padx=(4, 0))

        # Stopka
        tk.Label(frame, text="Kliknij gdziekolwiek lub naciśnij Escape aby zamknąć",
                 bg="#1e1e1e" if is_dark else "#f8f8f8",
                 fg="gray", font=("Segoe UI", 10),
                 pady=12).pack()

        # Zamknij na klik lub Escape
        overlay.bind("<Button-1>", lambda e: _close())
        overlay.bind("<Escape>", lambda e: _close())
        self.bind("<Escape>", lambda e: _close(), add="+")

        def _close():
            try:
                overlay.destroy()
            except tk.TclError:
                pass

        # Fade-in
        def _fade(alpha=0.0):
            try:
                alpha = min(alpha + 0.15, 0.92)
                overlay.wm_attributes("-alpha", alpha)
                if alpha < 0.92:
                    overlay.after(16, lambda: _fade(alpha))
            except tk.TclError:
                pass

        overlay.after(10, lambda: _fade(0.0))

    # ──────────────────────────────────────────────
    # AUTO-LOCK
    # ──────────────────────────────────────────────

    def _start_auto_lock(self):
        self._check_lock()

    def _check_lock(self):
        if not self._locked:
            timeout = self._prefs.get("auto_lock_seconds")
            if timeout and timeout > 0:
                idle = time.time() - self._last_activity
                if idle >= timeout:
                    self._lock()
                    return
            self.after(10000, self._check_lock)

    def _reset_activity(self, event=None):
        self._last_activity = time.time()

    def _lock(self):
        self._locked = True
        try:
            pyperclip.copy("")
        except Exception:
            pass

        lock_win = ctk.CTkToplevel(self)
        lock_win.transient(self)   # nad managerem, nie nad wszystkimi aplikacjami
        lock_win.title("Aplikacja zablokowana")
        _wh_available = self._prefs.get("wh_lock_unlock") and wh.has_credential(self.user.username)
        lock_win.geometry(f"440x{'370' if _wh_available else '320'}")
        lock_win.resizable(False, False)
        lock_win.grab_set()
        lock_win.protocol("WM_DELETE_WINDOW", lambda: None)
        lock_win.after(10, lambda: lock_win.attributes("-topmost", False))

        ctk.CTkLabel(lock_win, text="🔒", font=ctk.CTkFont(size=52)).pack(pady=(30, 8))
        ctk.CTkLabel(lock_win, text="Aplikacja zablokowana",
                     font=ctk.CTkFont(size=18, weight="bold")).pack()
        ctk.CTkLabel(lock_win, text="Wpisz hasło masterowe aby odblokować:",
                     font=ctk.CTkFont(size=12), text_color="gray").pack(pady=(4, 12))

        entry = ctk.CTkEntry(lock_win, placeholder_text="Hasło masterowe...",
                             show="•", height=42, corner_radius=10)
        entry.pack(padx=30, fill="x")
        entry.focus()

        msg = ctk.CTkLabel(lock_win, text="", font=ctk.CTkFont(size=11), text_color="#e53e3e")
        msg.pack(pady=4)

        def unlock():
            from core.crypto import verify_master_password
            pwd = entry.get()
            if verify_master_password(pwd, self.user.master_password_hash):
                self._locked = False
                self._last_activity = time.time()
                lock_win.destroy()
                self.after(10000, self._check_lock)
            else:
                msg.configure(text="Nieprawidłowe hasło!")
                entry.delete(0, "end")

        ctk.CTkButton(
            lock_win, text="🔓 Odblokuj", height=42,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
            font=ctk.CTkFont(size=13, weight="bold"), command=unlock
        ).pack(padx=30, pady=(4, 6), fill="x")

        # Windows Hello — opcjonalny przycisk odblokowania biometrycznego
        if _wh_available:
            wh_btn = ctk.CTkButton(
                lock_win, text="🪟  Odblokuj przez Windows Hello", height=38,
                fg_color=("#dce8ff", "#1a2e50"), hover_color=("#c0d8ff", "#1e3a6a"),
                text_color=(ACCENT, "#90b8ff"),
                corner_radius=10, font=ctk.CTkFont(size=12),
            )
            wh_btn.pack(padx=30, pady=(0, 20), fill="x")

            def _wh_unlock():
                wh_btn.configure(state="disabled", text="⏳  Weryfikacja…")
                # Oderwij focus od pola hasła — PIN z WH nie może trafiać do entry.
                wh_btn.focus_set()
                lock_win.attributes("-topmost", False)  # pozwól dialogowi WH pojawić się nad oknem
                # Zwolnij grab — bez tego dialog WH nie może dostać fokusu ani inputu.
                lock_win.grab_release()

                def _restore_grab():
                    try:
                        lock_win.grab_set()
                    except Exception:
                        pass

                def _do():
                    ok = wh.verify("Odblokuj AegisVault")
                    if not ok:
                        self.after(0, lambda: (
                            _restore_grab(),
                            wh_btn.configure(state="normal",
                                             text="🪟  Odblokuj przez Windows Hello"),
                            msg.configure(text="Weryfikacja Windows Hello nieudana."),
                        ))
                        return
                    stored_pwd = wh.get_credential(self.user.username)
                    if stored_pwd is None:
                        self.after(0, lambda: (
                            _restore_grab(),
                            wh_btn.configure(state="normal",
                                             text="🪟  Odblokuj przez Windows Hello"),
                            msg.configure(text="Brak zapisanego hasła w Windows Hello."),
                        ))
                        return
                    from core.crypto import verify_master_password
                    if verify_master_password(stored_pwd, self.user.master_password_hash):
                        self._locked = False
                        self._last_activity = time.time()
                        self.after(0, lambda: (lock_win.destroy(),
                                               self.after(10000, self._check_lock)))
                    else:
                        self.after(0, lambda: (
                            _restore_grab(),
                            wh_btn.configure(state="normal",
                                             text="🪟  Odblokuj przez Windows Hello"),
                            msg.configure(text="Dane Windows Hello nie pasują."),
                        ))

                threading.Thread(target=_do, daemon=True).start()

            wh_btn.configure(command=_wh_unlock)
        else:
            ctk.CTkLabel(lock_win, text="").pack(pady=7)  # odstęp

        entry.bind("<Return>", lambda e: unlock())

    # ──────────────────────────────────────────────
    # SCHOWEK Z TIMEREM
    # ──────────────────────────────────────────────

    def _on_copy(self, title: str):
        if self._clipboard_timer:
            self._clipboard_timer.cancel()
        self._clipboard_seconds_left = CLIPBOARD_SECONDS
        self._update_clipboard_label(title)
        self._clipboard_timer = threading.Timer(1.0, self._tick_clipboard, args=[title])
        self._clipboard_timer.daemon = True
        self._clipboard_timer.start()

    def _start_hwnd_tracker(self):
        """Co 250ms zapamiętuje ostatnie zewnętrzne okno — używane przez Auto-type."""
        import ctypes as _ct

        def _poll():
            buf = _ct.create_unicode_buffer(256)
            while True:
                try:
                    import time
                    time.sleep(0.25)
                    fw = _ct.windll.user32.GetForegroundWindow()
                    if not fw:
                        continue
                    # Przy pierwszym pojawieniu AegisVault zapamiętaj własny HWND
                    if self._own_hwnd_cache is None:
                        _ct.windll.user32.GetWindowTextW(fw, buf, 256)
                        if "AegisVault" in buf.value:
                            self._own_hwnd_cache = fw
                    # Zewnętrzne okno → zapamiętaj
                    if fw != self._own_hwnd_cache and fw != 0:
                        self._last_external_hwnd = fw
                except Exception:
                    pass

        threading.Thread(target=_poll, daemon=True).start()

    def _do_autotype(self, entry):
        """Uruchamia Auto-Type: minimalizuje okno, wpisuje login+hasło w aktywnym oknie."""
        try:
            password = self.db.decrypt_password(entry, self.crypto)
        except Exception:
            self._toast.show("Błąd deszyfrowania — Auto-type anulowany", "error")
            return

        username = entry.username or ""
        delay_s  = float(_prefs.get("autotype_delay") or 2)
        sequence = _prefs.get("autotype_sequence") or "{USERNAME}{TAB}{PASSWORD}{ENTER}"

        toast_ms = int(delay_s * 1000) + 800
        self._toast.show(
            f"⌨ Auto-type za {int(delay_s)}s — przełącz na okno logowania",
            "info",
            duration_ms=toast_ms,
        )

        # Zapamiętaj cel TERAZ — tracker już śledzi ostatnie zewnętrzne okno
        target_hwnd = self._last_external_hwnd

        def _type_worker():
            import time, ctypes
            from utils.autotype import type_sequence_now

            time.sleep(delay_s)

            if self._own_hwnd_cache:
                ctypes.windll.user32.ShowWindow(self._own_hwnd_cache, 6)  # SW_MINIMIZE
            time.sleep(0.5)

            if target_hwnd:
                ctypes.windll.user32.SetForegroundWindow(target_hwnd)
                time.sleep(0.2)

            type_sequence_now(username, password, sequence)

        threading.Thread(target=_type_worker, daemon=True).start()

        # Uruchom po delay_s sekund (already handled inside thread)
        # self.after not needed — thread manages its own timing

    def _autotype_selected(self):
        """Ctrl+T — auto-type dla aktualnie zaznaczonego/pierwszego widocznego wpisu."""
        # Pobierz pierwszy widoczny wiersz w scroll_frame
        for child in self.scroll_frame.winfo_children():
            if isinstance(child, PasswordRow) and child.winfo_exists():
                self._do_autotype(child.entry)
                return
        self._toast.show("Brak widocznych haseł do Auto-type", "warning")

    def _do_duplicate(self, entry=None):
        """Ctrl+D — duplikuje pierwszy widoczny wpis (lub podany entry)."""
        if entry is None:
            for child in self.scroll_frame.winfo_children():
                if isinstance(child, PasswordRow) and child.winfo_exists():
                    entry = child.entry
                    break
        if entry is None:
            self._toast.show("Brak widocznych haseł do zduplikowania", "warning")
            return
        try:
            plain = self.db.decrypt_password(entry, self.crypto)
        except Exception:
            self._toast.show("Błąd deszyfrowania — duplikowanie anulowane", "error")
            return
        self.db.add_password(
            self.user, self.crypto,
            title=f"Kopia — {entry.title}",
            username=entry.username or "",
            plaintext_password=plain,
            url=entry.url or "",
            notes=entry.notes or "",
            category=entry.category or "Inne",
            expires_at=entry.expires_at,
        )
        self._refresh()
        self._toast.show(f"Zduplikowano: {entry.title}", "success")

    def _sync_ping_loop(self):
        """Pinguje serwer co 30s i aktualizuje kropkę statusu."""
        def _check():
            try:
                from utils.sync_client import SyncClient
                sc = SyncClient()
                connected = sc.is_connected()
            except Exception:
                connected = False
            self.after(0, lambda: self._sync_update_dot(connected))

        threading.Thread(target=_check, daemon=True).start()
        self.after(30_000, self._sync_ping_loop)

    def _sync_update_dot(self, connected: bool):
        """Aktualizuje kolor kropki sync status."""
        if not (self._sync_dot_canvas and self._sync_dot_canvas.winfo_exists()):
            return
        if self._sync_connected == connected:
            return  # bez zmian
        self._sync_connected = connected
        color = "#4caf50" if connected else "#555555"
        self._sync_dot_canvas.itemconfig("dot", fill=color)
        # Pulse — flash brighter once
        bright = "#80e080" if connected else "#888888"

        def _pulse(step=0):
            if not (self._sync_dot_canvas and self._sync_dot_canvas.winfo_exists()):
                return
            t = step / 6
            r1 = int(int(color[1:3], 16) + (int(bright[1:3], 16) - int(color[1:3], 16)) * (1 - abs(t * 2 - 1)))
            g1 = int(int(color[3:5], 16) + (int(bright[3:5], 16) - int(color[3:5], 16)) * (1 - abs(t * 2 - 1)))
            b1 = int(int(color[5:7], 16) + (int(bright[5:7], 16) - int(color[5:7], 16)) * (1 - abs(t * 2 - 1)))
            c = f"#{r1:02x}{g1:02x}{b1:02x}"
            self._sync_dot_canvas.itemconfig("dot", fill=c)
            if step < 6:
                self._sync_dot_canvas.after(60, lambda: _pulse(step + 1))
            else:
                self._sync_dot_canvas.itemconfig("dot", fill=color)

        _pulse()

    def _tick_clipboard(self, title: str):
        self._clipboard_seconds_left -= 1
        if self._clipboard_seconds_left <= 0:
            try:
                pyperclip.copy("")
            except Exception:
                pass
            def _clear_clipboard():
                if self._clipboard_label and self._clipboard_label.winfo_exists():
                    self._clipboard_label.configure(text="")
                if hasattr(self, "_clipboard_bar") and self._clipboard_bar.winfo_exists():
                    self._clipboard_bar.delete("all")
            self.after(0, _clear_clipboard)
        else:
            self.after(0, lambda: self._update_clipboard_label(title))
            self._clipboard_timer = threading.Timer(1.0, self._tick_clipboard, args=[title])
            self._clipboard_timer.daemon = True
            self._clipboard_timer.start()

    def _update_clipboard_label(self, title: str):
        if not self._clipboard_label or not self._clipboard_label.winfo_exists():
            return
        left  = self._clipboard_seconds_left
        self._clipboard_label.configure(
            text=f"📋  {title}  ·  {left}s",
            text_color=ACCENT
        )
        self._update_clipboard_bar()

    def _update_clipboard_bar(self):
        """Aktualizuje Canvas-owy pasek postępu schowka."""
        if not hasattr(self, "_clipboard_bar") or not self._clipboard_bar.winfo_exists():
            return
        secs_left = self._clipboard_seconds_left
        total = CLIPBOARD_SECONDS
        ratio = max(0.0, secs_left / total)
        w = self._clipboard_bar.winfo_width() or 100
        fill_w = int(w * ratio)
        self._clipboard_bar.delete("all")
        # Tło
        self._clipboard_bar.create_rectangle(0, 0, w, 4, fill="#444444", outline="")
        # Fill (kolor zależny od pozostałego czasu)
        if ratio > 0.5:
            color = "#4caf50"
        elif ratio > 0.2:
            color = "#f0a500"
        else:
            color = "#e05252"
        if fill_w > 0:
            self._clipboard_bar.create_rectangle(0, 0, fill_w, 4, fill=color, outline="")

    # ──────────────────────────────────────────────
    # BUDOWANIE UI
    # ──────────────────────────────────────────────

    def _make_logo_image(self, accent: str, size: int = 30) -> ctk.CTkImage:
        """Ładuje icon.png i rekoloruje go na bieżący kolor akcentu."""
        path = os.path.join(os.path.dirname(__file__), "..", "assets", "icon.png")
        img = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
        r, g, b = int(accent[1:3], 16), int(accent[3:5], 16), int(accent[5:7], 16)
        pixels = img.getdata()
        img.putdata([(r, g, b, a) if a > 10 else (0, 0, 0, 0) for _, _, _, a in pixels])
        return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))

    def _build_ui(self):
        # Topbar — gradient tint akcentu (adaptive dark/light)
        _topbar_tint = _blend_accent(ACCENT, _gcard(), 0.18)
        self._top_frame = ctk.CTkFrame(
            self, height=64, corner_radius=0,
            fg_color=(LIGHT_CARD, _topbar_tint),
        )
        self._top_frame.pack(fill="x")
        self._top_frame.pack_propagate(False)

        left = ctk.CTkFrame(self._top_frame, fg_color="transparent")
        left.pack(side="left", padx=20, fill="y")
        self._logo_label = ctk.CTkLabel(left, text="", image=self._make_logo_image(ACCENT, 30))
        self._logo_label.pack(side="left", padx=(0, 8))
        self._app_title_label = ctk.CTkLabel(
            left, text="AegisVault",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=(ACCENT, ACCENT),
        )
        self._app_title_label.pack(side="left")

        # Breadcrumb: pokazuje aktywną kategorię gdy != "Wszystkie"
        self._breadcrumb_sep = ctk.CTkLabel(
            left, text=" › ", font=ctk.CTkFont(size=14),
            text_color=("gray60", "gray50"),
        )
        self._breadcrumb_lbl = ctk.CTkLabel(
            left, text="",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=(ACCENT, ACCENT),
        )
        # Nie pakujemy na start — pojawi się przy wyborze kategorii

        # Security Score badge
        _is_dark = ctk.get_appearance_mode() == "Dark"
        _topbar_bg = _topbar_tint if _is_dark else LIGHT_CARD
        self._score_ring = AnimatedScoreRing(
            self._top_frame,
            size=44,
            bg_color=_topbar_bg,
            is_dark=_is_dark,
        )
        self._score_ring.pack(side="right", padx=(0, 6))
        self._score_ring.bind("<Button-1>", lambda e: self._open_analysis())
        self._score_ring.start_pulse()

        # Ikonka aktualizacji — ukryta domyślnie, pojawia się po wykryciu nowej wersji
        self._update_btn = ctk.CTkButton(
            self._top_frame, text="⬆",
            width=36, height=36,
            fg_color=("#f0a500", "#b87800"),
            hover_color=("#d4920a", "#a06a00"),
            text_color="#ffffff",
            corner_radius=18, font=ctk.CTkFont(size=15, weight="bold"),
            command=self._open_update_dialog,
        )
        # Nie pakujemy — pojawi się dopiero po wykryciu aktualizacji

        self.user_btn = ctk.CTkButton(
            self._top_frame, text=f"👤  {self.user.username}  ▾",
            height=36, width=160, fg_color="transparent",
            border_width=1, border_color=(ACCENT, ACCENT),
            hover_color=(_blend_accent(ACCENT, LIGHT_CARD, 0.12),
                         _blend_accent(ACCENT, "#1e1e1e", 0.25)),
            text_color=(ACCENT, ACCENT),
            corner_radius=20, font=ctk.CTkFont(size=13),
            command=self._toggle_user_menu,
        )
        self.user_btn.pack(side="right", padx=20)

        # Dark/Light mode toggle — z obwódką w kolorze akcentu
        _dm_icon = "☀️" if ctk.get_appearance_mode() == "Dark" else "🌙"
        self._theme_toggle_btn = ctk.CTkButton(
            self._top_frame, text=_dm_icon,
            width=36, height=36,
            fg_color=(_blend_accent(ACCENT, LIGHT_CARD, 0.12),
                      _blend_accent(ACCENT, "#1e1e1e", 0.22)),
            hover_color=(_blend_accent(ACCENT, LIGHT_CARD, 0.25),
                         _blend_accent(ACCENT, "#1e1e1e", 0.40)),
            border_width=1,
            border_color=(ACCENT, ACCENT),
            text_color=(ACCENT, ACCENT),
            corner_radius=18, font=ctk.CTkFont(size=16),
            command=self._toggle_dark_light,
        )
        self._theme_toggle_btn.pack(side="right", padx=(0, 4))

        # Status sync — mała kropka ●
        try:
            _top_bg = self._top_frame.cget("fg_color")
            _is_dark_now = ctk.get_appearance_mode() == "Dark"
            if isinstance(_top_bg, (list, tuple)):
                _dot_bg = _top_bg[1] if _is_dark_now else _top_bg[0]
            else:
                _dot_bg = _top_bg
        except Exception:
            _dot_bg = "#1e1e1e"
        self._sync_dot_canvas = tk.Canvas(
            self._top_frame, width=12, height=12,
            bg=_dot_bg,
            highlightthickness=0,
        )
        self._sync_dot_canvas.pack(side="right", padx=(0, 6))
        self._sync_dot_canvas.create_oval(2, 2, 10, 10, fill="#555555", outline="", tags="dot")
        self._sync_dot_canvas.bind("<Button-1>", lambda e: self._open_sync())
        # Start pinging in background
        self.after(2000, self._sync_ping_loop)

        # Separator — animowany shimmer (sweep akcentu od lewej do prawej)
        self._top_separator = AnimatedGradientCanvas(
            self,
            accent=ACCENT,
            base=_gbg(),
            anim_mode="slide",
            period_ms=6000,
            fps=20,
            n_bands=1,
            direction="h",
            steps=96,
            height=2,
        )
        self._top_separator.pack(fill="x")
        self._top_separator.start_animation()
        # Upewnij się że bg separatora jest adaptive (light/dark) — zapobiega czarnemu paskowi
        self._top_separator.configure(bg=_gbg())

        body = ctk.CTkFrame(self, fg_color=(LIGHT_BG, DARK_BG))
        body.pack(fill="both", expand=True)

        # Sidebar
        self.sidebar = ctk.CTkFrame(body, width=175, corner_radius=0,
                                    fg_color=(LIGHT_CARD, "#1a1a1a"))
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self._build_sidebar()

        # Content
        content = ctk.CTkFrame(body, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True)
        self._content_frame = content  # referencja dla dashboard

        toolbar = ctk.CTkFrame(content, fg_color="transparent")
        toolbar.pack(fill="x", padx=16, pady=14)

        # Ambient gradient — overlay na górze contentu, nie zajmuje miejsca w layoutcie.
        # place() + lower() → widoczny w paddingach toolbara, niewidoczny pod widgetami.
        self._content_grad = AnimatedGradientCanvas(
            content,
            accent=ACCENT,
            base=_gcard(),
            anim_mode="breathe",
            alpha_min=0.03,
            alpha_max=0.11,
            period_ms=5000,
            fps=15,
            direction="v",
            steps=64,
            height=72,
        )
        self._content_grad.place(x=0, y=0, relwidth=1.0)
        self._content_grad.tk.call('lower', self._content_grad._w)
        self._content_grad.start_animation()

        self.entry_search = ctk.CTkEntry(
            toolbar, placeholder_text="🔍   Szukaj haseł...  (Ctrl+F)",
            height=44, corner_radius=12, border_color=("gray75", "gray40")
        )
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry_search.bind("<KeyRelease>", lambda e: self._on_search_debounced())
        # Highlight border na focus — wizualny akcent gdy użytkownik szuka
        self.entry_search.bind("<FocusIn>",
            lambda e: self.entry_search.configure(border_color=(ACCENT, ACCENT)), add="+")
        self.entry_search.bind("<FocusOut>",
            lambda e: self.entry_search.configure(border_color=("gray75", "gray40")), add="+")

        # Przycisk Dodaj — z zapisaną referencją
        self._add_btn = ctk.CTkButton(
            toolbar, text="＋  Dodaj  (Ctrl+N)", height=44,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            corner_radius=12, font=ctk.CTkFont(size=13, weight="bold"),
            command=self._add_password
        )
        self._add_btn.pack(side="right", padx=(8, 0))

        self._analysis_btn = ctk.CTkButton(
            toolbar, text="🛡️  Analiza", height=44,
            fg_color=("#f0f4ff", "#1a2a4a"), hover_color=("#ddeeff", "#1e3a60"),
            text_color=(ACCENT, "#7ab8f5"), corner_radius=12,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._open_analysis
        )
        self._analysis_btn.pack(side="right", padx=(8, 0))

        # Przycisk widoku: Normalny / Kompaktowy / Siatka
        _compact_text = self._view_btn_text()
        self._compact_btn = ctk.CTkButton(
            toolbar, text=_compact_text,
            height=44,
            fg_color=("gray88", "#2a2a2a"),
            hover_color=("gray80", "#383838"),
            text_color=("gray20", "gray80"),
            corner_radius=12,
            font=ctk.CTkFont(size=13),
            command=self._cycle_view
        )
        self._compact_btn.pack(side="right", padx=(0, 6))

        # Przycisk Dashboard
        self._dash_btn = ctk.CTkButton(
            toolbar, text="🏠",
            height=44, width=44,
            fg_color=("gray88", "#2a2a2a"),
            hover_color=("gray80", "#383838"),
            text_color=("gray20", "gray80"),
            corner_radius=12,
            font=ctk.CTkFont(size=18),
            command=self._toggle_dashboard
        )
        self._dash_btn.pack(side="right", padx=(0, 4))

        ctk.CTkButton(
            toolbar, text="🔄  Sync", height=44,
            fg_color=("#f0fff4", "#1a3a2a"), hover_color=("#c6f6d5", "#1e4a30"),
            text_color=("#38a169", "#68d391"), corner_radius=12,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._open_sync
        ).pack(side="right")

        # Pasek bezpieczeństwa (zielony/żółty/czerwony wg siły haseł)
        self._sec_bar_canvas = tk.Canvas(
            content, height=5, bd=0, highlightthickness=0,
            bg=_gcard()
        )
        self._sec_bar_canvas.pack(fill="x", padx=16, pady=(0, 2))
        self._sec_bar_canvas.bind("<Configure>", lambda e: self._redraw_sec_bar())
        self._sec_bar_tip_label = None  # tooltip
        self._sec_bar_canvas.bind("<Enter>", self._show_sec_bar_tip)
        self._sec_bar_canvas.bind("<Leave>", self._hide_sec_bar_tip)
        self._sec_bar_counts = (0, 0, 0)  # (strong, medium, weak)
        self._sec_bar_displayed = [0.0, 0.0, 0.0]  # current animated fractions [strong, medium, weak]
        self._sec_bar_anim_id = None  # AnimationScheduler handle
        self._expiry_banner = None  # banner wygasających haseł

        # Kontener widoku listy — chowany/pokazywany jako całość przy przełączaniu dashboardu
        self._list_view_frame = ctk.CTkFrame(content, fg_color="transparent")
        self._list_view_frame.pack(fill="both", expand=True)

        status_bar = ctk.CTkFrame(self._list_view_frame, fg_color="transparent")
        status_bar.pack(fill="x", padx=16, pady=(0, 6))

        self.label_count = ctk.CTkLabel(
            status_bar, text="", font=ctk.CTkFont(size=12), text_color="gray"
        )
        self.label_count.pack(side="left")

        self._clipboard_label = ctk.CTkLabel(
            status_bar, text="", font=ctk.CTkFont(size=12)
        )
        self._clipboard_label.pack(side="right")

        # Pasek postępu schowka (Canvas 100×4px)
        self._clipboard_bar = tk.Canvas(
            status_bar, width=100, height=4,
            bg=_gcard(), highlightthickness=0
        )
        self._clipboard_bar.pack(side="right", padx=(0, 4))

        # Nagłówek aktywnej kategorii
        cat_header_frame = ctk.CTkFrame(self._list_view_frame, fg_color="transparent")
        cat_header_frame.pack(fill="x", padx=16, pady=(0, 2))

        self._cat_header_label = ctk.CTkLabel(
            cat_header_frame, text="",
            font=ctk.CTkFont(size=12), text_color="gray", anchor="w"
        )
        self._cat_header_label.pack(side="left")

        self._cat_weak_label = ctk.CTkLabel(
            cat_header_frame, text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#e05252", anchor="w"
        )
        self._cat_weak_label.pack(side="left")

        self.scroll_frame = ctk.CTkScrollableFrame(
            self._list_view_frame, corner_radius=16,
            fg_color=(LIGHT_BG, DARK_BG),
            border_width=1, border_color=("gray80", "#2e2e2e")
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._bind_smooth_scroll(self.scroll_frame)

        self._scroll_hex_bg = apply_hex_to_scrollable(self.scroll_frame, hex_size=36, glow_max=6, glow_interval_ms=1200, glow_mode="fire")

    def _bind_smooth_scroll(self, sf):
        """Smooth scroll dla CTkScrollableFrame."""
        try:
            canvas = sf._parent_canvas
        except AttributeError:
            return

        def _smooth_to(target_pos):
            try:
                current = [canvas.yview()[0]]
            except tk.TclError:
                return
            steps = 6

            def _tick(step=0):
                if step >= steps:
                    return
                t = _ease_out((step + 1) / steps)
                pos = current[0] + (target_pos - current[0]) * t
                try:
                    canvas.yview_moveto(max(0.0, min(1.0, pos)))
                    sf.after(14, lambda: _tick(step + 1))
                except tk.TclError:
                    pass
            _tick()

        def _on_wheel(e):
            try:
                view = canvas.yview()
                page = view[1] - view[0]
                if e.delta:
                    delta = -e.delta / (120 * 8)  # Windows
                elif e.num == 4:
                    delta = -page / 8
                else:
                    delta = page / 8
                target = max(0.0, min(1.0, view[0] + delta))
                _smooth_to(target)
            except tk.TclError:
                pass
            return "break"

        sf.bind("<MouseWheel>", _on_wheel)
        try:
            canvas.bind("<MouseWheel>", _on_wheel)
        except tk.TclError:
            pass

    def _build_sidebar(self):
        # Statyczne (tylko przy pierwszym budowaniu lub zmianie motywu)
        if not hasattr(self, '_sidebar_scroll') or self._sidebar_scroll is None or not self._sidebar_scroll.winfo_exists():
            self._build_sidebar_static()
        self._build_sidebar_dynamic()

    def _build_sidebar_static(self):
        """Tworzy statyczne elementy sidebara: gradienty + scrollable frame."""
        # Zatrzymaj poprzednie animacje przed zniszczeniem widgetów
        if self._sidebar_grad_top is not None:
            try:
                self._sidebar_grad_top.stop_animation()
            except tk.TclError:
                pass
        if self._sidebar_grad_bot is not None:
            try:
                self._sidebar_grad_bot.stop_animation()
            except tk.TclError:
                pass

        for w in self.sidebar.winfo_children():
            try:
                w.destroy()
            except tk.TclError:
                pass

        # Gradient na górze sidebara — animowany, oddycha (breathe)
        self._sidebar_grad_top = AnimatedGradientCanvas(
            self.sidebar,
            accent=ACCENT,
            base=_gbg(),
            anim_mode="breathe",
            alpha_min=0.06,
            alpha_max=0.22,
            period_ms=4000,
            fps=15,
            direction="v",
            steps=36,
            height=36,
        )
        self._sidebar_grad_top.pack(fill="x")
        self._sidebar_grad_top.start_animation()

        # Gradient na dole sidebara — faza przesunięta (period_ms=4500)
        self._sidebar_grad_bot = AnimatedGradientCanvas(
            self.sidebar,
            accent=ACCENT,
            base=_gbg(),
            anim_mode="breathe",
            alpha_min=0.02,
            alpha_max=0.38,
            period_ms=4500,
            fps=12,
            reverse=True,
            direction="v",
            steps=36,
            height=40,
        )
        self._sidebar_grad_bot.pack(side="bottom", fill="x")
        self._sidebar_grad_bot.start_animation()

        self._sidebar_scroll = ctk.CTkScrollableFrame(
            self.sidebar, corner_radius=0, fg_color="transparent",
            scrollbar_button_color=("gray75", "#2e2e2e"),
            scrollbar_button_hover_color=("gray60", "#3a3a3a"),
        )
        self._sidebar_scroll.pack(fill="both", expand=True)

    def _build_sidebar_dynamic(self):
        """Czyści i odtwarza dynamiczną zawartość sidebara (przyciski kategorii itp.)."""
        sidebar_scroll = self._sidebar_scroll
        if sidebar_scroll is None or not sidebar_scroll.winfo_exists():
            self._build_sidebar_static()
            sidebar_scroll = self._sidebar_scroll

        # Usuń poprzednią zawartość scroll frame
        for w in sidebar_scroll.winfo_children():
            try:
                w.destroy()
            except tk.TclError:
                pass

        self._cat_buttons = {}
        self._cat_indicators = {}

        # Oblicz liczniki kategorii
        all_entries = self.db.get_all_passwords(self.user)
        counts: dict[str, int] = {}
        for e in all_entries:
            cat = e.category or "Inne"
            counts[cat] = counts.get(cat, 0) + 1
        counts["Wszystkie"] = len(all_entries)

        # ── KATEGORIE DOMYŚLNE ──
        ctk.CTkLabel(sidebar_scroll, text="KATEGORIE",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="gray").pack(padx=16, pady=(16, 6), anchor="w")

        # Cache: unikamy dwóch dodatkowych zapytań DB co każde _build_sidebar_dynamic()
        if not hasattr(self, '_categories_cache') or self._categories_cache is None:
            self._categories_cache = self.db.get_all_categories(self.user)
        if not hasattr(self, '_category_icons_cache2') or self._category_icons_cache2 is None:
            self._category_icons_cache2 = self.db.get_category_icons(self.user)
        custom_icons = self._category_icons_cache2
        categories = self._categories_cache
        default_set = set(DEFAULT_CATEGORIES)
        for cat in ["Wszystkie"] + categories:
            icon     = CATEGORIES.get(cat, {}).get("icon") or custom_icons.get(cat, "🏷")
            n        = counts.get(cat, 0)
            label    = f"{icon} {cat}  ({n})" if n > 0 else f"{icon} {cat}"
            deletable = cat not in default_set and cat != "Wszystkie"
            self._add_cat_btn(sidebar_scroll, cat, label=label, deletable=deletable)

        # ── DODAJ KATEGORIĘ ──
        ctk.CTkButton(
            sidebar_scroll, text="＋ Nowa kategoria", height=30, anchor="w",
            fg_color="transparent",
            hover_color=("gray85", "#2a2a2a"),
            text_color=("gray50", "gray50"),
            corner_radius=10, font=ctk.CTkFont(size=11),
            command=self._add_category_dialog
        ).pack(padx=10, pady=(2, 4), fill="x")

        ctk.CTkFrame(sidebar_scroll, height=1, fg_color=("gray80", "#2e2e2e")).pack(
            fill="x", padx=10, pady=8
        )

        # ── SPECJALNE ──
        ctk.CTkLabel(sidebar_scroll, text="SPECJALNE",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="gray").pack(padx=16, pady=(0, 6), anchor="w")

        expiring_count = len(self.db.get_expiring_passwords(self.user))
        exp_text = f"⏰ Wygasające" + (f"  ({expiring_count})" if expiring_count else "")
        self._add_cat_btn(sidebar_scroll, "Wygasające", label=exp_text,
                          color="#f0a500" if expiring_count else None)

        trash_count = len(self.db.get_trashed_passwords(self.user))
        trash_text  = f"🗑️ Kosz" + (f"  ({trash_count})" if trash_count else "")
        self._trash_sidebar_btn = ctk.CTkButton(
            sidebar_scroll, text=trash_text, height=36, anchor="w",
            fg_color="transparent", hover_color=("gray85", "#2a2a2a"),
            text_color=("#c0392b" if trash_count else ("gray20", "gray80")),
            corner_radius=10, font=ctk.CTkFont(size=12),
            command=self._open_trash
        )
        self._trash_sidebar_btn.pack(padx=10, pady=2, fill="x")

        ctk.CTkFrame(sidebar_scroll, height=1, fg_color=("gray80", "#2e2e2e")).pack(
            fill="x", padx=10, pady=8
        )

        # ── BACKUP ──
        ctk.CTkLabel(sidebar_scroll, text="BACKUP",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="gray").pack(padx=16, pady=(0, 6), anchor="w")

        for text, cmd in [
            ("📤 Eksport",          self._export_passwords),
            ("📥 Import .aegis",    self._import_passwords),
            ("📥 Import zewnętrzny", self._import_external),
        ]:
            ctk.CTkButton(
                sidebar_scroll, text=text, height=34, anchor="w",
                fg_color="transparent", hover_color=("gray85", "#2a2a2a"),
                text_color=("gray20", "gray80"), corner_radius=10,
                font=ctk.CTkFont(size=12), command=cmd
            ).pack(padx=10, pady=2, fill="x")

        ctk.CTkFrame(sidebar_scroll, height=1, fg_color=("gray80", "#2e2e2e")).pack(
            fill="x", padx=10, pady=8
        )

        # ── GENERATOR HASEŁ ──
        ctk.CTkLabel(sidebar_scroll, text="GENERATOR",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="gray").pack(padx=16, pady=(0, 6), anchor="w")

        self._build_gen_panel(sidebar_scroll)

    def _build_gen_panel(self, parent):
        """Mini-panel generatora haseł w sidebarze."""
        gen_frame = ctk.CTkFrame(parent, corner_radius=10,
                                 fg_color=("gray90", "#222222"))
        gen_frame.pack(padx=10, pady=(0, 10), fill="x")

        # Slider długości
        slider_row = ctk.CTkFrame(gen_frame, fg_color="transparent", height=1)
        slider_row.pack(fill="x", padx=10, pady=(8, 2))

        ctk.CTkLabel(slider_row, text="Długość:",
                     font=ctk.CTkFont(size=11), anchor="w").pack(side="left")

        self._gen_len_label = ctk.CTkLabel(
            slider_row, text=str(self._gen_length.get()),
            font=ctk.CTkFont(size=11, weight="bold"), width=28, anchor="e"
        )
        self._gen_len_label.pack(side="right")

        def _on_slider(val):
            v = int(float(val))
            self._gen_length.set(v)
            self._gen_len_label.configure(text=str(v))

        ctk.CTkSlider(
            gen_frame, from_=8, to=32, number_of_steps=24,
            variable=self._gen_length, command=_on_slider,
            height=16,
        ).pack(fill="x", padx=10, pady=(0, 4))

        # Checkboxy — 3 równe kolumny, brak stałej szerokości żeby nie wychodziły poza sidebar
        chk_row = ctk.CTkFrame(gen_frame, fg_color="transparent", height=1)
        chk_row.pack(fill="x", padx=8, pady=(0, 6))
        chk_row.columnconfigure(0, weight=1)
        chk_row.columnconfigure(1, weight=1)
        chk_row.columnconfigure(2, weight=1)

        self._gen_checkboxes = []
        for col, (var, txt) in enumerate([
            (self._gen_upper,   "A-Z"),
            (self._gen_digits,  "0-9"),
            (self._gen_special, "#!@"),
        ]):
            chk = ctk.CTkCheckBox(
                chk_row, text=txt, variable=var,
                checkbox_width=14, checkbox_height=14,
                font=ctk.CTkFont(size=10),
                fg_color=ACCENT, hover_color=ACCENT_HOVER,
            )
            chk.grid(row=0, column=col, sticky="w", padx=(0, 2))
            self._gen_checkboxes.append(chk)

        # Przyciski
        btn_row = ctk.CTkFrame(gen_frame, fg_color="transparent", height=1)
        btn_row.pack(fill="x", padx=10, pady=(0, 6))

        # 🎲 mały przycisk "odśwież" z prawej — pakujemy PIERWSZY (side=right)
        ctk.CTkButton(
            btn_row, text="🎲", width=30, height=28,
            fg_color=("gray80", "#333333"), hover_color=("gray70", "#444444"),
            text_color=("gray10", "gray90"),
            corner_radius=8, font=ctk.CTkFont(size=13),
            command=self._gen_generate
        ).pack(side="right")

        # 📋 Kopiuj — główna akcja, zawsze generuje nowe hasło i kopiuje
        self._gen_copy_btn = ctk.CTkButton(
            btn_row, text="📋 Kopiuj", height=28,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            corner_radius=8, font=ctk.CTkFont(size=11, weight="bold"),
            command=self._gen_copy
        )
        self._gen_copy_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        # Podgląd wygenerowanego hasła
        self._gen_label = ctk.CTkLabel(
            gen_frame, text=self._gen_pwd or "—",
            font=ctk.CTkFont(size=10, family="Courier New"),
            text_color=("gray30", "gray70"), wraplength=130, anchor="w"
        )
        self._gen_label.pack(fill="x", padx=10, pady=(0, 4))

        # Mini pasek siły
        self._gen_bar = tk.Canvas(gen_frame, height=3, bd=0, highlightthickness=0,
                                  bg=_gcard())
        self._gen_bar.pack(fill="x", padx=10, pady=(0, 8))
        # Auto-generuj przy otwarciu panelu (zawsze świeże hasło)
        self.after(50, self._gen_generate)

        # Historia wygenerowanych haseł (ostatnie 5)
        ctk.CTkLabel(
            gen_frame, text="HISTORIA",
            font=ctk.CTkFont(size=9),
            text_color=("gray50", "gray55"), anchor="w",
        ).pack(fill="x", padx=10, pady=(4, 0))
        self._gen_hist_frame = ctk.CTkFrame(gen_frame, fg_color="transparent")
        self._gen_hist_frame.pack(fill="x", padx=10, pady=(0, 8))
        self._update_gen_history_ui()

    def _gen_generate(self):
        chars = string.ascii_lowercase
        if self._gen_upper.get():   chars += string.ascii_uppercase
        if self._gen_digits.get():  chars += string.digits
        if self._gen_special.get(): chars += "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        if not chars:
            chars = string.ascii_lowercase
        length = self._gen_length.get()
        self._gen_pwd = "".join(random.SystemRandom().choices(chars, k=length))
        if self._gen_label and self._gen_label.winfo_exists():
            self._gen_label.configure(text=self._gen_pwd)
        self._gen_redraw_bar()
        # Zapisz w historii (max 5, bez duplikatów kolejnych)
        if not self._gen_history or self._gen_history[-1] != self._gen_pwd:
            self._gen_history.append(self._gen_pwd)
            if len(self._gen_history) > 5:
                self._gen_history.pop(0)
        self._update_gen_history_ui()

    def _update_gen_history_ui(self):
        """Odświeża sekcję historii wygenerowanych haseł w sidebarze."""
        if not (self._gen_hist_frame and self._gen_hist_frame.winfo_exists()):
            return
        for w in self._gen_hist_frame.winfo_children():
            w.destroy()
        if not self._gen_history:
            return
        # Pokaż ostatnie 5 od najnowszego
        for pwd in reversed(self._gen_history):
            row = ctk.CTkFrame(self._gen_hist_frame, fg_color="transparent", height=1)
            row.pack(fill="x", pady=1)
            short = pwd[:14] + "…" if len(pwd) > 14 else pwd
            ctk.CTkLabel(
                row, text=short,
                font=ctk.CTkFont(size=10, family="Courier New"),
                text_color=("gray40", "gray60"), anchor="w",
            ).pack(side="left", fill="x", expand=True)

            def _make_copy_fn(p=pwd):
                def _do():
                    try:
                        import pyperclip; pyperclip.copy(p)
                    except Exception:
                        pass
                    if self._toast:
                        self._toast.show("📋 Skopiowano z historii", duration_ms=1500)
                return _do

            ctk.CTkButton(
                row, text="📋", width=24, height=20,
                fg_color="transparent", hover_color=("gray80", "#333333"),
                font=ctk.CTkFont(size=10), corner_radius=4,
                command=_make_copy_fn(),
            ).pack(side="right")

    def _gen_copy(self):
        self._gen_generate()   # zawsze generuj nowe przed kopiowaniem
        pyperclip.copy(self._gen_pwd)
        if self._toast:
            self._toast.show("📋  Skopiowano wygenerowane hasło!", duration_ms=2000)

    def _gen_redraw_bar(self, _retries: int = 0):
        if not (self._gen_bar and self._gen_bar.winfo_exists()):
            return
        if not self._gen_pwd:
            return
        sc = check_strength(self._gen_pwd)
        color = sc["color"]
        score = sc["score"]
        w = self._gen_bar.winfo_width()
        if w <= 1:
            if _retries < 10:
                self._gen_bar.after(50, lambda: self._gen_redraw_bar(_retries + 1))
            return
        self._gen_bar.delete("all")
        fill_w = int(w * (score + 1) / 5)
        self._gen_bar.create_rectangle(0, 0, fill_w, 3, fill=color, outline="")

    def _add_cat_btn(self, parent, cat: str, label: str = None,
                     color: str = None, deletable: bool = False):
        """Dodaje przycisk kategorii do sidebaru.

        Każdy przycisk obsługuje PPM (prawy przycisk myszy):
        - kategorie własne: Dodaj / Usuń
        - domyślne: tylko Dodaj
        """
        is_active = (cat == self._active_category)

        def _on_cat_click(c=cat):
            """Krótki flash akcentem + font bounce + wybór kategorii."""
            try:
                btn.configure(fg_color=(ACCENT_HOVER, ACCENT_HOVER),
                              font=ctk.CTkFont(size=14, weight="bold"))
                btn.after(120, lambda: btn.configure(font=ctk.CTkFont(size=12))
                          if btn.winfo_exists() else None)
            except tk.TclError:
                pass
            self._select_category(c)

        # Kontener: 3px wskaźnik + przycisk (stała wysokość = wysokość buttona)
        _row = ctk.CTkFrame(parent, fg_color="transparent", height=38)
        _row.pack(fill="x", padx=10, pady=2)
        _row.pack_propagate(False)

        # 3px left-border indicator (widoczny tylko gdy aktywna)
        _indicator = tk.Canvas(_row, width=3, height=1, highlightthickness=0, bd=0)
        _indicator.configure(bg=ACCENT if is_active else ("gray85" if ctk.get_appearance_mode() != "Dark" else "#1a1a1a"))
        _indicator.pack(side="left", fill="y", pady=4)

        # Button musi być dzieckiem _row (nie parent) żeby pack(in_=_row) działał poprawnie
        btn = ctk.CTkButton(
            _row, text=label or cat, height=38, anchor="w",
            fg_color=((ACCENT, ACCENT) if is_active else (LIGHT_CARD, "#1a1a1a")),
            hover_color=("gray85", "#2a2a2a"),
            text_color=(
                ("white", "white") if is_active
                else (color if color else ("gray20", "gray80"))
            ),
            corner_radius=10, font=ctk.CTkFont(size=12),
            command=_on_cat_click
        )
        btn.pack(side="left", fill="x", expand=True)
        self._cat_buttons[cat] = btn
        self._cat_indicators[cat] = _indicator

        # ── Kontekstowe menu PPM ──────────────────────────────────────
        def _on_right_click(event, c=cat, d=deletable):
            items = [
                {"text": "➕  Dodaj kategorię", "command": self._add_category_dialog},
            ]
            if d:
                items.append(None)
                items.append({
                    "text": "🗑  Usuń kategorię",
                    "command": lambda: self._delete_category(c),
                    "destructive": True,
                })
            ContextMenu(self, event.x_root, event.y_root, items)

        btn.bind("<Button-3>", _on_right_click, add="+")

    # ──────────────────────────────────────────────
    # ZARZĄDZANIE KATEGORIAMI
    # ──────────────────────────────────────────────

    def _delete_category(self, name: str):
        count = sum(
            1 for e in self.db.get_all_passwords(self.user)
            if (e.category or "Inne") == name
        )
        if count:
            pw_word = 'hasło' if count == 1 else ('hasła' if 2 <= count <= 4 else 'haseł')
            detail = f"Przypisane do niej {count} {pw_word} zostaną przeniesione do kategorii Inne."
        else:
            detail = "Kategoria jest pusta."
        msg = f'Usunąć kategorię „{name}"?\n\n{detail}'
        if not ask_yes_no("Usuń kategorię", msg, parent=self, yes_text="Usuń"):
            return
        self.db.delete_custom_category(self.user, name)
        if self._active_category == name:
            self._active_category = "Wszystkie"
        self._refresh(rebuild_sidebar=True)

    def _add_category_dialog(self, on_created=None):
        """Dialog tworzenia kategorii.
        on_created(name, icon) — opcjonalny callback po dodaniu."""
        def _cb(name, icon):
            self._build_sidebar_dynamic()
            if on_created:
                on_created(name, icon)
        _CategoryDialog(self, self.db, self.user,
                        accent=ACCENT, accent_hover=ACCENT_HOVER,
                        on_created=_cb)

    # ──────────────────────────────────────────────
    # KATEGORIE
    # ──────────────────────────────────────────────

    def _select_category(self, category: str):
        old_cat = self._active_category
        self._active_category = category
        self._category_colors_cache = None

        # Aktualizuj stan aktywnych przycisków IN-PLACE (bez rebuild sidebara → zero blink)
        if old_cat in self._cat_buttons:
            try:
                self._cat_buttons[old_cat].configure(
                    fg_color=(LIGHT_CARD, "#1a1a1a"),
                    text_color=("gray20", "gray80"),
                )
            except tk.TclError:
                pass
        if category in self._cat_buttons:
            try:
                self._cat_buttons[category].configure(
                    fg_color=(ACCENT, ACCENT),
                    text_color=("white", "white"),
                )
            except tk.TclError:
                pass

        # Aktualizuj wskaźniki left-border
        is_dark = ctk.get_appearance_mode() == "Dark"
        inactive_bg = "#1a1a1a" if is_dark else "gray85"
        for c, ind in self._cat_indicators.items():
            try:
                ind.configure(bg=ACCENT if c == category else inactive_bg)
            except tk.TclError:
                pass

        # Załaduj hasła z crossfade overlay (stary content znika, nowy slide-in)
        _q = self.entry_search.get().strip()
        crossfade_list(self.scroll_frame,
                       lambda: self._load_passwords(_q))
        self.after(300, self._compute_security_score)

        # Aktualizuj breadcrumb w topbarze
        self._update_breadcrumb(category)

    # ──────────────────────────────────────────────
    # ŁADOWANIE HASEŁ
    # ──────────────────────────────────────────────

    def _get_category_colors(self) -> dict:
        if self._category_colors_cache is not None:
            return self._category_colors_cache
        colors = dict(DEFAULT_CATEGORY_COLORS)
        try:
            for cat in self.db.session.query(CustomCategory).filter_by(user_id=self.user.id).all():
                colors[cat.name] = cat.color
        except Exception:
            pass
        self._category_colors_cache = colors
        return colors

    def _search_local(self, query: str, entries: list) -> list:
        """Filtruje listę wpisów lokalnie używając rapidfuzz (jeśli dostępny) albo prostego contains."""
        if not query:
            return entries
        try:
            from rapidfuzz import process, fuzz
            titles = [e.title for e in entries]
            results = process.extract(query, titles, scorer=fuzz.partial_ratio, score_cutoff=55, limit=200)
            matched = {title for title, score, _ in results}
            return [e for e in entries if e.title in matched]
        except ImportError:
            q = query.lower()
            return [e for e in entries if q in (e.title or "").lower() or q in (e.url or "").lower()]

    def _load_passwords(self, query="", animate=True):
        # Chowamy stare wiersze zamiast natychmiast niszczyć — eliminuje flash pustej listy.
        # Nowe widgety budujemy w tym samym przebiegu, stare niszczymy w kolejnej iteracji.
        # HexBackground jest tłem — pomijamy go, żeby przeżył każdy reload listy.
        _old = [w for w in self.scroll_frame.winfo_children()
                if not isinstance(w, HexBackground)]

        if not animate:
            # Tryb bez animacji — zniszcz stare widgety od razu, zero flash.
            for w in _old:
                try:
                    w.destroy()
                except tk.TclError:
                    pass
        else:
            for w in _old:
                try:
                    w.pack_forget()
                except tk.TclError:
                    pass

            def _cleanup_old():
                for w in _old:
                    try:
                        w.destroy()
                    except tk.TclError:
                        pass
            self.after(0, _cleanup_old)

        if query:
            # Wczytaj wszystkie wpisy z aktywnej kategorii, potem filtruj lokalnie przez rapidfuzz
            all_entries = self.db.get_passwords_by_category(self.user, self._active_category)
            entries = self._search_local(query, all_entries)
        else:
            entries = self.db.get_passwords_by_category(self.user, self._active_category)

        count = len(entries)
        self.label_count.configure(
            text=f"{count} {'hasło' if count == 1 else 'haseł'}"
        )

        # ── Nagłówek aktywnej kategorii ───────────────────────────────
        if self._cat_header_label and self._cat_header_label.winfo_exists():
            icon = CATEGORIES.get(self._active_category, {}).get("icon", "🏷")
            cat_text = f"{icon}  {self._active_category}  ·  {count} {'hasło' if count == 1 else 'haseł'}"
            self._cat_header_label.configure(text=cat_text)

        # ── Empty state ───────────────────────────────────────────────
        if not entries:
            if self._cat_weak_label and self._cat_weak_label.winfo_exists():
                self._cat_weak_label.configure(text="")
            empty = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            empty.pack(fill="both", expand=True, pady=60)

            if query:
                ctk.CTkLabel(empty, text="🔍", font=ctk.CTkFont(size=40)).pack()
                ctk.CTkLabel(empty, text="Brak wyników",
                             font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(8, 2))
                ctk.CTkLabel(empty, text=f'Nic nie pasuje do \u201e{query}\u201c',
                             font=ctk.CTkFont(size=12), text_color="gray").pack()
            elif self._active_category not in ("Wszystkie", "Wygasające"):
                ctk.CTkLabel(empty, text="📂", font=ctk.CTkFont(size=40)).pack()
                ctk.CTkLabel(empty, text=f'Brak hase\u0142 w \u201e{self._active_category}\u201c',
                             font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(8, 2))
                ctk.CTkLabel(empty, text="Ta kategoria jest pusta.",
                             font=ctk.CTkFont(size=12), text_color="gray").pack()
                ctk.CTkButton(
                    empty, text="＋ Dodaj hasło do tej kategorii", height=42, width=250,
                    fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
                    font=ctk.CTkFont(size=13, weight="bold"),
                    command=self._add_password
                ).pack(pady=(16, 0))
            elif self._active_category == "Wygasające":
                ctk.CTkLabel(empty, text="✅", font=ctk.CTkFont(size=40)).pack()
                ctk.CTkLabel(empty, text="Brak wygasających haseł",
                             font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(8, 2))
                ctk.CTkLabel(empty, text="Wszystkie hasła są aktualne.",
                             font=ctk.CTkFont(size=12), text_color="gray").pack()
            else:
                self._build_empty_canvas(empty)
                ctk.CTkLabel(empty, text="Brak haseł",
                             font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(8, 2))
                ctk.CTkLabel(empty, text="Nie masz jeszcze żadnych zapisanych haseł.",
                             font=ctk.CTkFont(size=12), text_color="gray").pack()
                ctk.CTkButton(
                    empty, text="＋ Dodaj pierwsze hasło", height=42, width=220,
                    fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
                    font=ctk.CTkFont(size=13, weight="bold"),
                    command=self._add_password
                ).pack(pady=(16, 0))
            return

        # ── Oblicz siłę i posortuj ulubione na górze ──────────────────
        cat_colors = self._get_category_colors()
        entry_data = []    # (entry, strength_color, is_favorite)
        strength_map = {}  # entry.id → strength score (int)
        weak_count = 0
        medium_count = 0
        strong_count = 0
        for entry in entries:
            cache_key = (entry.id, getattr(entry, "updated_at", None))
            if cache_key in self._strength_cache:
                score, s_color = self._strength_cache[cache_key]
            else:
                try:
                    plaintext = self.db.decrypt_password(entry, self.crypto)
                    sc = check_strength(plaintext)
                    s_color = sc["color"]
                    score = sc["score"]
                except Exception:
                    s_color = "#718096"
                    score = 2
                self._strength_cache[cache_key] = (score, s_color)
            strength_map[entry.id] = score
            if score <= 1:
                weak_count += 1
            elif score <= 2:
                medium_count += 1
            else:
                strong_count += 1
            fav = getattr(entry, "is_favorite", 0) or 0
            entry_data.append((entry, s_color, fav))

        # Banner wygasających — pokaż gdy ≥2 wygasające i kategoria "Wszystkie" bez query
        expiring_count = sum(
            1 for e, _, _ in entry_data
            if getattr(e, "expiry_status", None) == "soon"
        )
        if expiring_count >= 2 and not query and self._active_category == "Wszystkie":
            self.after(200, lambda: self._show_expiry_banner(expiring_count))
        else:
            self._hide_expiry_banner()

        # Zaktualizuj pasek bezpieczeństwa
        self._sec_bar_counts = (strong_count, medium_count, weak_count)
        self.after(10, self._animate_sec_bar)

        # Nagłówek — odznaka słabych haseł
        if self._cat_weak_label and self._cat_weak_label.winfo_exists():
            if weak_count > 0:
                self._cat_weak_label.configure(
                    text=f"  ·  ⚠ {weak_count} {'słabe' if weak_count == 1 else 'słabych'}"
                )
            else:
                self._cat_weak_label.configure(text="")

        # Oblicz recent_ids wcześnie — potrzebne do filtrowania fav/normal
        recent_ids: set = set()
        if not query and self._active_category == "Wszystkie":
            _used = [(e, sc, f) for e, sc, f in entry_data
                     if getattr(e, "last_used_at", None) is not None]
            _used.sort(key=lambda x: x[0].last_used_at, reverse=True)
            recent_ids = {e.id for e, _, _ in _used[:3]}

        # Sortowanie: ulubione na górze, potem po tytule
        # Wyklucz wpisy już pokazane w sekcji "Ostatnio używane"
        fav_entries    = [(e, sc, f) for e, sc, f in entry_data if f and e.id not in recent_ids]
        normal_entries = [(e, sc, f) for e, sc, f in entry_data if not f and e.id not in recent_ids]
        all_sorted     = fav_entries + normal_entries

        # ── WIDOK SIATKI ──────────────────────────────────────────
        if self._grid_mode:
            # W siatce pokazujemy WSZYSTKIE wpisy (brak sekcji "Ostatnio używane")
            all_grid = sorted(entry_data, key=lambda x: (-x[2], (x[0].title or "").lower()))
            grid_f = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            grid_f.pack(fill="x", padx=8, pady=8)
            grid_f.columnconfigure(0, weight=1)
            grid_f.columnconfigure(1, weight=1)
            _stagger = 30
            for idx, (entry, s_color, fav) in enumerate(all_grid):
                card = PasswordCard(
                    grid_f, entry, self.db, self.crypto,
                    self.user, self._refresh, self._on_copy,
                    category_colors=cat_colors,
                    strength_color=s_color,
                    strength_score=strength_map.get(entry.id, 2),
                    is_favorite=fav,
                )
                card.grid(row=idx // 2, column=idx % 2,
                          padx=6, pady=6, sticky="nsew")
                if animate:
                    slide_in_row(card, 160, delay_ms=idx * _stagger)
            return

        # ── WIDOK LISTY (normalny / kompaktowy) ───────────────────
        # Separator ulubionych
        if fav_entries:
            sep_lbl = ctk.CTkLabel(
                self.scroll_frame,
                text="★  ULUBIONE",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="#f0a500",
                anchor="w",
            )
            sep_lbl.pack(fill="x", padx=8, pady=(6, 2))

        _target_h = 36 if self._compact_mode else 74
        _row_pady = 1 if self._compact_mode else 3
        _stagger  = 8   # ms między wierszami

        # ── Sekcja "Ostatnio używane" ─────────────────────────────────
        # Pokazuj TYLKO gdy: brak query, kategoria "Wszystkie"
        if not query and self._active_category == "Wszystkie" and recent_ids:
            recent = [
                (e, sc, fav) for e, sc, fav in entry_data
                if e.id in recent_ids
            ]
            recent.sort(key=lambda x: x[0].last_used_at, reverse=True)

            if recent:
                # Nagłówek sekcji
                sep_recent = ctk.CTkFrame(
                    self.scroll_frame, fg_color="transparent", height=1
                )
                sep_recent.pack(fill="x", padx=8, pady=(4, 2))
                ctk.CTkLabel(
                    sep_recent, text="⏱  OSTATNIO UŻYWANE",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color=("gray50", "gray55"), anchor="w",
                ).pack(side="left")

                for idx, (entry, s_color, fav) in enumerate(recent):
                    row = PasswordRow(
                        self.scroll_frame, entry, self.db, self.crypto,
                        self.user, self._refresh, self._on_copy,
                        category_colors=cat_colors,
                        compact=self._compact_mode,
                        strength_color=s_color,
                        strength_score=strength_map.get(entry.id, 2),
                        is_favorite=fav,
                        on_autotype=self._do_autotype,
                        highlight_query=query,
                    )
                    row.pack(fill="x", pady=_row_pady, padx=4)
                    if animate:
                        slide_in_row(row, _target_h, delay_ms=min(idx * _stagger, 80))

                # Cienki separator po sekcji
                ctk.CTkFrame(
                    self.scroll_frame, height=1, fg_color=("gray80", "#2e2e2e")
                ).pack(fill="x", padx=8, pady=(4, 6))

        for idx, (entry, s_color, fav) in enumerate(fav_entries):
            row = PasswordRow(
                self.scroll_frame, entry, self.db, self.crypto,
                self.user, self._refresh, self._on_copy,
                category_colors=cat_colors,
                compact=self._compact_mode,
                strength_color=s_color,
                strength_score=strength_map.get(entry.id, 2),
                is_favorite=fav,
                on_autotype=self._do_autotype,
                highlight_query=query,
            )
            row.pack(fill="x", pady=_row_pady, padx=4)
            if animate:
                slide_in_row(row, _target_h, delay_ms=min(idx * _stagger, 80))

        if fav_entries and normal_entries:
            ctk.CTkFrame(
                self.scroll_frame, height=1, fg_color=("gray80", "#2e2e2e")
            ).pack(fill="x", padx=8, pady=(4, 6))

        _offset = len(fav_entries)
        for idx, (entry, s_color, fav) in enumerate(normal_entries):
            row = PasswordRow(
                self.scroll_frame, entry, self.db, self.crypto,
                self.user, self._refresh, self._on_copy,
                category_colors=cat_colors,
                compact=self._compact_mode,
                strength_color=s_color,
                strength_score=strength_map.get(entry.id, 2),
                is_favorite=fav,
                on_autotype=self._do_autotype,
                highlight_query=query,
            )
            row.pack(fill="x", pady=_row_pady, padx=4)
            if animate:
                slide_in_row(row, _target_h, delay_ms=min((_offset + idx) * _stagger, 250))

        # Odśwież regiony kart dla hex glow — po zakończeniu animacji wink_height() jest poprawny
        _hbg = getattr(self, '_scroll_hex_bg', None)
        if _hbg and hasattr(_hbg, '_refresh_card_regions'):
            self.after(600, _hbg._refresh_card_regions)

    def _update_sidebar_counts(self):
        """Lekka aktualizacja liczników w sidebarze — bez destroy/recreate widgetów."""
        if not self._cat_buttons:
            # Sidebar jeszcze nie zbudowany — zrób pełny rebuild
            self._build_sidebar_dynamic()
            return

        all_entries = self.db.get_all_passwords(self.user)
        counts: dict[str, int] = {}
        for e in all_entries:
            cat = e.category or "Inne"
            counts[cat] = counts.get(cat, 0) + 1
        counts["Wszystkie"] = len(all_entries)

        custom_icons = self._category_icons_cache2 or {}
        for cat, btn in list(self._cat_buttons.items()):
            try:
                if not btn.winfo_exists():
                    continue
                if cat == "Wygasające":
                    continue  # obsługiwany osobno poniżej
                icon = CATEGORIES.get(cat, {}).get("icon") or custom_icons.get(cat, "🏷")
                n = counts.get(cat, 0)
                label = f"{icon} {cat}  ({n})" if n > 0 else f"{icon} {cat}"
                btn.configure(text=label)
            except tk.TclError:
                pass

        # Wygasające
        try:
            expiring_count = len(self.db.get_expiring_passwords(self.user))
            exp_btn = self._cat_buttons.get("Wygasające")
            if exp_btn and exp_btn.winfo_exists():
                exp_text = "⏰ Wygasające" + (f"  ({expiring_count})" if expiring_count else "")
                exp_btn.configure(text=exp_text)
        except tk.TclError:
            pass

        # Kosz
        try:
            if self._trash_sidebar_btn and self._trash_sidebar_btn.winfo_exists():
                trash_count = len(self.db.get_trashed_passwords(self.user))
                trash_text = "🗑️ Kosz" + (f"  ({trash_count})" if trash_count else "")
                self._trash_sidebar_btn.configure(
                    text=trash_text,
                    text_color="#c0392b" if trash_count else ("gray20", "gray80"),
                )
        except tk.TclError:
            pass

    def _refresh(self, rebuild_sidebar: bool = False):
        self._category_colors_cache = None  # invaliduj cache przy każdej zmianie
        # _strength_cache jest celowo zachowany — działa per (id, updated_at)
        if rebuild_sidebar:
            self._categories_cache = None
            self._category_icons_cache2 = None
            self._build_sidebar_dynamic()
        else:
            self._update_sidebar_counts()  # lekka aktualizacja liczników (bez rebuild)
        self._load_passwords(self.entry_search.get().strip(), animate=False)
        self.after(300, self._compute_security_score)

    def _on_search_debounced(self):
        """Debounce 250 ms — uruchamia _on_search dopiero po chwili bez wpisywania."""
        if hasattr(self, "_search_after_id") and self._search_after_id:
            try:
                self.after_cancel(self._search_after_id)
            except Exception:
                pass
        self._search_after_id = self.after(250, self._on_search)

    def _on_search(self):
        self._search_after_id = None
        self._load_passwords(self.entry_search.get().strip())

    def _build_empty_canvas(self, parent):
        """Rysuje geometryczną ilustrację kłódki + subtelna animacja oddychania."""
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg = "#1a1a1a" if is_dark else "#f5f5f5"
        accent = ACCENT
        gray = "#555555" if is_dark else "#c0c0c0"

        cv = tk.Canvas(parent, width=80, height=80, bg=bg, highlightthickness=0)
        cv.pack(pady=(0, 4))

        def _draw(scale: float = 1.0):
            cv.delete("all")
            cx, cy = 40, 40
            # Rozmiary skalowane
            bw = int(34 * scale)  # szerokość korpusu
            bh = int(24 * scale)  # wysokość korpusu
            bx1, by1 = cx - bw // 2, cy - bh // 2 + int(8 * scale)
            bx2, by2 = cx + bw // 2, cy + bh // 2 + int(8 * scale)

            # Korpus kłódki
            cv.create_rectangle(bx1, by1, bx2, by2, fill=gray, outline="", width=0)

            # Otwór kluczowy (mały okrąg)
            kx, ky = cx, (by1 + by2) // 2
            kr = int(4 * scale)
            cv.create_oval(kx - kr, ky - kr, kx + kr, ky + kr, fill=accent, outline="")

            # Pałąk (łuk U)
            sw = int(28 * scale)
            sh = int(24 * scale)
            sx1, sy1 = cx - sw // 2, by1 - sh
            sx2, sy2 = cx + sw // 2, by1
            cv.create_arc(sx1, sy1, sx2, sy2, start=0, extent=180,
                          outline=gray, width=int(5 * scale), style="arc")

        _draw(1.0)

        # Animacja oddychania: 1.0 → 1.05 → 1.0, co 3s
        _anim_state = [0.0, 1]  # [elapsed_ms, direction]
        PERIOD = 3000  # ms per half-cycle

        def _breathe():
            if not cv.winfo_exists():
                return
            _anim_state[0] += 50
            t = _anim_state[0] / PERIOD
            if t >= 1.0:
                _anim_state[0] = 0.0
                _anim_state[1] *= -1
                t = 0.0

            if _anim_state[1] > 0:
                scale = 1.0 + 0.05 * (t * t * (3 - 2 * t))  # smoothstep
            else:
                scale = 1.05 - 0.05 * (t * t * (3 - 2 * t))

            _draw(scale)
            cv.after(50, _breathe)

        cv.after(1000, _breathe)  # zacznij po 1s opóźnieniu

    def _add_password(self):
        form = PasswordFormWindow(self, self.db, self.crypto, self.user)
        self.wait_window(form)
        if form.result:
            self._refresh()

    # ──────────────────────────────────────────────
    # WIDOK: NORMALNY / KOMPAKTOWY / SIATKA / DASHBOARD
    # ──────────────────────────────────────────────

    def _view_btn_text(self) -> str:
        if self._grid_mode:    return "⊞⊞  Siatka"
        if self._compact_mode: return "⊟  Kompaktowy"
        return "⊞  Normalny"

    def _cycle_view(self):
        """Cykl: Normalny → Kompaktowy → Siatka → Normalny."""
        if self._grid_mode:
            self._grid_mode    = False
            self._compact_mode = False
        elif self._compact_mode:
            self._compact_mode = False
            self._grid_mode    = True
        else:
            self._compact_mode = True
            self._grid_mode    = False
        self._prefs.set("compact_mode", self._compact_mode)
        self._prefs.set("grid_mode",    self._grid_mode)
        if self._compact_btn and self._compact_btn.winfo_exists():
            self._compact_btn.configure(text=self._view_btn_text())
        if self._dashboard_mode:
            self._hide_dashboard()
        _q = self.entry_search.get().strip()
        crossfade_list(self.scroll_frame,
                       lambda: self._load_passwords(_q))

    # Zachowaj alias dla wstecznej kompatybilności
    def _toggle_compact(self):
        self._cycle_view()

    def _toggle_dashboard(self):
        if self._dashboard_mode:
            self._hide_dashboard()
        else:
            self._show_dashboard()

    def _show_dashboard(self):
        self._dashboard_mode = True
        if self._dash_btn and self._dash_btn.winfo_exists():
            self._dash_btn.configure(
                fg_color=(ACCENT, ACCENT), text_color=("white", "white")
            )
        if self._list_view_frame and self._list_view_frame.winfo_exists():
            self._list_view_frame.pack_forget()
        self._build_dashboard()

    def _hide_dashboard(self):
        self._dashboard_mode = False
        if self._dash_btn and self._dash_btn.winfo_exists():
            self._dash_btn.configure(
                fg_color=("gray88", "#2a2a2a"), text_color=("gray20", "gray80")
            )
        # Najpierw przywróć listę — potem ukryj/zniszcz dashboard.
        # Odwrócona kolejność eliminuje czarny ekran przy pack_forget.
        if self._list_view_frame and self._list_view_frame.winfo_exists():
            self._list_view_frame.pack(fill="both", expand=True)
        _df = self._dashboard_frame
        self._dashboard_frame = None
        if _df is not None:
            try:
                _df.pack_forget()
                _df.destroy()
            except tk.TclError:
                pass

    def _build_dashboard(self):
        """Buduje widok Dashboard z kartami statystyk."""
        if self._dashboard_frame and self._dashboard_frame.winfo_exists():
            self._dashboard_frame.destroy()
        self._dashboard_frame = ctk.CTkScrollableFrame(
            self._content_frame, corner_radius=16,
            fg_color=(LIGHT_BG, DARK_BG),
            border_width=1, border_color=("gray80", "#2e2e2e")
        )
        self._dashboard_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._dashboard_hex_bg = apply_hex_to_scrollable(self._dashboard_frame, hex_size=36, glow_max=6, glow_interval_ms=1200, glow_mode="fire")

        all_entries = self.db.get_all_passwords(self.user)
        expiring    = self.db.get_expiring_passwords(self.user)

        # Oblicz statystyki siły haseł
        strong_n = medium_n = weak_n = 0
        recent_used = []
        for e in all_entries:
            try:
                sc = check_strength(self.db.decrypt_password(e, self.crypto))["score"]
                if sc >= 3:   strong_n += 1
                elif sc >= 2: medium_n += 1
                else:         weak_n   += 1
            except Exception:
                medium_n += 1
            if getattr(e, "last_used_at", None):
                recent_used.append(e)

        total = len(all_entries)
        sec_pct = int((strong_n / total * 100) if total else 0)

        # ── Tytuł ──────────────────────────────────────────────────
        ctk.CTkLabel(
            self._dashboard_frame, text="🏠  Dashboard",
            font=ctk.CTkFont(size=18, weight="bold"), anchor="w"
        ).pack(fill="x", padx=20, pady=(16, 8))

        # ── Siatka 2×2 kart statystyk ──────────────────────────────
        grid_f = ctk.CTkFrame(self._dashboard_frame, fg_color="transparent", height=1)
        grid_f.pack(fill="x", padx=16, pady=(0, 12))
        grid_f.columnconfigure(0, weight=1)
        grid_f.columnconfigure(1, weight=1)

        stats = [
            ("🔐", str(total),         "haseł łącznie",    ACCENT,     lambda: self._select_category("Wszystkie")),
            ("🛡️", f"{sec_pct}%",      "wynik siły",       "#4caf50",  self._open_analysis),
            ("⚠️", str(weak_n),         "słabych haseł",    "#e05252",  lambda: None),
            ("⏰", str(len(expiring)),  "wygasających",     "#f0a500",  lambda: self._select_category("Wygasające")),
        ]
        for idx, (icon, val, label, color, cmd) in enumerate(stats):
            card = ctk.CTkFrame(
                grid_f, corner_radius=14,
                fg_color=(LIGHT_CARD, DARK_CARD),
                border_width=1, border_color=("gray82", "#2e2e2e"),
                height=90,
            )
            card.grid(row=idx // 2, column=idx % 2, padx=6, pady=6, sticky="nsew")
            card.pack_propagate(False)
            card.bind("<Button-1>", lambda e, c=cmd: c())
            card.configure(cursor="hand2")

            ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=26)).place(x=12, y=10)
            ctk.CTkLabel(
                card, text=val,
                font=ctk.CTkFont(size=28, weight="bold"),
                text_color=(color, color)
            ).place(x=52, y=8)
            ctk.CTkLabel(
                card, text=label,
                font=ctk.CTkFont(size=10), text_color="gray"
            ).place(x=52, y=46)

            # Animowany licznik
            self._animate_counter(card, val)

        # ── Ostatnio dodane ────────────────────────────────────────
        sorted_new = sorted(all_entries,
                            key=lambda e: e.created_at or datetime.min, reverse=True)[:5]
        if sorted_new:
            ctk.CTkLabel(
                self._dashboard_frame, text="🕐  Ostatnio dodane",
                font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
            ).pack(fill="x", padx=20, pady=(8, 4))
            for e in sorted_new:
                self._dash_entry_row(e, date_attr="created_at")

        # ── Ostatnio używane ───────────────────────────────────────
        sorted_used = sorted(
            recent_used,
            key=lambda e: e.last_used_at or datetime.min, reverse=True
        )[:5]
        if sorted_used:
            ctk.CTkLabel(
                self._dashboard_frame, text="📋  Ostatnio kopiowane",
                font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
            ).pack(fill="x", padx=20, pady=(12, 4))
            for e in sorted_used:
                self._dash_entry_row(e, date_attr="last_used_at")

    def _animate_counter(self, card, final_str: str):
        """Animuje licznik od 0 do wartości docelowej."""
        try:
            target = int(final_str.rstrip("%"))
        except ValueError:
            return
        suffix = "%" if final_str.endswith("%") else ""
        # Znajdź label z dużą czcionką (wartość)
        labels = [w for w in card.winfo_children()
                  if isinstance(w, ctk.CTkLabel) and "bold" in str(w.cget("font"))]
        if not labels:
            return
        lbl = labels[0]
        steps = 20
        delay = 800 // max(steps, 1)

        def _tick(step=0):
            if step > steps:
                lbl.configure(text=f"{target}{suffix}")
                return
            val = int(target * step / steps)
            try:
                lbl.configure(text=f"{val}{suffix}")
                card.after(delay, lambda: _tick(step + 1))
            except tk.TclError:
                pass
        card.after(200, _tick)

    def _dash_entry_row(self, entry, date_attr: str = "created_at"):
        """Wiersz ostatnio dodanego/używanego hasła w dashboardzie."""
        cat_colors = self._get_category_colors()
        color  = cat_colors.get(entry.category or "Inne", "#718096")
        initial = (entry.title or "?")[0].upper()
        dt = getattr(entry, date_attr, None)
        date_str = dt.strftime("%d.%m.%Y  %H:%M") if dt else "—"

        row = ctk.CTkFrame(
            self._dashboard_frame, corner_radius=10,
            fg_color=(LIGHT_ROW, DARK_ROW), height=52
        )
        row.pack(fill="x", padx=16, pady=2)
        row.pack_propagate(False)

        ctk.CTkLabel(
            row, text=initial, width=34, height=34,
            fg_color=color, corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"), text_color="white"
        ).pack(side="left", padx=(10, 8), pady=9)

        info = ctk.CTkFrame(row, fg_color="transparent", height=1)
        info.pack(side="left", fill="both", expand=True, pady=9)
        ctk.CTkLabel(
            info, text=entry.title,
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w"
        ).pack(fill="x")
        ctk.CTkLabel(
            info, text=date_str,
            font=ctk.CTkFont(size=10), text_color="gray", anchor="w"
        ).pack(fill="x")

        ctk.CTkButton(
            row, text="📋", width=32, height=30,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=8,
            font=ctk.CTkFont(size=13),
            command=lambda e=entry: self._dash_copy(e)
        ).pack(side="right", padx=8, pady=11)

    def _dash_copy(self, entry):
        decrypted = self.db.decrypt_password(entry, self.crypto)
        pyperclip.copy(decrypted)
        self.db.mark_used(entry)
        self._on_copy(entry.title)

    # ──────────────────────────────────────────────
    # SECURITY SCORE
    # ──────────────────────────────────────────────

    def _compute_security_score(self):
        self._score_ver += 1
        ver = self._score_ver

        # Odczytaj dane na głównym wątku (Session jest tu bezpieczna)
        try:
            entries = self.db.get_all_passwords(self.user)
        except Exception:
            return

        def worker():
            try:
                result = _sec_score.calculate_from_entries(entries, self.crypto)
                def update():
                    if self._score_ver == ver:
                        self._update_score_badge(result)
                self.after(0, update)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _update_score_badge(self, result: dict):
        if not self._score_ring or not self._score_ring.winfo_exists():
            return
        score = result.get("score", 0)
        self._score_ring.animate_to(score)

    # ──────────────────────────────────────────────
    # APPLY THEME
    # ──────────────────────────────────────────────

    def apply_theme(self, theme_id: str):
        """Aktualizuje kolory akcentu in-place — bez rebuild, bez flash."""
        if getattr(self, '_accent_animating', False):
            return
        self._accent_animating = True
        try:
            self._do_apply_theme()
        finally:
            self._accent_animating = False

    def _do_apply_theme(self):
        """Właściwa przebudowa UI po zmianie koloru akcentu/motywu."""
        global ACCENT, ACCENT_HOVER
        old_accent   = ACCENT
        colors       = self._prefs.get_theme_colors()
        ACCENT       = colors["accent"]
        ACCENT_HOVER = colors["hover"]

        # ── Sidebar — aktualizuj kolory in-place (bez rebuild) ────────
        _is_dark_sb = ctk.get_appearance_mode() == "Dark"
        _inactive_ind = "#1a1a1a" if _is_dark_sb else "gray85"
        for c, btn in list(self._cat_buttons.items()):
            is_active = (c == self._active_category)
            try:
                btn.configure(
                    fg_color=(ACCENT, ACCENT) if is_active else (LIGHT_CARD, "#1a1a1a"),
                    text_color=("white", "white") if is_active else ("gray20", "gray80"),
                )
            except tk.TclError:
                pass
        for c, ind in list(self._cat_indicators.items()):
            try:
                ind.configure(bg=ACCENT if c == self._active_category else _inactive_ind)
            except tk.TclError:
                pass

        # ── Lista haseł — aktualizuj akcent in-place (zero rebuild, zero flash) ─
        for w in self.scroll_frame.winfo_children():
            if isinstance(w, (PasswordRow, PasswordCard)):
                try:
                    w.update_accent(ACCENT, ACCENT_HOVER)
                except Exception:
                    pass

        # ── Topbar — live update ───────────────────────────────────
        if self._top_frame and self._top_frame.winfo_exists():
            _tint = _blend_accent(ACCENT, _gcard(), 0.18)
            self._top_frame.configure(fg_color=(LIGHT_CARD, _tint))
            # Sync dot canvas bg musi pasować do topbara (Canvas nie dziedziczy fg_color)
            if self._sync_dot_canvas and self._sync_dot_canvas.winfo_exists():
                _is_dark = ctk.get_appearance_mode() == "Dark"
                _dot_bg = _tint if _is_dark else LIGHT_CARD
                self._sync_dot_canvas.configure(bg=_dot_bg)

        if self._app_title_label and self._app_title_label.winfo_exists():
            self._app_title_label.configure(text_color=(ACCENT, ACCENT))

        if self._logo_label and self._logo_label.winfo_exists():
            self._logo_label.configure(image=self._make_logo_image(ACCENT, 30))

        if self._theme_toggle_btn and self._theme_toggle_btn.winfo_exists():
            self._theme_toggle_btn.configure(
                border_color=(ACCENT, ACCENT),
                text_color=(ACCENT, ACCENT),
                fg_color=(_blend_accent(ACCENT, LIGHT_CARD, 0.12),
                          _blend_accent(ACCENT, "#1e1e1e", 0.22)),
                hover_color=(_blend_accent(ACCENT, LIGHT_CARD, 0.25),
                             _blend_accent(ACCENT, "#1e1e1e", 0.40)),
            )

        if self.user_btn and self.user_btn.winfo_exists():
            self.user_btn.configure(
                border_color=(ACCENT, ACCENT),
                text_color=(ACCENT, ACCENT),
                hover_color=(
                    _blend_accent(ACCENT, LIGHT_CARD, 0.12),
                    _blend_accent(ACCENT, _gcard(), 0.25),
                ),
            )

        if self._top_separator and self._top_separator.winfo_exists():
            self._top_separator.update_accent(ACCENT, _gbg())
            self._top_separator.configure(bg=_gbg())
        if self._settings_overlay and self._settings_overlay.winfo_exists():
            try:
                self._settings_overlay.configure(bg=_gbg())
            except Exception:
                pass

        if self._content_grad and self._content_grad.winfo_exists():
            self._content_grad.update_accent(ACCENT, _gcard())
            self._content_grad.configure(bg=_gcard())

        if self._sidebar_grad_top and self._sidebar_grad_top.winfo_exists():
            self._sidebar_grad_top.update_accent(ACCENT, _gbg())
        if self._sidebar_grad_bot and self._sidebar_grad_bot.winfo_exists():
            self._sidebar_grad_bot.update_accent(ACCENT, _gbg())

        if self._sec_bar_canvas and self._sec_bar_canvas.winfo_exists():
            self._sec_bar_canvas.configure(bg=_gcard())
            self._redraw_sec_bar()

        # Score ring — zaktualizuj tło przy zmianie motywu
        if self._score_ring and self._score_ring.winfo_exists():
            _is_dark = ctk.get_appearance_mode() == "Dark"
            _tint = _blend_accent(ACCENT, _gcard(), 0.18)
            self._score_ring.set_bg(_tint if _is_dark else LIGHT_CARD, _is_dark)

        # Score badge — przerysuj z nowym kontrastem względem akcentu
        self._compute_security_score()

        # ── Płynna animacja koloru przycisku Dodaj ─────────────────
        if self._add_btn and self._add_btn.winfo_exists():
            animate_color(
                self._add_btn,
                from_color=old_accent,
                to_color=ACCENT,
                configure_fn=lambda c: self._add_btn.configure(fg_color=c),
                steps=16, interval_ms=15,
            )
            self._add_btn.configure(hover_color=ACCENT_HOVER)

        # Zaktualizuj przycisk Analiza (text_color)
        if self._analysis_btn and self._analysis_btn.winfo_exists():
            self._analysis_btn.configure(text_color=(ACCENT, "#7ab8f5"))

        # Zaktualizuj schowek timer label (kolor tekstu)
        if self._clipboard_label and self._clipboard_label.winfo_exists():
            if self._clipboard_seconds_left > 0:
                self._clipboard_label.configure(text_color=ACCENT)

        # ── Generator haseł w sidebarze — zaktualizuj kolory checkboxów i przycisku Kopiuj ──
        for chk in getattr(self, '_gen_checkboxes', []):
            try:
                if chk.winfo_exists():
                    chk.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER)
            except Exception:
                pass
        _gen_copy_btn = getattr(self, '_gen_copy_btn', None)
        if _gen_copy_btn:
            try:
                if _gen_copy_btn.winfo_exists():
                    _gen_copy_btn.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER)
            except Exception:
                pass

        # Wymuś pełną aktualizację wszystkich CTK widgetów do aktualnego trybu.
        # update_callbacks() jest bezpieczne — każdy callback (CTKFrame._draw,
        # HexBackground._on_appearance_change) jest idempotentny.
        try:
            ctk.AppearanceModeTracker.update_callbacks()
        except Exception:
            pass

        # Odśwież hex backgrounds — wymusza aktualizację bg i kolorów siatki
        for _hbg_attr in ('_scroll_hex_bg', '_dashboard_hex_bg'):
            _hbg = getattr(self, _hbg_attr, None)
            if _hbg and hasattr(_hbg, 'update_theme'):
                try:
                    if _hbg.winfo_exists():
                        _hbg.update_theme()
                except Exception:
                    pass

    # ──────────────────────────────────────────────
    # BANNER WYGASAJĄCYCH HASEŁ
    # ──────────────────────────────────────────────

    def _show_expiry_banner(self, expiring_count: int):
        """Pokazuje pomarańczowy banner o wygasających hasłach."""
        # Ukryj poprzedni jeśli istnieje
        self._hide_expiry_banner()

        content_area = getattr(self, "_content_frame", None) or getattr(self, "scroll_frame", None)
        if content_area is None or not content_area.winfo_exists():
            return

        # Szukamy rodzica scroll_frame — ramkę nadrzędną
        parent = self.scroll_frame.master
        if parent is None or not parent.winfo_exists():
            return

        banner = ctk.CTkFrame(
            parent,
            fg_color=("#fff3cd", "#3d2e00"),
            corner_radius=8,
            border_width=1,
            border_color=("#f0a500", "#8a6000"),
            height=1,
        )
        # Wstaw PRZED scroll_frame
        banner.pack(fill="x", padx=8, pady=(4, 2))
        banner.pack_configure(before=self.scroll_frame)
        self._expiry_banner = banner

        row = ctk.CTkFrame(banner, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(
            row,
            text=f"⚠  {expiring_count} {'hasło wygasa' if expiring_count == 1 else 'haseł wygasa'} w ciągu 7 dni",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#8a6000", "#f0c040"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            row,
            text="Zobacz →",
            width=90, height=28,
            fg_color=("#f0a500", "#b87800"),
            hover_color=("#d4920a", "#a06a00"),
            text_color="#ffffff",
            corner_radius=8,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: self._select_category("Wygasające"),
        ).pack(side="right")

        # Slide-in
        from gui.animations import slide_fade_in
        try:
            slide_fade_in(banner)
        except Exception:
            pass

    def _hide_expiry_banner(self):
        """Chowa banner wygasających haseł."""
        if self._expiry_banner:
            try:
                if self._expiry_banner.winfo_exists():
                    self._expiry_banner.destroy()
            except tk.TclError:
                pass
            self._expiry_banner = None

    # ──────────────────────────────────────────────
    # PASEK BEZPIECZEŃSTWA
    # ──────────────────────────────────────────────

    def _redraw_sec_bar(self):
        if not (self._sec_bar_canvas and self._sec_bar_canvas.winfo_exists()):
            return
        c = self._sec_bar_canvas
        c.delete("all")
        w = c.winfo_width()
        if w <= 1:
            return
        h = 5
        fracs = self._sec_bar_displayed
        total_frac = sum(fracs)
        if total_frac < 0.001:
            return
        colors = ["#4caf50", "#f0a500", "#e05252"]
        x = 0
        for i, (frac, color) in enumerate(zip(fracs, colors)):
            seg_w = round(w * frac)
            if seg_w > 0:
                c.create_rectangle(x, 0, x + seg_w, h, fill=color, outline="")
                x += seg_w
        if x < w and total_frac >= 0.999:
            c.create_rectangle(x, 0, w, h, fill=colors[-1], outline="")

    def _animate_sec_bar(self):
        """Animuje pasek bezpieczeństwa od bieżącej pozycji do docelowej."""
        if not (self._sec_bar_canvas and self._sec_bar_canvas.winfo_exists()):
            return

        strong, medium, weak = self._sec_bar_counts
        total = strong + medium + weak
        if total == 0:
            target = [0.0, 0.0, 0.0]
        else:
            target = [strong / total, medium / total, weak / total]

        # Anuluj poprzednią animację
        if self._sec_bar_anim_id is not None:
            try:
                from gui.animations import get_scheduler
                get_scheduler(self).cancel(self._sec_bar_anim_id)
            except Exception:
                pass
            self._sec_bar_anim_id = None

        elapsed = [0.0]
        duration = 600.0  # ms

        from gui.animations import get_scheduler
        from utils.easing import ease_out_cubic

        start = list(self._sec_bar_displayed)

        def _tick(dt_ms: float) -> bool:
            if not (self._sec_bar_canvas and self._sec_bar_canvas.winfo_exists()):
                return False
            elapsed[0] += dt_ms
            t = ease_out_cubic(min(elapsed[0] / duration, 1.0))
            for i in range(3):
                self._sec_bar_displayed[i] = start[i] + (target[i] - start[i]) * t
            self._redraw_sec_bar()
            return elapsed[0] < duration

        self._sec_bar_anim_id = get_scheduler(self).add(_tick)

    def _show_sec_bar_tip(self, event=None):
        strong, medium, weak = self._sec_bar_counts
        if strong + medium + weak == 0:
            return
        text = f"  {strong} mocne  ·  {medium} średnie  ·  {weak} słabe  "
        tip = tk.Toplevel(self)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        lbl = tk.Label(tip, text=text, bg="#1a1a1a", fg="white",
                       font=("Segoe UI", 10), padx=6, pady=3)
        lbl.pack()
        x = self._sec_bar_canvas.winfo_rootx() + 10
        y = self._sec_bar_canvas.winfo_rooty() - 28
        tip.geometry(f"+{x}+{y}")
        self._sec_bar_tip_label = tip

    def _hide_sec_bar_tip(self, event=None):
        if self._sec_bar_tip_label:
            try:
                self._sec_bar_tip_label.destroy()
            except tk.TclError:
                pass
            self._sec_bar_tip_label = None

    # ──────────────────────────────────────────────
    # DARK / LIGHT TOGGLE
    # ──────────────────────────────────────────────

    def _toggle_dark_light(self):
        if getattr(self, "_theme_animating", False):
            return
        is_dark = ctk.get_appearance_mode() == "Dark"
        new_mode = "light" if is_dark else "dark"
        self._crossfade_theme_switch(new_mode)

    def _crossfade_theme_switch(self, new_mode: str):
        """Przełącza tryb jasny/ciemny z alpha-fade, bez blokowania pętli zdarzeń.

        Faza 1 — fade-out: alpha 1.0 → 0.0 w ~80ms (8 kroków × 10ms)
        Faza 2 — swap:     set_appearance_mode + _refresh_after_mode_change przy alpha=0
        Faza 3 — fade-in:  alpha 0.0 → 1.0 w ~120ms (10 kroków × 12ms)
        """
        if getattr(self, "_theme_animating", False):
            return
        self._theme_animating = True

        FADE_OUT_STEPS = 8
        FADE_OUT_MS    = 10
        FADE_IN_STEPS  = 10
        FADE_IN_MS     = 12

        is_dark = (new_mode.lower() == "dark")

        def _set_alpha(value: float):
            try:
                self.attributes("-alpha", value)
            except tk.TclError:
                pass

        def _do_swap():
            ctk.set_appearance_mode(new_mode)
            if self._theme_toggle_btn and self._theme_toggle_btn.winfo_exists():
                self._theme_toggle_btn.configure(text="☀️" if is_dark else "🌙")
            try:
                self.update_idletasks()
            except tk.TclError:
                pass
            self._refresh_after_mode_change()

        def _fade_in(step: int):
            alpha = step / FADE_IN_STEPS
            _set_alpha(alpha)
            if step < FADE_IN_STEPS:
                self.after(FADE_IN_MS, lambda: _fade_in(step + 1))
            else:
                self._theme_animating = False

        def _fade_out(step: int):
            # step counts down: FADE_OUT_STEPS → 0  (alpha = step/FADE_OUT_STEPS)
            alpha = step / FADE_OUT_STEPS
            _set_alpha(alpha)
            if step > 0:
                self.after(FADE_OUT_MS, lambda: _fade_out(step - 1))
            else:
                # Fully invisible — perform the swap, then fade back in
                _do_swap()
                self.after(FADE_IN_MS, lambda: _fade_in(1))

        _fade_out(FADE_OUT_STEPS - 1)

    def _refresh_after_mode_change(self):
        _is_dark = ctk.get_appearance_mode() == "Dark"
        _tint = _blend_accent(ACCENT, _gcard(), 0.18)
        if self._top_frame and self._top_frame.winfo_exists():
            self._top_frame.configure(fg_color=(LIGHT_CARD, _tint))
        if self._sync_dot_canvas and self._sync_dot_canvas.winfo_exists():
            _dot_bg = _tint if _is_dark else LIGHT_CARD
            self._sync_dot_canvas.configure(bg=_dot_bg)
        if self._top_separator and self._top_separator.winfo_exists():
            self._top_separator.update_accent(ACCENT, _gbg())
        if self._content_grad and self._content_grad.winfo_exists():
            self._content_grad.update_accent(ACCENT, _gcard())
            self._content_grad.configure(bg=_gcard())
        if self._sec_bar_canvas and self._sec_bar_canvas.winfo_exists():
            self._sec_bar_canvas.configure(bg=_gcard())
            self._redraw_sec_bar()
        if self._sidebar_grad_top and self._sidebar_grad_top.winfo_exists():
            self._sidebar_grad_top.update_accent(ACCENT, _gbg())
        if self._sidebar_grad_bot and self._sidebar_grad_bot.winfo_exists():
            self._sidebar_grad_bot.update_accent(ACCENT, _gbg())
        if self._score_ring and self._score_ring.winfo_exists():
            self._score_ring.set_bg(_tint if _is_dark else LIGHT_CARD, _is_dark)
        for _hbg_attr in ('_scroll_hex_bg', '_dashboard_hex_bg'):
            _hbg = getattr(self, _hbg_attr, None)
            if _hbg and hasattr(_hbg, 'update_theme'):
                try:
                    if _hbg.winfo_exists():
                        _hbg.update_theme()
                except Exception:
                    pass

        # Wymuś aktualizację wszystkich CTK widgetów (sidebar, body itp.)
        try:
            ctk.AppearanceModeTracker.update_callbacks()
        except Exception:
            pass

        # Sidebar — indicator canvas (tk.Canvas nie obsługuje tuple CTK)
        _inactive_ind = "#1a1a1a" if _is_dark else "gray85"
        for c, ind in list(self._cat_indicators.items()):
            try:
                ind.configure(bg=ACCENT if c == self._active_category else _inactive_ind)
            except tk.TclError:
                pass

        # Wiersze haseł i karty — CTK nie propaguje automatycznie tuple fg_color
        # do widgetów zagnieżdżonych w CTkScrollableFrame, dlatego wywołujemy
        # update_mode() explicite. PasswordCard żyje w pośrednim grid_f (CTkFrame),
        # dlatego sprawdzamy też dzieci dzieci scroll_frame.
        for w in self.scroll_frame.winfo_children():
            if isinstance(w, PasswordRow):
                try:
                    w.update_mode(_is_dark)
                except Exception:
                    pass
            elif isinstance(w, ctk.CTkFrame):
                # Może to być grid_f zawierający PasswordCard
                try:
                    for child in w.winfo_children():
                        if isinstance(child, PasswordCard):
                            try:
                                child.update_mode(_is_dark)
                            except Exception:
                                pass
                except Exception:
                    pass

    # ──────────────────────────────────────────────
    # KOSZ
    # ──────────────────────────────────────────────

    def _open_trash(self):
        TrashWindow(self, self.db, self.crypto, self.user, self._refresh)

    # ──────────────────────────────────────────────
    # EKSPORT / IMPORT
    # ──────────────────────────────────────────────

    def _export_passwords(self):
        import os
        desktop  = os.path.join(os.path.expanduser("~"), "Desktop")
        filepath = filedialog.asksaveasfilename(
            title="Eksportuj hasła",
            defaultextension=".aegis",
            filetypes=[("AegisVault Backup", "*.aegis"), ("Wszystkie pliki", "*.*")],
            initialdir=desktop
        )
        if not filepath:
            return
        try:
            count = self.db.export_passwords(self.user, self.crypto, filepath)
            self._toast.show(f"Wyeksportowano {count} haseł", "success")
        except Exception as e:
            show_error("Błąd eksportu", str(e), parent=self)

    def _import_passwords(self):
        import os
        desktop  = os.path.join(os.path.expanduser("~"), "Desktop")
        filepath = filedialog.askopenfilename(
            title="Importuj hasła (AegisVault)",
            filetypes=[("AegisVault Backup", "*.aegis"), ("Wszystkie pliki", "*.*")],
            initialdir=desktop
        )
        if not filepath:
            return
        try:
            imported, skipped = self.db.import_passwords(self.user, self.crypto, filepath)
            self._toast.show(f"Zaimportowano: {imported}  •  Pominięto: {skipped}", "success")
            self._refresh()
        except Exception as e:
            show_error("Błąd importu", f"Nie udało się zaimportować pliku.\n\n{e}", parent=self)

    def _import_external(self):
        import os
        desktop  = os.path.join(os.path.expanduser("~"), "Desktop")
        filepath = filedialog.askopenfilename(
            title="Importuj z innego menedżera haseł",
            filetypes=[
                ("Obsługiwane formaty", "*.csv *.json"),
                ("CSV", "*.csv"),
                ("JSON (Bitwarden)", "*.json"),
                ("Wszystkie pliki", "*.*"),
            ],
            initialdir=desktop
        )
        if not filepath:
            return
        try:
            from utils.import_manager import import_file
            items, fmt = import_file(filepath)

            fmt_names = {
                "lastpass": "LastPass", "bitwarden": "Bitwarden",
                "1password": "1Password", "generic": "Ogólny CSV"
            }
            fmt_label = fmt_names.get(fmt, fmt)

            if not ask_yes_no(
                "Import zewnętrzny",
                f"Wykryto format: {fmt_label}\nZnaleziono {len(items)} wpisów.\n\nImportować?",
                parent=self
            ):
                return

            imported = skipped = 0
            existing = {e.title for e in self.db.get_all_passwords(self.user)}

            for item in items:
                if item["title"] in existing:
                    skipped += 1
                    continue
                self.db.add_password(
                    self.user, self.crypto,
                    title=item["title"],
                    username=item.get("username", ""),
                    plaintext_password=item.get("password", ""),
                    url=item.get("url", ""),
                    notes=item.get("notes", ""),
                    category=item.get("category", "Inne"),
                )
                imported += 1

            self._toast.show(
                f"Import {fmt_label}: {imported} wpisów  •  Pominięto: {skipped}",
                "success"
            )
            self._refresh()
        except Exception as e:
            show_error("Błąd importu", str(e), parent=self)

    # ──────────────────────────────────────────────
    # DROPDOWN MENU UŻYTKOWNIKA
    # ──────────────────────────────────────────────

    def _toggle_user_menu(self):
        if self._user_menu_visible:
            self._close_user_menu()
        else:
            self._open_user_menu()

    def _open_user_menu(self):
        self._user_menu_visible = True
        is_dark = ctk.get_appearance_mode() == "Dark"
        btn     = self.user_btn
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height() + 6

        bg     = "#1e1e1e" if is_dark else "#ffffff"
        border = "#3a3a3a" if is_dark else "#e0e0e0"
        hover  = "#2b2b2b" if is_dark else "#f0f4ff"
        text_c = "#e8e8e8" if is_dark else "#1a1a1a"

        shadow = ctk.CTkToplevel(self)
        shadow.overrideredirect(True)
        shadow.geometry(f"185x115+{x+3}+{y+3}")
        shadow.configure(fg_color="#000000")
        shadow.attributes("-alpha", 0.18)
        shadow.lift()
        self._user_menu_shadow = shadow

        menu = ctk.CTkToplevel(self)
        menu.overrideredirect(True)
        menu.geometry(f"185x158+{x}+{y}")
        menu.configure(fg_color=bg)
        menu.lift()
        self._user_menu = menu

        card = ctk.CTkFrame(menu, corner_radius=14, fg_color=bg,
                            border_width=1, border_color=border)
        card.pack(fill="both", expand=True)

        # ── Gradient header z nazwą użytkownika (tekst na canvasie — brak artefaktów) ──
        _hdr_text_color = _resolve_menu_color(ACCENT)
        grad_hdr = AnimatedGradientCanvas(
            card,
            accent=ACCENT,
            base=_gcard(),
            anim_mode="slide",
            period_ms=5000,
            fps=20,
            n_bands=1,
            direction="h",
            steps=64,
            height=3,
        )
        grad_hdr.pack(fill="x")
        grad_hdr.start_animation()
        grad_hdr.set_overlay_text(
            f"👤  {self.user.username}",
            fill=_hdr_text_color,
            font=("Segoe UI Semibold", 11),
        )

        ctk.CTkFrame(card, height=1, corner_radius=0,
                     fg_color=border).pack(fill="x")

        options = [
            ("⚙️   Ustawienia", self._open_settings),
            ("🚪   Wyloguj się", self._logout),
        ]
        for i, (label, command) in enumerate(options):
            def make_cmd(cmd):
                def callback():
                    self._close_user_menu()
                    cmd()
                return callback
            ctk.CTkButton(
                card, text=label, height=42,
                fg_color="transparent", hover_color=hover,
                anchor="w", font=ctk.CTkFont(size=13),
                text_color=text_c, corner_radius=10,
                command=make_cmd(command)
            ).pack(fill="x", padx=6,
                   pady=(4 if i == 0 else 2, 4 if i == len(options)-1 else 2))

        self.after(100, self._bind_click_outside)

    def _bind_click_outside(self):
        self.bind("<Button-1>", self._on_click_outside)

    def _on_click_outside(self, event):
        if self._user_menu and self._user_menu.winfo_exists():
            mx = self._user_menu.winfo_rootx()
            my = self._user_menu.winfo_rooty()
            mw = self._user_menu.winfo_width()
            mh = self._user_menu.winfo_height()
            if not (mx <= event.x_root <= mx + mw and my <= event.y_root <= my + mh):
                self._close_user_menu()

    def _close_user_menu(self):
        self.unbind("<Button-1>")
        if self._user_menu and self._user_menu.winfo_exists():
            self._user_menu.destroy()
        if self._user_menu_shadow and self._user_menu_shadow.winfo_exists():
            self._user_menu_shadow.destroy()
        self._user_menu         = None
        self._user_menu_shadow  = None
        self._user_menu_visible = False

    # ──────────────────────────────────────────────
    # IN-APP PANEL SYSTEM
    # ──────────────────────────────────────────────

    @staticmethod
    def _toggle_panel_animations(panel, start: bool) -> None:
        """Rekurencyjnie startuje lub zatrzymuje animowane widgety wewnątrz panelu."""
        stack = []
        try:
            stack = list(panel.winfo_children())
        except Exception:
            return
        while stack:
            w = stack.pop()
            if hasattr(w, 'stop_animation') and hasattr(w, 'start_animation'):
                try:
                    if start:
                        w.start_animation()
                    else:
                        w.stop_animation()
                except Exception:
                    pass
            try:
                stack.extend(w.winfo_children())
            except Exception:
                pass

    def _precreate_settings_panel(self):
        """Tworzy overlay (tk.Frame) + SettingsPanel raz przy starcie.

        Architektura:
          overlay (tk.Frame) — stale place(relx=0, relwidth=1, relheight=1),
            warstwowo lift()/lower() żeby przykryć lub odkryć główny UI.
            tk.Frame.lift() jest niezawodny (brak canvas CTk).
          panel (SettingsPanel) — wewnątrz overlay, slideuje od relx=1.0→0.0
            gdy overlay jest już widoczny → slide jest przycinany do granic okna,
            main content niewidoczny przez cały czas trwania animacji.
        """
        if self._settings_overlay and self._settings_overlay.winfo_exists():
            return
        try:
            from gui.settings_window import SettingsPanel

            def _on_close():
                if self._settings_panel and hasattr(self._settings_panel, 'crypto'):
                    self.crypto = self._settings_panel.crypto
                # apply_theme() NIE tutaj — masowe przerysowania main window
                # podczas gdy overlay zasłania widok powodują blink przy zamknięciu.
                # Odkładamy na po zakończeniu animacji slide-out (patrz _close_settings_panel).
                self._close_settings_panel()

            # Overlay stale zakrywa całe okno gdy widoczny (relx=0, relheight=1)
            # Domyślnie poniżej wszystkiego (lower) — niewidoczny
            overlay = tk.Frame(self, bg=_gbg())
            overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            overlay.lower()

            panel = SettingsPanel(
                overlay,
                db=self.db,
                crypto=self.crypto,
                user=self.user,
                on_close=_on_close,
                on_logout=self._on_account_deleted,
                on_theme_change=self.apply_theme,
            )
            # Panel na prawej krawędzi overlay — gotowy do slide-in
            panel.place(relx=1.0, rely=0, relwidth=1, relheight=1)

            self._settings_overlay = overlay
            self._settings_panel   = panel
            # Animacje tykają w tle od razu — overlay jest lower(), więc koszt CPU ≈ 0
            # dla użytkownika, ale kanwasy mają zawsze wyrenderowaną zawartość.
            # Efekt: overlay.lift() przy otwarciu odkrywa już gotowy panel → brak shutter.
        except Exception:
            self._settings_overlay = None
            self._settings_panel   = None

    def show_panel(self, panel_class, **kwargs):
        """Otwiera non-settings panel z animacją slide-in."""
        if self._current_panel and self._current_panel.winfo_exists():
            return
        self._current_panel = panel_class(self, **kwargs)
        self._current_panel.place(relx=1.0, rely=0, relwidth=1, relheight=1)
        self._current_panel.lift()
        self._toggle_panel_animations(self._current_panel, False)

        def _on_open_done():
            if self._current_panel:
                self._toggle_panel_animations(self._current_panel, True)

        self._slide_frame(self._current_panel, 1.0, 0.0, on_done=_on_open_done)

    def close_panel(self):
        """Zamyka aktywny non-settings panel."""
        if not self._current_panel or not self._current_panel.winfo_exists():
            return
        self._toggle_panel_animations(self._current_panel, False)
        panel = self._current_panel
        self._current_panel = None

        def _done():
            try:
                if panel.winfo_exists():
                    panel.destroy()
            except Exception:
                pass

        self._slide_frame(panel, 0.0, 1.0, on_done=_done)

    def _slide_frame(self, frame, relx_start, relx_end, duration_ms=200, _t0=None, on_done=None):
        """Animuje place(relx=...) wybranego CTkFrame od relx_start do relx_end."""
        if _t0 is None:
            _t0 = time.perf_counter()
        elapsed = (time.perf_counter() - _t0) * 1000.0
        t = min(elapsed / duration_ms, 1.0)
        eased = _ease_out(t) if relx_end < relx_start else _ease_in(t)
        relx = relx_start + (relx_end - relx_start) * eased
        try:
            frame.place_configure(relx=relx, rely=0, relwidth=1, relheight=1)
        except Exception:
            if on_done:
                on_done()
            return
        if t < 1.0:
            self.after(8, lambda: self._slide_frame(frame, relx_start, relx_end, duration_ms, _t0, on_done))
        elif on_done:
            on_done()

    def _close_settings_panel(self):
        """Slide-out panelu wewnątrz overlay, potem schowanie overlay."""
        if not self._settings_open:
            return
        # Natychmiast — zapobiega podwójnemu otwarciu podczas animacji zamknięcia
        self._settings_open = False

        overlay = self._settings_overlay
        panel   = self._settings_panel
        # NIE zatrzymujemy animacji panelu — overlay je ukrywa; restart przy następnym
        # otwarciu blikałby. Animacje tykają w tle (znikomy koszt CPU).

        def _done():
            try:
                # Resetuj panel na prawy brzeg — gotowy na następne otwarcie
                if panel and panel.winfo_exists():
                    panel.place_configure(relx=1.0, rely=0, relwidth=1, relheight=1)
                # Schowaj overlay pod główny UI
                if overlay and overlay.winfo_exists():
                    overlay.lower()
            except Exception:
                pass
            # apply_theme dopiero PO odkryciu main content — żadnych redraws
            # przez overlay, żadnego blink. Zmiana koloru akcentu widoczna od razu.
            try:
                self.apply_theme(self._prefs.get("color_theme"))
            except Exception:
                pass
            # Wymuś natychmiastowe przerysowanie — CTK zaktualizował kolory via
            # AppearanceModeTracker, ale bez update_idletasks() Tkinter może
            # odroczyć rendering do następnej interakcji użytkownika.
            try:
                self.update_idletasks()
            except Exception:
                pass

        if panel and panel.winfo_exists():
            self._slide_frame(panel, 0.0, 1.0, on_done=_done)
        else:
            _done()

    # ──────────────────────────────────────────────
    # NAWIGACJA
    # ──────────────────────────────────────────────

    def _open_settings(self):
        if self._settings_open:
            return
        if not self._settings_overlay or not self._settings_overlay.winfo_exists():
            self._precreate_settings_panel()
        overlay = self._settings_overlay
        panel   = self._settings_panel
        if not overlay:
            return

        # Odśwież referencje (crypto może się zmienić po zmianie hasła)
        if panel:
            panel.crypto = self.crypto
            panel.user   = self.user

        self._settings_open = True

        # Animacje panelu biegną w tle od precreate — nie trzeba ich startować.
        # Natychmiast przykryj main content:
        overlay.lift()

        # Krok 3: slideuj panel — _t0 cofnięty o 16ms żeby pierwszy frame
        # był już w ruchu (relx ≈ 0.82 zamiast 1.0) i wyrenderował się
        # w tej samej ramce co overlay.lift() → zero blank-frame blink.
        if panel:
            panel.place_configure(relx=1.0, rely=0, relwidth=1, relheight=1)
        _t0 = time.perf_counter() - 0.016
        self._slide_frame(panel, 1.0, 0.0, _t0=_t0)

    def _open_sync(self):
        from gui.sync_window import SyncWindow
        SyncWindow(self, self.db, self.crypto, self.user, self.sync_client,
                   on_refresh=self._refresh)

    def _open_analysis(self):
        from gui.security_analysis_window import SecurityAnalysisWindow
        SecurityAnalysisWindow(self, self.db, self.crypto, self.user)

    def _logout(self):
        db_path = self.db.db_path
        self._cleanup()
        from gui.login_window import LoginWindow
        import gui.main_window as mw
        login = LoginWindow(db_path=db_path)
        login.mainloop()
        if login.logged_user and login.crypto:
            app = mw.MainWindow(login.db, login.crypto, login.logged_user)
            app.mainloop()

    def _on_account_deleted(self):
        self._cleanup()

    def _cleanup(self):
        if self._clipboard_timer:
            self._clipboard_timer.cancel()
        if self._content_grad:
            self._content_grad.stop_animation()
        if self._top_separator:
            self._top_separator.stop_animation()
        if self._sidebar_grad_top:
            self._sidebar_grad_top.stop_animation()
        if self._sidebar_grad_bot:
            self._sidebar_grad_bot.stop_animation()
        if self._score_ring:
            self._score_ring.stop_pulse()
        if self._tray:
            self._tray.stop()
        self._current_panel    = None
        self._settings_overlay = None
        self._settings_panel   = None
        self._settings_open    = False
        try:
            pyperclip.copy("")
        except Exception:
            pass
        self.db.close()
        # Cancel all pending after() callbacks before destroy to prevent
        # "invalid command name" bgerror messages after the window is gone.
        try:
            for after_id in self.tk.eval("after info").split():
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.quit()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        sys.exit(0)

    def on_close(self):
        self._cleanup()


if __name__ == "__main__":
    from gui.login_window import LoginWindow
    login = LoginWindow()
    login.mainloop()
    if login.logged_user:
        app = MainWindow(login.db, login.crypto, login.logged_user)
        app.mainloop()
