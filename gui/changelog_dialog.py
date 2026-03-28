"""
changelog_dialog.py - Dialog "Co nowego" po aktualizacji AegisVault
====================================================================
Pokazywany raz po uruchomieniu aplikacji w nowej wersji.
"""

import customtkinter as ctk

ACCENT       = "#4F8EF7"
ACCENT_HOVER = "#3a7ae0"
GREEN        = "#4caf50"
DARK_CARD    = "#1e1e1e"
LIGHT_CARD   = "#ffffff"


class ChangelogDialog(ctk.CTkToplevel):
    """Dialog 'Co nowego w wersji X.Y.Z' pokazywany po pierwszym uruchomieniu po aktualizacji."""

    def __init__(self, parent, version: str, changelog: str, accent: str = ACCENT):
        super().__init__(parent)
        self._version   = version
        self._changelog = changelog
        self._accent    = accent

        self.title("")
        self.geometry("500x460")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus_force()

        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width()  - 500) // 2
        py = parent.winfo_y() + (parent.winfo_height() - 460) // 2
        self.geometry(f"500x460+{px}+{py}")

        self._build()

    def _build(self):
        # ── Nagłówek ──────────────────────────────────────────────
        header = ctk.CTkFrame(
            self, fg_color=(self._accent, self._accent),
            corner_radius=0, height=70,
        )
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="🚀  Co nowego?",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#ffffff",
        ).pack(side="left", padx=20)

        ctk.CTkLabel(
            header,
            text=f"v{self._version}",
            font=ctk.CTkFont(size=13),
            text_color="#ffffffaa",
        ).pack(side="right", padx=20)

        # ── Treść ─────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        ctk.CTkLabel(
            body,
            text=f"AegisVault został zaktualizowany do wersji {self._version}.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(anchor="w", pady=(0, 12))

        changelog_box = ctk.CTkTextbox(
            body,
            corner_radius=10,
            fg_color=("gray95", "#252525"),
            border_width=1, border_color=("gray80", "#333"),
            font=ctk.CTkFont(size=12, family="Consolas"),
            wrap="word",
        )
        changelog_box.pack(fill="both", expand=True)
        changelog_box.insert("1.0", self._changelog.strip())
        changelog_box.configure(state="disabled")

        # ── Przycisk ──────────────────────────────────────────────
        ctk.CTkButton(
            body,
            text="✓  Super, dzięki!",
            height=42,
            fg_color=(self._accent, self._accent),
            hover_color=(ACCENT_HOVER, ACCENT_HOVER),
            text_color="#ffffff",
            corner_radius=12,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.destroy,
        ).pack(fill="x", pady=(14, 0))
