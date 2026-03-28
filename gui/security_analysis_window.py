"""
security_analysis_window.py - Dashboard analizy bezpieczeństwa haseł
=====================================================================
Pokazuje:
- Ogólny wynik bezpieczeństwa
- Słabe hasła
- Zduplikowane hasła
- Stare hasła (>90 dni)
"""

import customtkinter as ctk
from datetime import datetime, timezone
from utils.password_strength import check_strength
from utils.prefs_manager import PrefsManager
from gui.gradient import GradientCanvas, AnimatedGradientCanvas
from gui.animations import slide_fade_in
from gui.hex_background import apply_hex_to_scrollable, apply_hex_to_window

def _blend(accent: str, base: str, alpha: float) -> str:
    def _p(c):
        c = c.lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    ar, ag, ab = _p(accent)
    br, bg_, bb = _p(base)
    return (f"#{int(br+(ar-br)*alpha):02x}"
            f"{int(bg_+(ag-bg_)*alpha):02x}"
            f"{int(bb+(ab-bb)*alpha):02x}")


class SecurityAnalysisWindow(ctk.CTkToplevel):
    def __init__(self, parent, db, crypto, user):
        super().__init__(parent)

        self.db = db
        self.crypto = crypto
        self.user = user
        self._accent = PrefsManager().get_accent()   # czytane przy każdym otwarciu

        self.title("Analiza bezpieczeństwa")
        self.geometry("560x680")
        self.resizable(False, False)
        self.grab_set()
        self.focus()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._analyse()
        self._build_ui()
        self.after(10, lambda: slide_fade_in(self))

    # ──────────────────────────────────────────────
    # ANALIZA
    # ──────────────────────────────────────────────

    def _analyse(self):
        entries = self.db.get_all_passwords(self.user)
        self.total = len(entries)
        self.weak = []
        self.duplicates = []
        self.old = []

        password_map = {}  # plaintext → lista wpisów

        for entry in entries:
            try:
                plaintext = self.db.decrypt_password(entry, self.crypto)
            except Exception:
                continue

            # Siła
            strength = check_strength(plaintext)
            if strength["score"] <= 1:
                self.weak.append((entry, strength))

            # Duplikaty
            if plaintext not in password_map:
                password_map[plaintext] = []
            password_map[plaintext].append(entry)

            # Stare (>90 dni)
            if entry.updated_at:
                now = datetime.now()
                updated = entry.updated_at
                # Usuń info o strefie czasowej jeśli jest
                if hasattr(updated, 'tzinfo') and updated.tzinfo:
                    now = datetime.now(timezone.utc)
                days_old = (now - updated).days
                if days_old > 90:
                    self.old.append((entry, days_old))

        # Tylko grupy z duplikatami (2+ wpisów)
        for pwd, ents in password_map.items():
            if len(ents) > 1:
                self.duplicates.append(ents)

        # Wynik ogólny (0-100)
        issues = len(self.weak) + len(self.duplicates) + len(self.old)
        if self.total == 0:
            self.security_score = 100
        else:
            penalty = min(100, issues * 15)
            self.security_score = max(0, 100 - penalty)

    # ──────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────

    def _build_ui(self):
        apply_hex_to_window(self)
        # ── Nagłówek z gradientem ──────────────────────────────────
        _is_dark = ctk.get_appearance_mode() == "Dark"
        _gbg = "#1a1a1a" if _is_dark else "#f5f5f5"
        _gcard = "#1e1e1e" if _is_dark else "#fafafa"

        _hdr_tint = _blend(self._accent, _gcard, 0.18)
        hdr = ctk.CTkFrame(self, fg_color=("gray92", _hdr_tint), corner_radius=0,
                           height=70)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="🛡️  Analiza bezpieczeństwa",
            font=ctk.CTkFont(size=19, weight="bold"),
        ).pack(side="left", padx=20, pady=14)

        ctk.CTkLabel(
            hdr, text=f"Przeanalizowano {self.total} haseł",
            font=ctk.CTkFont(size=12),
            text_color=(self._accent, self._accent),
        ).pack(side="right", padx=20)

        self._grad_hdr_sep = AnimatedGradientCanvas(
            self,
            accent=_blend(self._accent, _gcard, 0.55),
            base=_gbg,
            anim_mode="slide",
            fps=20,
            period_ms=6000,
            n_bands=1,
            direction="h",
            steps=96,
            height=2,
        )
        self._grad_hdr_sep.pack(fill="x")
        self._grad_hdr_sep.start_animation()

        # Wynik ogólny
        self._build_score_card()

        # Przewijana lista problemów
        scroll = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=(8, 0))
        apply_hex_to_scrollable(scroll, hex_size=36, glow_max=2, glow_interval_ms=1800)

        if self.total == 0:
            ctk.CTkLabel(
                scroll, text="Nie masz jeszcze żadnych haseł do analizy.",
                text_color="gray", font=ctk.CTkFont(size=13)
            ).pack(pady=30)
        else:
            self._build_section(scroll, f"⚠️  Słabe hasła ({len(self.weak)})",
                                 self.weak, self._render_weak, "#dd6b20")
            self._build_section(scroll, f"🔄  Zduplikowane hasła ({len(self.duplicates)})",
                                 self.duplicates, self._render_duplicate, "#805ad5")
            self._build_section(scroll, f"🕐  Stare hasła >90 dni ({len(self.old)})",
                                 self.old, self._render_old, "#2b6cb0")

            if not self.weak and not self.duplicates and not self.old:
                ctk.CTkLabel(
                    scroll,
                    text="✅  Wszystkie hasła wyglądają dobrze!\nNie wykryto żadnych problemów.",
                    font=ctk.CTkFont(size=14), text_color="#38a169", justify="center"
                ).pack(pady=30)

        # Przycisk zamknij
        ctk.CTkButton(
            self, text="Zamknij", height=40,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"),
            hover_color=("gray85", "#2a2a2a"),
            text_color=("gray10", "gray90"),
            corner_radius=10,
            command=self._on_close
        ).pack(padx=20, pady=14, fill="x")

    def _on_close(self):
        try:
            self._grad_hdr_sep.stop_animation()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def _build_score_card(self):
        is_dark = ctk.get_appearance_mode() == "Dark"
        card = ctk.CTkFrame(self, corner_radius=16,
                            fg_color=("#ffffff", "#1e1e1e"),
                            border_width=1,
                            border_color=("gray80", "#2e2e2e"))
        card.pack(padx=16, fill="x")

        # Kolor wyniku
        if self.security_score >= 80:
            score_color = "#38a169"
            score_icon = "🟢"
        elif self.security_score >= 50:
            score_color = "#d69e2e"
            score_icon = "🟡"
        else:
            score_color = "#e53e3e"
            score_icon = "🔴"

        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=20, pady=(16, 8))

        ctk.CTkLabel(
            top_row, text=f"{score_icon}  Wynik bezpieczeństwa",
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
        ).pack(side="left")

        ctk.CTkLabel(
            top_row,
            text=f"{self.security_score}/100",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=score_color
        ).pack(side="right")

        # Pasek postępu
        progress = ctk.CTkProgressBar(card, height=10, corner_radius=5,
                                       progress_color=score_color,
                                       fg_color=("gray85", "#2e2e2e"))
        progress.pack(padx=20, fill="x", pady=(0, 16))
        progress.set(self.security_score / 100)

        # Statystyki
        stats = ctk.CTkFrame(card, fg_color=("gray94", "#161616"), corner_radius=10)
        stats.pack(padx=20, fill="x", pady=(0, 16))

        stats_data = [
            ("⚠️", "Słabe", len(self.weak), "#dd6b20"),
            ("🔄", "Duplikaty", len(self.duplicates), "#805ad5"),
            ("🕐", "Stare", len(self.old), "#2b6cb0"),
            ("✅", "Bezpieczne",
             max(0, self.total - len(self.weak) - len(self.duplicates)), "#38a169"),
        ]

        for icon, label, count, color in stats_data:
            col = ctk.CTkFrame(stats, fg_color="transparent")
            col.pack(side="left", fill="x", expand=True, pady=10)

            ctk.CTkLabel(col, text=str(count),
                         font=ctk.CTkFont(size=20, weight="bold"),
                         text_color=color).pack()
            ctk.CTkLabel(col, text=f"{icon} {label}",
                         font=ctk.CTkFont(size=11),
                         text_color="gray").pack()

    def _build_section(self, parent, title, items, render_fn, color):
        if not items:
            return

        # Nagłówek sekcji
        ctk.CTkLabel(
            parent, text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=color, anchor="w"
        ).pack(fill="x", pady=(16, 6))

        for item in items:
            render_fn(parent, item)

    def _render_weak(self, parent, item):
        entry, strength = item
        row = ctk.CTkFrame(parent, corner_radius=10,
                           fg_color=("#fff8f0", "#2a1f10"),
                           border_width=1, border_color=("#f6ad55", "#7a4a10"))
        row.pack(fill="x", pady=3)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=12, pady=8)

        ctk.CTkLabel(left, text=entry.title,
                     font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(fill="x")
        ctk.CTkLabel(left, text=f"Siła: {strength['label']}  •  Entropia: {strength['entropy']} bit",
                     font=ctk.CTkFont(size=11), text_color="gray", anchor="w").pack(fill="x")

        if strength["suggestions"]:
            tip = strength["suggestions"][0]
            ctk.CTkLabel(left, text=f"💡 {tip}",
                         font=ctk.CTkFont(size=11), text_color="#dd6b20", anchor="w").pack(fill="x")

    def _render_duplicate(self, parent, group):
        names = ", ".join(e.title for e in group)
        row = ctk.CTkFrame(parent, corner_radius=10,
                           fg_color=("#f8f0ff", "#1f1030"),
                           border_width=1, border_color=("#b794f4", "#5a3090"))
        row.pack(fill="x", pady=3)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=12, pady=10)

        ctk.CTkLabel(left, text=f"Takie samo hasło w: {names}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#805ad5", anchor="w", wraplength=420).pack(fill="x")
        ctk.CTkLabel(left, text="💡 Użyj unikalnego hasła dla każdego serwisu",
                     font=ctk.CTkFont(size=11), text_color="gray", anchor="w").pack(fill="x")

    def _render_old(self, parent, item):
        entry, days = item
        row = ctk.CTkFrame(parent, corner_radius=10,
                           fg_color=("#f0f4ff", "#101830"),
                           border_width=1, border_color=("#76b0f5", "#1a3a70"))
        row.pack(fill="x", pady=3)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=12, pady=8)

        ctk.CTkLabel(left, text=entry.title,
                     font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(fill="x")
        ctk.CTkLabel(left, text=f"Ostatnia zmiana: {days} dni temu",
                     font=ctk.CTkFont(size=11), text_color="gray", anchor="w").pack(fill="x")
        ctk.CTkLabel(left, text="💡 Rozważ zmianę tego hasła",
                     font=ctk.CTkFont(size=11), text_color="#2b6cb0", anchor="w").pack(fill="x")
