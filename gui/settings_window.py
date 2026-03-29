"""
settings_window.py - Okno ustawień (redesign z zakładkami)
===========================================================
Zakładki:
  🎨 Wygląd        — dark/light + kolor akcentu
  🔒 Bezpieczeństwo — Windows Hello, zmiana hasła, reset 2FA
  ⚙️  System        — Ctrl+W, autostart, usunięcie konta
"""

import threading
import customtkinter as ctk
from PIL import Image

from gui.dialogs import show_error, show_info, show_success, ask_yes_no
from gui.animations import slide_fade_in
from gui.hex_background import apply_hex_to_scrollable, apply_hex_to_window
from gui.gradient import GradientCanvas, AnimatedGradientCanvas
from database.db_manager import DatabaseManager
from core.crypto import (CryptoManager, hash_master_password,
                         verify_master_password, generate_salt)
from core.totp import TOTPManager
from utils.prefs_manager import PrefsManager, THEMES
import utils.windows_hello as wh
import utils.autostart as autostart
from utils.logger import get_logger, cleanup_old_logs

logger = get_logger(__name__)


def _gbg_s() -> str:
    """Adaptive gradient background for settings window."""
    import customtkinter as _ctk
    return "#1a1a1a" if _ctk.get_appearance_mode() == "Dark" else "#f5f5f5"


def _gcard_s() -> str:
    """Adaptive gradient card for settings window."""
    import customtkinter as _ctk
    return "#1c1c1c" if _ctk.get_appearance_mode() == "Dark" else "#fafafa"


def _blend_settings_accent(accent: str, base: str, alpha: float) -> str:
    """Miesza kolor akcentu z kolorem bazowym (alpha 0→base, 1→accent)."""
    def _p(c):
        c = c.lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    ar, ag, ab = _p(accent)
    br, bg_, bb = _p(base)
    r = int(br + (ar - br) * alpha)
    g = int(bg_ + (ag - bg_) * alpha)
    b = int(bb + (ab - bb) * alpha)
    return f"#{r:02x}{g:02x}{b:02x}"


class SettingsWindow(ctk.CTkToplevel):

    def __init__(self, parent, db: DatabaseManager, crypto: CryptoManager,
                 user, on_logout=None, on_theme_change=None):
        super().__init__(parent)
        self.geometry("+5000+5000")          # off-screen: CTk auto-deiconify flash niewidoczny
        self.wm_attributes("-alpha", 0.0)   # alpha=0 na starcie; slide_fade_in ujawni okno
        self.db              = db
        self.crypto          = crypto
        self.user            = user
        self.on_logout       = on_logout
        self.on_theme_change = on_theme_change
        self._prefs             = PrefsManager()
        self._swatch_btns: dict[str, ctk.CTkButton] = {}
        self._hdr_frame         = None
        self._hdr_user_lbl      = None
        self._hdr_separator     = None
        self._current_tab       = "appearance"

        self.title("Ustawienia")
        self.geometry("520x660")
        self.resizable(False, False)
        self.grab_set()
        self.focus()
        self.protocol("WM_DELETE_WINDOW", self._safe_destroy)

        self._build_ui()
        self.after(20, lambda: slide_fade_in(self, slide_px=4, duration_ms=60, steps=12))

    def _safe_destroy(self):
        try:
            if self._hdr_separator:
                self._hdr_separator.stop_animation()
        except Exception:
            pass
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def _on_map_update_hex(self, event=None):
        """Odświeża kolory hex tła gdy okno staje się widoczne po zmianie motywu."""
        hbg = getattr(self, '_window_hex_bg', None)
        if hbg and hasattr(hbg, 'update_theme'):
            try:
                if hbg.winfo_exists():
                    hbg.update_theme()
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════════════
    # SZKIELET OKNA
    # ══════════════════════════════════════════════════════════════════

    def _build_ui(self):
        self._window_hex_bg = apply_hex_to_window(self)
        # Gdy okno staje się widoczne (np. po zmianie motywu przez rodzica),
        # wymuszamy odświeżenie kolorów hex tła.
        self.bind("<Map>", self._on_map_update_hex, add="+")
        _accent = self._prefs.get_accent()
        _hdr_bg = ("gray92", _blend_settings_accent(_accent, "#1c1c1c", 0.18))

        # ── Nagłówek ─────────────────────────────────────────────────
        self._hdr_frame = ctk.CTkFrame(self, fg_color=_hdr_bg, corner_radius=0)
        self._hdr_frame.pack(fill="x")

        ctk.CTkLabel(
            self._hdr_frame, text="⚙️  Ustawienia",
            font=ctk.CTkFont(size=19, weight="bold")
        ).pack(side="left", padx=20, pady=14)

        self._hdr_user_lbl = ctk.CTkLabel(
            self._hdr_frame, text=f"👤  {self.user.username}",
            font=ctk.CTkFont(size=12),
            text_color=(_accent, _accent),
        )
        self._hdr_user_lbl.pack(side="right", padx=20)

        # Gradient separator — accent → tło (adaptive)
        self._hdr_separator = AnimatedGradientCanvas(
            self,
            accent=_blend_settings_accent(_accent, _gcard_s(), 0.55),
            base=_gbg_s(),
            anim_mode="slide",
            fps=20,
            period_ms=6000,
            n_bands=1,
            direction="h",
            steps=96,
            height=2,
        )
        self._hdr_separator.pack(fill="x")
        self._hdr_separator.start_animation()

        # ── Pasek zakładek ────────────────────────────────────────────
        tab_bar = ctk.CTkFrame(
            self, fg_color=("gray90", "#181818"), corner_radius=0, height=46
        )
        tab_bar.pack(fill="x")
        tab_bar.pack_propagate(False)

        self._tab_btns: dict[str, ctk.CTkButton] = {}
        for label, tid in [
            ("🎨  Wygląd",         "appearance"),
            ("🔒  Bezpieczeństwo", "security"),
            ("⚙️   System",         "system"),
        ]:
            btn = ctk.CTkButton(
                tab_bar, text=label,
                height=46, corner_radius=0, border_spacing=0,
                font=ctk.CTkFont(size=12),
                fg_color="transparent",
                hover_color=("gray83", "#242424"),
                text_color=("gray35", "gray65"),
                command=lambda t=tid: self._switch_tab(t),
            )
            btn.pack(side="left", padx=1)
            self._tab_btns[tid] = btn

        ctk.CTkFrame(
            self, height=1, corner_radius=0,
            fg_color=("gray78", "#2e2e2e")
        ).pack(fill="x")

        # ── Stopka (pakuj PRZED area żeby pack widział kolejność) ─────
        ctk.CTkFrame(
            self, height=1, corner_radius=0,
            fg_color=("gray78", "#2e2e2e")
        ).pack(side="bottom", fill="x")

        ctk.CTkButton(
            self, text="Zamknij", height=42,
            fg_color="transparent", hover_color=("gray85", "#252525"),
            text_color=("gray30", "gray65"), corner_radius=0,
            command=self._safe_destroy
        ).pack(side="bottom", fill="x")

        # ── Obszar treści — ramki nakładane przez place() + lift() ────
        # Wszystkie 3 ramki zajmują CAŁĄ area naraz (relwidth/relheight=1).
        # _switch_tab() woła .lift() na aktywnej — zero zmian geometrii.
        self._area = ctk.CTkFrame(
            self, fg_color=("gray96", "#1e1e1e"), corner_radius=0
        )
        self._area.pack(fill="both", expand=True)

        _configs = [
            ("appearance", self._build_appearance),
            ("security",   self._build_security),
            ("system",     self._build_system),
        ]

        # FAZA 1 — stwórz WSZYSTKIE ramki zanim uruchomisz jakikolwiek builder.
        # Dzięki temu _tab_frames jest zawsze w pełni wypełniony, nawet jeśli
        # jeden z builderów rzuci wyjątek.
        self._tab_frames: dict[str, ctk.CTkFrame] = {}
        for tab_id, _ in _configs:
            f = ctk.CTkFrame(
                self._area, corner_radius=0,
                fg_color=("gray96", "#1e1e1e"),
            )
            f.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._tab_frames[tab_id] = f

        # FAZA 2 — każda zakładka dostaje CTkScrollableFrame wewnątrz
        # swojej ramki. Ramka ma znane wymiary (z place()), więc
        # CTkScrollableFrame renderuje się poprawnie.
        for tab_id, builder in _configs:
            sc = ctk.CTkScrollableFrame(
                self._tab_frames[tab_id],
                corner_radius=0,
                fg_color="transparent",
                scrollbar_button_color=("gray80", "#2a2a2a"),
                scrollbar_button_hover_color=("gray70", "#3a3a3a"),
            )
            sc.pack(fill="both", expand=True)
            apply_hex_to_scrollable(sc, hex_size=36, glow_max=2, glow_interval_ms=1800)
            builder(sc)

        self._switch_tab("appearance")

    def _switch_tab(self, tab_id: str):
        self._current_tab = tab_id
        accent = self._prefs.get_accent()
        for tid, btn in self._tab_btns.items():
            active = (tid == tab_id)
            btn.configure(
                text_color=(accent, accent) if active else ("gray35", "gray65"),
                fg_color=("gray86", "#202020") if active else "transparent",
            )
        self._tab_frames[tab_id].lift()

    # ══════════════════════════════════════════════════════════════════
    # HELPERS — karty, wiersze
    # ══════════════════════════════════════════════════════════════════

    def _card(self, parent, title: str) -> ctk.CTkFrame:
        """Karta sekcji z nagłówkiem i separatorem."""
        frame = ctk.CTkFrame(parent, corner_radius=14)
        frame.pack(fill="x", padx=20, pady=(0, 14))

        ctk.CTkLabel(
            frame, text=title,
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
        ).pack(fill="x", padx=16, pady=(14, 6))

        ctk.CTkFrame(
            frame, height=1, fg_color=("gray80", "#333")
        ).pack(fill="x", padx=16, pady=(0, 10))

        return frame

    def _setting_row(self, parent, title: str, subtitle: str = ""):
        """Wiersz ustawienia: tekst po lewej, widget po prawej.
        Zwraca `right_frame` — tam pakuj przełączniki, segmenty itp."""
        row = ctk.CTkFrame(parent, fg_color="transparent", height=1)
        row.pack(fill="x", padx=16, pady=(0, 4))

        left = ctk.CTkFrame(row, fg_color="transparent", height=1)
        left.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            left, text=title, font=ctk.CTkFont(size=13), anchor="w"
        ).pack(fill="x")
        if subtitle:
            ctk.CTkLabel(
                left, text=subtitle,
                font=ctk.CTkFont(size=11), text_color="gray", anchor="w",
                wraplength=280, justify="left",
            ).pack(fill="x")

        right = ctk.CTkFrame(row, fg_color="transparent", height=1)
        right.pack(side="right", padx=(12, 0))
        return right

    def _action_btn(self, parent, text: str, command,
                    color="#1f6aa5", hover="#1a5a94",
                    text_color="white"):
        """Przycisk akcji wewnątrz karty."""
        ctk.CTkButton(
            parent, text=text, height=38,
            fg_color=color, hover_color=hover,
            text_color=text_color,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=10,
            command=command,
        ).pack(fill="x", padx=16, pady=(6, 14))

    # ══════════════════════════════════════════════════════════════════
    # ZAKŁADKA: WYGLĄD
    # ══════════════════════════════════════════════════════════════════

    def _build_appearance(self, parent):
        ctk.CTkLabel(parent, text="").pack(pady=2)

        # ── Tryb ciemny/jasny ─────────────────────────────────────────
        card1 = self._card(parent, "🌓  Tryb wyświetlania")
        right1 = self._setting_row(
            card1,
            "Tryb ciemny",
            "Przełącz między jasnym a ciemnym interfejsem.",
        )
        is_dark = ctk.get_appearance_mode() == "Dark"
        self.theme_switch_var = ctk.StringVar(value="on" if is_dark else "off")
        ctk.CTkSwitch(
            right1, text="",
            variable=self.theme_switch_var,
            onvalue="on", offvalue="off",
            command=self._toggle_theme, width=46
        ).pack()

        # ── Kolor akcentu ─────────────────────────────────────────────
        card2 = self._card(parent, "🎨  Kolor akcentu")

        current = self._prefs.get("color_theme")

        # Podgląd wybranego koloru
        preview_row = ctk.CTkFrame(card2, fg_color="transparent")
        preview_row.pack(fill="x", padx=16, pady=(0, 10))

        ctk.CTkLabel(
            preview_row, text="Aktywny:",
            font=ctk.CTkFont(size=12), text_color="gray"
        ).pack(side="left")

        self._theme_name_lbl = ctk.CTkLabel(
            preview_row,
            text=THEMES.get(current, {}).get("label", ""),
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self._theme_name_lbl.pack(side="left", padx=(6, 0))

        # Pasek koloru akcentu (animowany podgląd)
        self._accent_bar = ctk.CTkFrame(
            card2, height=6, corner_radius=3,
            fg_color=THEMES.get(current, {}).get("accent", "#0F52BA")
        )
        self._accent_bar.pack(fill="x", padx=16, pady=(0, 12))

        # Siatka swatchy — 4 kolumny × 3 wiersze (pack zamiast grid)
        COLS = 4
        theme_list_full = list(THEMES.items())
        rows_n = (len(theme_list_full) + COLS - 1) // COLS

        swatch_outer = ctk.CTkFrame(card2, fg_color="transparent")
        swatch_outer.pack(fill="x", padx=16, pady=(0, 16))

        row_frames = []
        for _ in range(rows_n):
            rf = ctk.CTkFrame(swatch_outer, fg_color="transparent")
            rf.pack(anchor="w")
            row_frames.append(rf)

        self._swatch_btns = {}
        for idx, (tid, tdata) in enumerate(theme_list_full):
            r, c = divmod(idx, COLS)
            is_sel = (tid == current)

            btn = ctk.CTkButton(
                row_frames[r],
                text="✔" if is_sel else "",
                width=56, height=56,
                corner_radius=10,
                fg_color=tdata["accent"],
                hover_color=tdata["hover"],
                border_width=3 if is_sel else 0,
                border_color=("gray15", "white"),
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="#ffffff",
                command=lambda t=tid: self._select_color_theme(t),
            )
            btn.pack(side="left", padx=5, pady=5)
            self._swatch_btns[tid] = btn

            lbl = tdata["label"]
            accent_c = tdata["accent"]
            btn.bind(
                "<Enter>",
                lambda e, n=lbl, a=accent_c: (
                    self._theme_name_lbl.configure(text=n),
                    self._accent_bar.configure(fg_color=a),
                ),
                add="+",
            )
            btn.bind(
                "<Leave>",
                lambda e: (
                    self._theme_name_lbl.configure(
                        text=THEMES.get(self._prefs.get("color_theme"), {}).get("label", "")
                    ),
                    self._accent_bar.configure(
                        fg_color=THEMES.get(self._prefs.get("color_theme"), {}).get("accent", "#0F52BA")
                    ),
                ),
                add="+",
            )

        # ── Własny kolor hex ─────────────────────────────────────────────
        current_accent = THEMES.get(current, {}).get("accent", "#0F52BA")

        hex_row = ctk.CTkFrame(card2, fg_color="transparent")
        hex_row.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(hex_row, text="#", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="gray").pack(side="left", padx=(0, 2))

        self._hex_entry = ctk.CTkEntry(
            hex_row, width=90, height=32,
            placeholder_text="4F8EF7",
            font=ctk.CTkFont(family="Courier New", size=12),
        )
        self._hex_entry.pack(side="left", padx=(0, 8))

        self._hex_preview = ctk.CTkFrame(
            hex_row, width=40, height=32, corner_radius=8,
            fg_color=current_accent,
        )
        self._hex_preview.pack(side="left")
        self._hex_preview.pack_propagate(False)

        # Bindingi
        self._hex_debounce_job = None

        def _try_save_hex(val: str) -> bool:
            """Waliduje i zapisuje kolor do prefs. Zwraca True jeśli zapisano."""
            if len(val) != 6:
                return False
            try:
                int(val, 16)
            except ValueError:
                return False
            color = f"#{val}"
            # Szukaj pasującego swatcha
            for tid, tdata in THEMES.items():
                if tdata["accent"].lower() == color.lower():
                    self._select_color_theme(tid)
                    return True
            # Custom — zapisz natychmiast do prefs (przed debounce'em UI)
            self._prefs.set("accent_custom", color)
            self._prefs.set("color_theme", "custom")
            return True

        def _update_hex_ui(val: str):
            """Aktualizuje UI ustawień po wpisaniu koloru (debounce)."""
            if len(val) == 6:
                try:
                    int(val, 16)
                    color = f"#{val}"
                    self._hex_preview.configure(fg_color=color)
                    self._hex_entry.configure(border_color=("gray70", "gray30"))
                    # Sprawdź czy custom (nie pasuje do żadnego swacha)
                    is_custom = not any(
                        tdata["accent"].lower() == color.lower()
                        for tdata in THEMES.values()
                    )
                    if is_custom:
                        for b in self._swatch_btns.values():
                            if b.winfo_exists():
                                b.configure(text="", border_width=0)
                        self._theme_name_lbl.configure(text="Własny")
                        self._accent_bar.configure(fg_color=color)
                        _tint = _blend_settings_accent(color, _gcard_s(), 0.18)
                        if self._hdr_frame and self._hdr_frame.winfo_exists():
                            self._hdr_frame.configure(fg_color=("gray92", _tint))
                        if self._hdr_user_lbl and self._hdr_user_lbl.winfo_exists():
                            self._hdr_user_lbl.configure(text_color=(color, color))
                        if self._hdr_separator and self._hdr_separator.winfo_exists():
                            self._hdr_separator.update_accent(
                                accent=_blend_settings_accent(color, _gcard_s(), 0.55),
                                base=_gbg_s(),
                            )
                        self._switch_tab(self._current_tab)
                        self._update_hex_accents(color)
                except ValueError:
                    self._hex_entry.configure(border_color="#e05252")
            elif len(val) == 0:
                self._hex_preview.configure(fg_color=current_accent)
                self._hex_entry.configure(border_color=("gray70", "gray30"))
            else:
                self._hex_entry.configure(border_color="#f0a500")

        def _on_hex_change(*_):
            val = self._hex_entry.get().strip().lstrip("#")
            # Zapisz prefs NATYCHMIAST (nie debounce'uj) — po zamknięciu settings
            # apply_theme odczyta prawidłowy kolor
            _try_save_hex(val)
            # Debounce tylko dla aktualizacji UI (nagłówki, etykiety)
            if self._hex_debounce_job:
                try:
                    self.after_cancel(self._hex_debounce_job)
                except Exception:
                    pass
            self._hex_debounce_job = self.after(300, lambda: _update_hex_ui(val))

        self._hex_entry.bind("<KeyRelease>", _on_hex_change)
        self._hex_entry.bind("<Return>", lambda e: (
            _try_save_hex(self._hex_entry.get().strip().lstrip("#")),
            _update_hex_ui(self._hex_entry.get().strip().lstrip("#")),
        ))

    # ══════════════════════════════════════════════════════════════════
    # ZAKŁADKA: BEZPIECZEŃSTWO
    # ══════════════════════════════════════════════════════════════════

    def _build_security(self, parent):
        ctk.CTkLabel(parent, text="").pack(pady=2)

        # ── Windows Hello ─────────────────────────────────────────────
        card_wh = self._card(parent, "🪟  Windows Hello")

        right_wh = self._setting_row(
            card_wh,
            "Logowanie biometryczne",
            "Użyj odcisku palca, twarzy lub PIN-u zamiast hasła masterowego.",
        )
        self._wh_badge = ctk.CTkLabel(
            right_wh, text="…",
            font=ctk.CTkFont(size=11), text_color="gray",
            width=90, anchor="e",
        )
        self._wh_badge.pack()

        wh_row = ctk.CTkFrame(card_wh, fg_color="transparent")
        wh_row.pack(fill="x", padx=16, pady=(0, 14))

        self._wh_enable_btn = ctk.CTkButton(
            wh_row, text="✔  Włącz Windows Hello", height=38,
            fg_color="#2d6a4f", hover_color="#40916c",
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=10,
            command=self._wh_enable,
        )
        self._wh_enable_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._wh_disable_btn = ctk.CTkButton(
            wh_row, text="✖  Wyłącz", height=38,
            fg_color=("#ffdddd", "#4a1a1a"),
            hover_color=("#ffc8c8", "#5a2020"),
            text_color=("#c0392b", "#ff8080"),
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=10,
            command=self._wh_disable,
        )
        self._wh_disable_btn.pack(side="left")

        threading.Thread(target=self._wh_check_status, daemon=True).start()

        # ── Windows Hello na ekranie blokady ──────────────────────────
        right_whl = self._setting_row(
            card_wh,
            "Odblokuj przez Windows Hello",
            "Zamiast hasła masterowego — użyj biometrii na ekranie blokady.",
        )
        self._wh_lock_var = ctk.StringVar(
            value="on" if self._prefs.get("wh_lock_unlock") else "off"
        )
        self._wh_lock_switch = ctk.CTkSwitch(
            right_whl, text="",
            variable=self._wh_lock_var,
            onvalue="on", offvalue="off",
            command=self._on_wh_lock_toggle,
            width=46,
        )
        self._wh_lock_switch.pack()

        # ── Auto-lock ─────────────────────────────────────────────────
        card_al = self._card(parent, "⏱  Automatyczne blokowanie")
        self._setting_row(
            card_al,
            "Zablokuj po bezczynności",
            "Aplikacja zablokuje się po wybranym czasie bez aktywności.",
        )
        _al_labels = ["1 min", "5 min", "15 min", "30 min", "1 godz", "Nigdy"]
        _al_values = [60, 300, 900, 1800, 3600, 0]
        _al_map    = dict(zip(_al_labels, _al_values))
        _al_rev    = {v: k for k, v in _al_map.items()}
        cur_al = self._prefs.get("auto_lock_seconds")
        self._al_var = ctk.StringVar(value=_al_rev.get(cur_al, "5 min"))
        self._al_map = _al_map

        ctk.CTkSegmentedButton(
            card_al,
            values=_al_labels,
            variable=self._al_var,
            command=self._on_al_change,
        ).pack(fill="x", padx=16, pady=(0, 14))

        # ── Zmiana hasła masterowego ──────────────────────────────────
        card_pwd = self._card(parent, "🔑  Hasło masterowe")
        self._setting_row(
            card_pwd,
            "Zmiana hasła masterowego",
            "Wymaga podania aktualnego hasła oraz kodu 2FA.",
        )
        self._action_btn(
            card_pwd, "Zmień hasło masterowe",
            self._show_reset_password,
            color="#1f6aa5", hover="#1a5a94",
        )

        # ── Reset 2FA ─────────────────────────────────────────────────
        card_2fa = self._card(parent, "📱  Uwierzytelnianie dwuetapowe")
        self._setting_row(
            card_2fa,
            "Wygeneruj nowy kod QR",
            "Przydatne przy zmianie telefonu lub aplikacji 2FA.",
        )
        self._action_btn(
            card_2fa, "Wygeneruj nowy QR",
            self._show_reset_2fa,
            color="#2d6a4f", hover="#40916c",
        )

        # ── Auto-Type ─────────────────────────────────────────────────
        card_at = self._card(parent, "⌨️  Auto-Type")

        self._setting_row(
            card_at,
            "Opóźnienie przed wpisaniem",
            "Czas na przełączenie się na okno logowania po kliknięciu Auto-type.",
        )
        _at_labels = ["1s", "2s", "3s", "5s"]
        _at_values = [1, 2, 3, 5]
        _at_map    = dict(zip(_at_labels, _at_values))
        _at_rev    = {v: k for k, v in _at_map.items()}
        cur_at = self._prefs.get("autotype_delay") or 2
        self._at_var = ctk.StringVar(value=_at_rev.get(int(cur_at), "2s"))
        self._at_map = _at_map

        ctk.CTkSegmentedButton(
            card_at,
            values=_at_labels,
            variable=self._at_var,
            command=self._on_at_delay_change,
        ).pack(fill="x", padx=16, pady=(0, 10))

        self._setting_row(
            card_at,
            "Sekwencja wpisywania",
            "Tokeny: {USERNAME} {TAB} {PASSWORD} {ENTER} {DELAY=ms}",
        )
        cur_seq = self._prefs.get("autotype_sequence") or "{USERNAME}{TAB}{PASSWORD}{ENTER}"
        self._at_seq_var = ctk.StringVar(value=cur_seq)
        seq_row = ctk.CTkFrame(card_at, fg_color="transparent")
        seq_row.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkEntry(
            seq_row,
            textvariable=self._at_seq_var,
            font=ctk.CTkFont(family="Courier New", size=12),
            height=36,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            seq_row,
            text="Zapisz",
            width=70, height=36,
            fg_color=self._prefs.get_accent(),
            hover_color=self._prefs.get_accent_hover(),
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_at_seq_save,
        ).pack(side="left")

    # ══════════════════════════════════════════════════════════════════
    # ZAKŁADKA: SYSTEM
    # ══════════════════════════════════════════════════════════════════

    def _build_system(self, parent):
        ctk.CTkLabel(parent, text="").pack(pady=2)

        # ── Ctrl+W ───────────────────────────────────────────────────
        card_w = self._card(parent, "⌨️  Skrót Ctrl+W")
        right_w = self._setting_row(
            card_w,
            "Akcja Ctrl+W",
            "Co ma robić Ctrl+W w głównym oknie aplikacji.",
        )
        current_cw = self._prefs.get("ctrl_w_action") or "minimize"
        self._ctrl_w_var = ctk.StringVar(
            value="Minimalizuj" if current_cw == "minimize" else "Zamknij"
        )
        ctk.CTkSegmentedButton(
            right_w,
            values=["Minimalizuj", "Zamknij"],
            variable=self._ctrl_w_var,
            command=self._on_ctrl_w_change,
            width=200,
        ).pack()

        # ── Autostart ─────────────────────────────────────────────────
        card_as = self._card(parent, "🚀  Autostart")
        right_as = self._setting_row(
            card_as,
            "Uruchamiaj przy starcie Windows",
            "AegisVault uruchomi się automatycznie po zalogowaniu do systemu.",
        )
        self._autostart_var = ctk.StringVar(
            value="on" if autostart.is_enabled() else "off"
        )
        ctk.CTkSwitch(
            right_as, text="",
            variable=self._autostart_var,
            onvalue="on", offvalue="off",
            command=self._on_autostart_toggle, width=46,
        ).pack()

        # ── Automatyczny backup ───────────────────────────────────────
        card_backup = self._card(parent, "💾  Automatyczny backup")
        self._setting_row(
            card_backup,
            "Częstotliwość",
            "Backup zaszyfrowany zapisywany w folderze danych aplikacji.",
        )
        _backup_labels   = ["Wyłączony", "Codziennie", "Co 3 dni", "Tygodniowo", "Miesięcznie"]
        _backup_values   = ["wyłączony", "codziennie", "co 3 dni", "tygodniowo", "miesięcznie"]
        _label_to_val    = dict(zip(_backup_labels, _backup_values))
        _val_to_label    = dict(zip(_backup_values, _backup_labels))
        _cur_interval    = self._prefs.get("backup_interval") or "wyłączony"
        if _cur_interval not in _backup_values:
            _cur_interval = "wyłączony"
        self._backup_interval_var = ctk.StringVar(value=_val_to_label.get(_cur_interval, "Wyłączony"))

        def _on_backup_interval_change(label: str):
            self._prefs.set("backup_interval", _label_to_val.get(label, "wyłączony"))

        ctk.CTkOptionMenu(
            card_backup,
            values=_backup_labels,
            variable=self._backup_interval_var,
            command=_on_backup_interval_change,
            width=220,
        ).pack(padx=16, pady=(0, 8), anchor="w")

        self._action_btn(
            card_backup,
            "💾  Wykonaj backup teraz",
            self._do_backup_now,
        )

        # ── Strefa niebezpieczna ──────────────────────────────────────
        card_del = self._card(parent, "⚠️  Strefa niebezpieczna")
        self._setting_row(
            card_del,
            "Usuń konto",
            "Trwale usuwa konto i wszystkie zapisane hasła.\nOperacji nie można cofnąć!",
        )
        self._action_btn(
            card_del, "🗑️  Usuń konto",
            self._show_delete_account,
            color=("#ffdddd", "#4a1a1a"),
            hover=("#ffc8c8", "#5a2020"),
            text_color=("#c0392b", "#ff8080"),
        )

        # ── Logi ──────────────────────────────────────────────────────────────────
        card_logs = self._card(parent, "📋  Logi aplikacji")

        ctk.CTkLabel(
            card_logs,
            text="Pliki logów przechowywane w AppData\\AegisVault\\logs\\",
            font=ctk.CTkFont(size=12), text_color="gray", anchor="w"
        ).pack(padx=15, pady=(0, 8), fill="x")

        # wiersz: etykieta + wartość
        logs_row = ctk.CTkFrame(card_logs, fg_color="transparent")
        logs_row.pack(fill="x", padx=15, pady=(0, 4))

        ctk.CTkLabel(logs_row, text="Przechowuj logi przez:", font=ctk.CTkFont(size=13), anchor="w").pack(side="left")
        _days_var = ctk.StringVar(value=f"{PrefsManager().get('log_retention_days')} dni")
        _days_label = ctk.CTkLabel(logs_row, textvariable=_days_var, font=ctk.CTkFont(size=13, weight="bold"), width=60, anchor="e")
        _days_label.pack(side="right")

        def _on_log_slider(val):
            days = int(val)
            _days_var.set(f"{days} dni")
            PrefsManager().set("log_retention_days", days)
            cleanup_old_logs(days)

        _accent = self._prefs.get_accent()
        _accent_hover = _blend_settings_accent(_accent, "#1c1c1c", 0.72)
        _log_slider = ctk.CTkSlider(
            card_logs,
            from_=1, to=30, number_of_steps=29,
            command=_on_log_slider,
            button_color=_accent,
            button_hover_color=_accent_hover,
            progress_color=_accent,
        )
        _log_slider.set(PrefsManager().get("log_retention_days"))
        _log_slider.pack(fill="x", padx=15, pady=(0, 12))

    # ══════════════════════════════════════════════════════════════════
    # LOGIKA — MOTYW
    # ══════════════════════════════════════════════════════════════════

    def _select_color_theme(self, theme_id: str):
        self._prefs.set("color_theme", theme_id)

        for tid, btn in self._swatch_btns.items():
            sel = (tid == theme_id)
            btn.configure(
                text="✔" if sel else "",
                border_width=3 if sel else 0,
                border_color=("gray15", "white"),
            )

        tdata = self._prefs.get_theme_colors()
        self._theme_name_lbl.configure(text=tdata.get("label", ""))
        _new_accent = tdata.get("accent", "#0F52BA")
        self._accent_bar.configure(fg_color=_new_accent)

        # ── Live update nagłówka tego okna ───────────────────────────
        _tint = _blend_settings_accent(_new_accent, _gcard_s(), 0.18)
        if self._hdr_frame and self._hdr_frame.winfo_exists():
            self._hdr_frame.configure(fg_color=("gray92", _tint))
        if self._hdr_user_lbl and self._hdr_user_lbl.winfo_exists():
            self._hdr_user_lbl.configure(text_color=(_new_accent, _new_accent))
        if self._hdr_separator and self._hdr_separator.winfo_exists():
            self._hdr_separator.update_accent(
                accent=_blend_settings_accent(_new_accent, _gcard_s(), 0.55),
                base=_gbg_s(),
            )

        # Odśwież kolor aktywnej zakładki
        self._switch_tab(self._current_tab)

        # ── Aktualizuj hex tło okna ustawień ──────────────────────────
        self._update_hex_accents(_new_accent)

        if self.on_theme_change:
            self.on_theme_change(theme_id)

        # ── Synchronizuj hex entry z wybranym swatchem ────────────────
        if (hasattr(self, "_hex_entry") and self._hex_entry.winfo_exists()
                and hasattr(self, "_hex_preview") and self._hex_preview.winfo_exists()):
            _ha = self._prefs.get_accent()
            self._hex_entry.delete(0, "end")
            self._hex_entry.insert(0, _ha[1:])
            self._hex_preview.configure(fg_color=_ha)
            self._hex_entry.configure(border_color=("gray70", "gray30"))

    def _update_hex_accents(self, new_accent: str) -> None:
        """Aktualizuje kolor akcentu hex tła we wszystkich warstwach okna ustawień."""
        # Warstwa okna (HexBackground z apply_hex_to_window)
        hbg = getattr(self, '_window_hex_bg', None)
        if hbg is not None:
            try:
                if hbg.winfo_exists() and hasattr(hbg, 'update_accent'):
                    hbg.update_accent(new_accent)
            except Exception:
                pass
        # Warstwy scrollable w zakładkach (CTkScrollableFrame._parent_canvas)
        for tab_frame in getattr(self, '_tab_frames', {}).values():
            try:
                for child in tab_frame.winfo_children():
                    # CTkScrollableFrame pakuje HexBackground wewnątrz i _parent_canvas
                    sc = child  # CTkScrollableFrame
                    if hasattr(sc, '_parent_canvas'):
                        pc = sc._parent_canvas
                        if hasattr(pc, '_hex_update_accent'):
                            pc._hex_update_accent(new_accent)
                    for sub in child.winfo_children():
                        if hasattr(sub, 'update_accent'):
                            try:
                                sub.update_accent(new_accent)
                            except Exception:
                                pass
            except Exception:
                pass

    def _toggle_theme(self):
        if self.theme_switch_var.get() == "on":
            ctk.set_appearance_mode("dark")
        else:
            ctk.set_appearance_mode("light")
        # GradientCanvas nie reaguje na zmianę trybu CTK — wymuszamy odświeżenie.
        # after(50) daje CTK czas na przemalowanie widgetów zanim przerysujemy gradienty.
        self.after(50, lambda: self._select_color_theme(self._prefs.get("color_theme")))

    # ══════════════════════════════════════════════════════════════════
    # LOGIKA — SYSTEM
    # ══════════════════════════════════════════════════════════════════

    def _on_ctrl_w_change(self, label: str):
        self._prefs.set("ctrl_w_action",
                        "minimize" if label == "Minimalizuj" else "close")

    def _on_autostart_toggle(self):
        if self._autostart_var.get() == "on":
            if not autostart.enable():
                self._autostart_var.set("off")
                show_error("Błąd", "Nie udało się dodać wpisu autostartu.", parent=self)
        else:
            autostart.disable()

    def _do_backup_now(self):
        from utils.auto_backup import do_backup
        import os as _os
        path = do_backup(self.db, self.crypto, self.user, self._prefs)
        if path:
            fname = _os.path.basename(path)
            show_success("Backup", f"Backup zapisany:\n{fname}", parent=self)
        else:
            show_error("Backup", "Nie udało się wykonać backupu.\nSprawdź logi aplikacji.", parent=self)

    # ══════════════════════════════════════════════════════════════════
    # LOGIKA — WINDOWS HELLO
    # ══════════════════════════════════════════════════════════════════

    def _wh_check_status(self):
        status  = wh.check_availability()
        enabled = wh.has_credential(self.user.username)
        self.after(0, lambda: self._wh_update_ui(status, enabled))

    def _wh_update_ui(self, status: str, enabled: bool):
        try:
            if not self._wh_badge.winfo_exists():
                return
        except Exception:
            return
        available = (status == "Available")
        if not available:
            msg = wh.STATUS_MESSAGES.get(status, "Niedostępne")
            self._wh_badge.configure(text="Niedostępne", text_color="#e05252")
            self._wh_enable_btn.configure(state="disabled", text=msg)
            self._wh_disable_btn.configure(state="disabled")
        elif enabled:
            self._wh_badge.configure(text="✔  Włączone", text_color="#4caf50")
            self._wh_enable_btn.configure(state="disabled", text="✔  Włącz Windows Hello")
            self._wh_disable_btn.configure(state="normal")
        else:
            self._wh_badge.configure(text="Wyłączone", text_color="gray")
            self._wh_enable_btn.configure(state="normal", text="✔  Włącz Windows Hello")
            self._wh_disable_btn.configure(state="disabled")

    def _wh_enable(self):
        dialog = ctk.CTkToplevel(self)
        dialog.transient(self)
        dialog.title("Włącz Windows Hello")
        dialog.geometry("400x300")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift()

        ctk.CTkLabel(
            dialog, text="🪟  Włącz Windows Hello",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(22, 4))
        _sep_wh = AnimatedGradientCanvas(
            dialog,
            accent=self._prefs.get_accent(),
            base=_gcard_s(),
            anim_mode="slide",
            period_ms=6000,
            fps=20,
            n_bands=1,
            direction="h",
            steps=64,
            height=2,
        )
        _sep_wh.pack(fill="x", padx=0, pady=(0, 8))
        _sep_wh.start_animation()
        ctk.CTkLabel(
            dialog,
            text="Potwierdź hasłem masterowym,\naby skojarzyć konto z Windows Hello.",
            font=ctk.CTkFont(size=12), text_color="gray", justify="center"
        ).pack(pady=(0, 10))

        frame = ctk.CTkFrame(dialog, corner_radius=12)
        frame.pack(padx=20, fill="both", expand=True, pady=(0, 20))

        ctk.CTkLabel(
            frame, text="Hasło masterowe", anchor="w"
        ).pack(padx=15, pady=(15, 2), fill="x")
        entry_pwd = ctk.CTkEntry(
            frame, placeholder_text="Wpisz hasło...", show="•", height=38
        )
        entry_pwd.pack(padx=15, fill="x")
        dialog.after(250, entry_pwd.focus_set)

        err_lbl = ctk.CTkLabel(
            frame, text="", font=ctk.CTkFont(size=11), text_color="#e05252"
        )
        err_lbl.pack(padx=15, pady=(4, 0))

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(padx=15, pady=(10, 15), fill="x")

        ctk.CTkButton(
            btn_row, text="Anuluj", height=36,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"),
            hover_color=("gray85", "#2a2a2a"),
            text_color=("gray20", "gray80"),
            corner_radius=10, command=dialog.destroy
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))

        confirm_btn = ctk.CTkButton(
            btn_row, text="Dalej →", height=36,
            fg_color="#2d6a4f", hover_color="#40916c",
            font=ctk.CTkFont(weight="bold"), corner_radius=10,
        )
        confirm_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))

        def _confirm():
            if not verify_master_password(entry_pwd.get(),
                                          self.user.master_password_hash):
                err_lbl.configure(text="Nieprawidłowe hasło masterowe!")
                return
            confirm_btn.configure(state="disabled", text="⏳  Oczekiwanie…")
            err_lbl.configure(text="")
            # Oderwij focus od entry_pwd — inaczej PIN wpisywany w dialog WH
            # trafia do pola hasła (widget focus ≠ window focus).
            confirm_btn.focus_set()
            dialog.lift()    # dialog WH wyskakuje nad oknem ustawień
            dialog.focus_force()
            threading.Thread(
                target=self._wh_do_enable, args=(dialog, entry_pwd.get()),
                daemon=True
            ).start()

        confirm_btn.configure(command=_confirm)
        entry_pwd.bind("<Return>", lambda e: _confirm())

    def _wh_do_enable(self, dialog, master_password: str):
        verified = wh.verify("Włącz Windows Hello dla AegisVault")
        if not verified:
            self.after(0, lambda: show_error(
                "Windows Hello",
                "Weryfikacja anulowana lub nieudana.\nSpróbuj ponownie.",
                parent=dialog
            ))
            return
        ok = wh.store_credential(self.user.username, master_password)
        if ok:
            wh.invalidate_cache()
            self.after(0, lambda: (
                dialog.destroy(),
                show_success(
                    "Windows Hello",
                    "Windows Hello zostało włączone.\nMożesz teraz logować się bez hasła.",
                    parent=self
                ),
                self._wh_update_ui("Available", True),
            ))
        else:
            self.after(0, lambda: show_error(
                "Błąd",
                "Nie można zapisać poświadczeń w Credential Manager.",
                parent=dialog
            ))

    def _wh_disable(self):
        if not ask_yes_no(
            "Wyłącz Windows Hello",
            "Czy na pewno chcesz wyłączyć logowanie Windows Hello?\n"
            "Będziesz musiał ponownie wpisywać hasło masterowe.",
            parent=self, yes_text="Wyłącz"
        ):
            return
        self._wh_disable_btn.configure(state="disabled", text="⏳  Weryfikacja…")
        # Oderwij focus od wszelkich entry — PIN z WH nie może trafiać do pola tekstowego.
        self._wh_disable_btn.focus_set()
        self.lift()          # dialog WH wyskakuje nad oknem ustawień
        self.focus_force()

        def _do():
            verified = wh.verify("Wyłącz Windows Hello — AegisVault")
            if not verified:
                self.after(0, lambda: (
                    self._wh_disable_btn.configure(
                        state="normal", text="✖  Wyłącz"
                    ),
                    show_error("Windows Hello",
                               "Weryfikacja nieudana lub anulowana.", parent=self),
                ))
                return
            wh.delete_credential(self.user.username)
            wh.invalidate_cache()
            self.after(0, lambda: (
                show_success("Windows Hello",
                             "Windows Hello zostało wyłączone.", parent=self),
                self._wh_update_ui("Available", False),
            ))

        threading.Thread(target=_do, daemon=True).start()

    def _on_wh_lock_toggle(self):
        self._prefs.set("wh_lock_unlock", self._wh_lock_var.get() == "on")

    def _on_al_change(self, label: str):
        self._prefs.set("auto_lock_seconds", self._al_map[label])

    def _on_at_delay_change(self, value: str):
        seconds = self._at_map.get(value, 2)
        self._prefs.set("autotype_delay", seconds)

    def _on_at_seq_save(self):
        seq = self._at_seq_var.get().strip()
        if not seq:
            seq = "{USERNAME}{TAB}{PASSWORD}{ENTER}"
            self._at_seq_var.set(seq)
        self._prefs.set("autotype_sequence", seq)
        # Toast jeśli dostępny (MainWindow może nasłuchiwać, ale Settings jest niezależne)
        try:
            from gui.toast import ToastManager
            # Szybkie potwierdzenie przez zmianę tekstu przycisku
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════
    # LOGIKA — ZMIANA HASŁA MASTEROWEGO
    # ══════════════════════════════════════════════════════════════════

    def _show_reset_password(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Zmiana hasła masterowego")
        dialog.geometry("420x480")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus()

        ctk.CTkLabel(
            dialog, text="🔑  Zmiana hasła masterowego",
            font=ctk.CTkFont(size=17, weight="bold")
        ).pack(pady=(25, 4))
        _sep_pwd = AnimatedGradientCanvas(
            dialog,
            accent=self._prefs.get_accent(),
            base=_gcard_s(),
            anim_mode="slide",
            period_ms=6000,
            fps=20,
            n_bands=1,
            direction="h",
            steps=64,
            height=2,
        )
        _sep_pwd.pack(fill="x", padx=0, pady=(0, 8))
        _sep_pwd.start_animation()

        frame = ctk.CTkFrame(dialog, corner_radius=12)
        frame.pack(padx=20, fill="both", expand=True, pady=(0, 20))

        def _field(lbl, ph, secret=False):
            ctk.CTkLabel(frame, text=lbl, anchor="w").pack(
                padx=15, pady=(12, 2), fill="x"
            )
            e = ctk.CTkEntry(frame, placeholder_text=ph,
                             show="•" if secret else "", height=38, corner_radius=10)
            e.pack(padx=15, fill="x")
            return e

        e_old   = _field("Aktualne hasło masterowe", "Wpisz aktualne hasło...", True)
        e_new   = _field("Nowe hasło masterowe",      "Min. 8 znaków...",       True)
        e_new2  = _field("Powtórz nowe hasło",        "Powtórz nowe hasło...", True)
        e_totp  = _field("Kod 2FA",                   "000000")
        e_old.focus()

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(padx=15, pady=(14, 15), fill="x")

        ctk.CTkButton(
            btn_row, text="Anuluj", height=38,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"),
            hover_color=("gray85", "#2a2a2a"),
            text_color=("gray20", "gray80"), corner_radius=10,
            command=dialog.destroy
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            btn_row, text="Zmień hasło", height=38,
            fg_color="#1f6aa5", hover_color="#1a5a94",
            font=ctk.CTkFont(weight="bold"), corner_radius=10,
            command=lambda: self._on_reset_password(
                dialog,
                e_old.get(), e_new.get(), e_new2.get(), e_totp.get().strip()
            )
        ).pack(side="left", fill="x", expand=True, padx=(6, 0))

    def _on_reset_password(self, dialog, old_pwd, new_pwd, new_pwd2, totp_code):
        if not all([old_pwd, new_pwd, new_pwd2, totp_code]):
            show_error("Błąd", "Wypełnij wszystkie pola!", parent=dialog)
            return
        if len(new_pwd) < 8:
            show_error("Błąd", "Nowe hasło musi mieć co najmniej 8 znaków!", parent=dialog)
            return
        if new_pwd != new_pwd2:
            show_error("Błąd", "Nowe hasła nie są identyczne!", parent=dialog)
            return
        if not verify_master_password(old_pwd, self.user.master_password_hash):
            show_error("Błąd", "Aktualne hasło jest nieprawidłowe!", parent=dialog)
            return
        if not TOTPManager(secret=self.user.totp_secret).verify(totp_code):
            show_error("Błąd 2FA", "Nieprawidłowy kod 2FA!", parent=dialog)
            return
        try:
            new_salt   = generate_salt()
            new_crypto = CryptoManager(new_pwd, new_salt)
            for entry in self.db.get_all_passwords(self.user):
                pt = self.crypto.decrypt(entry.encrypted_password)
                entry.encrypted_password = new_crypto.encrypt(pt)
            self.user.master_password_hash = hash_master_password(new_pwd)
            self.user.salt = new_salt
            self.db.session.commit()
            self.crypto = new_crypto
            show_success("Sukces", "Hasło masterowe zostało zmienione.", parent=dialog)
            dialog.destroy()
        except Exception as e:
            show_error("Błąd", f"Wystąpił błąd:\n{e}", parent=dialog)

    # ══════════════════════════════════════════════════════════════════
    # LOGIKA — RESET 2FA
    # ══════════════════════════════════════════════════════════════════

    def _show_reset_2fa(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Reset 2FA")
        dialog.geometry("420x560")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus()

        container = ctk.CTkFrame(dialog, fg_color="transparent")
        container.pack(fill="both", expand=True)

        def show_step1():
            for w in container.winfo_children():
                w.destroy()

            ctk.CTkLabel(
                container, text="📱  Reset 2FA — Krok 1/2",
                font=ctk.CTkFont(size=17, weight="bold")
            ).pack(pady=(24, 4))
            _sep_2fa1 = AnimatedGradientCanvas(
                container,
                accent=self._prefs.get_accent(),
                base=_gcard_s(),
                anim_mode="slide",
                period_ms=6000,
                fps=20,
                n_bands=1,
                direction="h",
                steps=64,
                height=2,
            )
            _sep_2fa1.pack(fill="x", padx=0, pady=(0, 8))
            _sep_2fa1.start_animation()
            ctk.CTkLabel(
                container,
                text="Potwierdź tożsamość hasłem masterowym,\naby wygenerować nowy kod QR.",
                font=ctk.CTkFont(size=12), text_color="gray", justify="center"
            ).pack(pady=(0, 16))

            frame = ctk.CTkFrame(container, corner_radius=12)
            frame.pack(padx=20, fill="x")

            ctk.CTkLabel(frame, text="Hasło masterowe", anchor="w").pack(
                padx=15, pady=(15, 2), fill="x"
            )
            entry_pwd = ctk.CTkEntry(
                frame, placeholder_text="Wpisz hasło...", show="•", height=38
            )
            entry_pwd.pack(padx=15, fill="x")
            entry_pwd.focus()

            err_lbl = ctk.CTkLabel(
                frame, text="", font=ctk.CTkFont(size=11), text_color="#e05252"
            )
            err_lbl.pack(padx=15, pady=(4, 12))

            def ok1():
                if not verify_master_password(entry_pwd.get(),
                                              self.user.master_password_hash):
                    err_lbl.configure(text="Nieprawidłowe hasło masterowe!")
                    return
                show_step2()

            entry_pwd.bind("<Return>", lambda e: ok1())

            btn_row = ctk.CTkFrame(container, fg_color="transparent")
            btn_row.pack(padx=20, pady=12, fill="x")

            ctk.CTkButton(
                btn_row, text="Anuluj", height=38,
                fg_color="transparent", border_width=1,
                border_color=("gray70", "gray40"),
                hover_color=("gray85", "#2a2a2a"),
                text_color=("gray20", "gray80"), corner_radius=10,
                command=dialog.destroy
            ).pack(side="left", fill="x", expand=True, padx=(0, 5))

            ctk.CTkButton(
                btn_row, text="Dalej →", height=38,
                fg_color="#2d6a4f", hover_color="#40916c",
                font=ctk.CTkFont(weight="bold"), corner_radius=10,
                command=ok1
            ).pack(side="left", fill="x", expand=True, padx=(5, 0))

        def show_step2():
            for w in container.winfo_children():
                w.destroy()

            new_totp = TOTPManager()
            logger.info(f"Reset 2FA — generowanie nowego QR: użytkownik={self.user.username}")

            ctk.CTkLabel(
                container, text="📱  Reset 2FA — Krok 2/2",
                font=ctk.CTkFont(size=17, weight="bold")
            ).pack(pady=(20, 4))
            _sep_2fa2 = AnimatedGradientCanvas(
                container,
                accent=self._prefs.get_accent(),
                base=_gcard_s(),
                anim_mode="slide",
                period_ms=6000,
                fps=20,
                n_bands=1,
                direction="h",
                steps=64,
                height=2,
            )
            _sep_2fa2.pack(fill="x", padx=0, pady=(0, 8))
            _sep_2fa2.start_animation()
            ctk.CTkLabel(
                container,
                text="Zeskanuj nowy kod QR w aplikacji\nuwierzytelniającej i wpisz kod.",
                font=ctk.CTkFont(size=12), text_color="gray", justify="center"
            ).pack(pady=(0, 8))

            qr_img = new_totp.get_qr_image(self.user.username).resize((180, 180), Image.NEAREST)
            logger.debug(f"QR reset 2FA: rozmiar={qr_img.size}, tryb={qr_img.mode}")
            qr_ctk = ctk.CTkImage(light_image=qr_img, dark_image=qr_img,
                                   size=(180, 180))
            qr_lbl = ctk.CTkLabel(container, image=qr_ctk, text="")
            qr_lbl.pack()
            qr_lbl._qr = qr_ctk  # zapobiegaj GC

            ctk.CTkLabel(
                container,
                text="Po zeskanowaniu wpisz kod aby potwierdzić:",
                font=ctk.CTkFont(size=12), text_color="gray"
            ).pack(pady=(10, 4))

            entry_code = ctk.CTkEntry(
                container, placeholder_text="000000",
                height=46, font=ctk.CTkFont(size=22), justify="center"
            )
            entry_code.pack(padx=20, fill="x")
            entry_code.focus()

            err2 = ctk.CTkLabel(
                container, text="", font=ctk.CTkFont(size=11), text_color="#e05252"
            )
            err2.pack(pady=(4, 0))

            def save():
                if not new_totp.verify(entry_code.get().strip()):
                    logger.warning(f"Błędny kod przy reset 2FA: użytkownik={self.user.username}")
                    err2.configure(text="Nieprawidłowy kod!")
                    entry_code.delete(0, "end")
                    return
                self.user.totp_secret = new_totp.secret
                logger.info(f"Reset 2FA zakończony sukcesem: użytkownik={self.user.username}")
                self.db.session.commit()
                show_success("2FA zaktualizowane",
                             "Nowy kod QR zapisany.\nOd teraz używaj nowego kodu.",
                             parent=dialog)
                dialog.destroy()

            entry_code.bind("<Return>", lambda e: save())

            btn_row2 = ctk.CTkFrame(container, fg_color="transparent")
            btn_row2.pack(padx=20, pady=10, fill="x")

            ctk.CTkButton(
                btn_row2, text="← Wróć", height=38,
                fg_color="transparent", border_width=1,
                border_color=("gray70", "gray40"),
                hover_color=("gray85", "#2a2a2a"),
                text_color=("gray20", "gray80"), corner_radius=10,
                command=show_step1
            ).pack(side="left", fill="x", expand=True, padx=(0, 5))

            ctk.CTkButton(
                btn_row2, text="💾  Zapisz nowy QR", height=38,
                fg_color="#2d6a4f", hover_color="#40916c",
                font=ctk.CTkFont(weight="bold"), corner_radius=10,
                command=save
            ).pack(side="left", fill="x", expand=True, padx=(5, 0))

        show_step1()

    # ══════════════════════════════════════════════════════════════════
    # LOGIKA — USUNIĘCIE KONTA
    # ══════════════════════════════════════════════════════════════════

    def _show_delete_account(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Usuń konto")
        dialog.geometry("420x360")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus()

        ctk.CTkLabel(
            dialog, text="⚠️  Usuń konto",
            font=ctk.CTkFont(size=17, weight="bold"), text_color="#e05252"
        ).pack(pady=(25, 4))
        _sep_del = AnimatedGradientCanvas(
            dialog,
            accent="#e05252",
            base=_gcard_s(),
            anim_mode="slide",
            period_ms=6000,
            fps=20,
            n_bands=1,
            direction="h",
            steps=64,
            height=2,
        )
        _sep_del.pack(fill="x", padx=0, pady=(0, 8))
        _sep_del.start_animation()
        ctk.CTkLabel(
            dialog,
            text="Ta operacja jest nieodwracalna!\nWszystkie zapisane hasła zostaną trwale usunięte.",
            font=ctk.CTkFont(size=12), text_color="gray", justify="center"
        ).pack(pady=(0, 12))

        frame = ctk.CTkFrame(dialog, corner_radius=12)
        frame.pack(padx=20, fill="both", expand=True, pady=(0, 20))

        ctk.CTkLabel(frame, text="Hasło masterowe", anchor="w").pack(
            padx=15, pady=(15, 2), fill="x"
        )
        entry_pwd = ctk.CTkEntry(
            frame, placeholder_text="Wpisz hasło...", show="•", height=38
        )
        entry_pwd.pack(padx=15, fill="x")

        ctk.CTkLabel(frame, text="Kod 2FA", anchor="w").pack(
            padx=15, pady=(10, 2), fill="x"
        )
        entry_totp = ctk.CTkEntry(
            frame, placeholder_text="000000",
            height=42, font=ctk.CTkFont(size=18), justify="center"
        )
        entry_totp.pack(padx=15, fill="x")

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(padx=15, pady=(14, 15), fill="x")

        ctk.CTkButton(
            btn_row, text="Anuluj", height=38,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"),
            hover_color=("gray85", "#2a2a2a"),
            text_color=("gray20", "gray80"), corner_radius=10,
            command=dialog.destroy
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            btn_row, text="🗑️  Usuń konto", height=38,
            fg_color="#8b2020", hover_color="#a02525",
            font=ctk.CTkFont(weight="bold"), corner_radius=10,
            command=lambda: self._on_delete_account(
                dialog, entry_pwd.get(), entry_totp.get().strip()
            )
        ).pack(side="left", fill="x", expand=True, padx=(6, 0))

    def _on_delete_account(self, dialog, password, totp_code):
        if not password or not totp_code:
            show_error("Błąd", "Wypełnij wszystkie pola!", parent=dialog)
            return
        if not verify_master_password(password, self.user.master_password_hash):
            show_error("Błąd", "Nieprawidłowe hasło masterowe!", parent=dialog)
            return
        if not TOTPManager(secret=self.user.totp_secret).verify(totp_code):
            show_error("Błąd 2FA", "Nieprawidłowy kod 2FA!", parent=dialog)
            return
        if not ask_yes_no(
            "Ostatnie ostrzeżenie",
            f"Czy na pewno chcesz usunąć konto '{self.user.username}'?\n\n"
            "Wszystkie hasła zostaną trwale usunięte i NIE będzie możliwości ich odzyskania!",
            parent=dialog, yes_text="Usuń konto", destructive=True
        ):
            return
        try:
            self.db.session.delete(self.user)
            self.db.session.commit()
            show_info("Konto usunięte",
                      "Konto zostało pomyślnie usunięte.", parent=dialog)
            dialog.destroy()
            self.destroy()
            if self.on_logout:
                self.on_logout()
        except Exception as e:
            show_error("Błąd", f"Wystąpił błąd:\n{e}", parent=dialog)
