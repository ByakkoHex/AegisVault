"""
update_dialog.py - Dialog informacji o dostępnej aktualizacji
=============================================================
Wyświetla popup z informacją o nowej wersji, changelogiem
i przyciskiem do pobrania.
"""

import customtkinter as ctk
import webbrowser
from gui.gradient import AnimatedGradientCanvas
from gui.animations import slide_fade_in
from gui.hex_background import apply_hex_to_window


ACCENT       = "#4F8EF7"
ACCENT_HOVER = "#3a7ae0"
DARK_CARD    = "#1e1e1e"
DARK_BG      = "#1a1a1a"
LIGHT_CARD   = "#ffffff"
LIGHT_BG     = "#f5f5f5"


class UpdateDialog(ctk.CTkToplevel):
    """Stylizowany dialog informujący o dostępnej aktualizacji."""

    def __init__(self, parent, update_info: dict):
        super().__init__(parent)
        self._info = update_info

        self.title("Dostępna aktualizacja")
        self.geometry("500x460")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus_force()

        # Wyśrodkuj względem rodzica
        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width()  - 500) // 2
        py = parent.winfo_y() + (parent.winfo_height() - 460) // 2
        self.geometry(f"500x460+{px}+{py}")

        self._build()
        self.after(10, lambda: slide_fade_in(self))

    def _build(self):
        apply_hex_to_window(self)
        # Nagłówek
        header = ctk.CTkFrame(self, fg_color=(ACCENT, ACCENT), corner_radius=0, height=72)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="⬆  Dostępna aktualizacja",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#ffffff",
        ).pack(expand=True)

        _sep = AnimatedGradientCanvas(
            self,
            accent=ACCENT,
            base=DARK_CARD,
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

        # Wersje
        ver_frame = ctk.CTkFrame(self, fg_color="transparent")
        ver_frame.pack(fill="x", padx=28, pady=(18, 0))

        ctk.CTkLabel(
            ver_frame,
            text=f"Aktualna wersja:  {self._info['current']}",
            font=ctk.CTkFont(size=12), text_color="gray",
        ).pack(anchor="w")

        ctk.CTkLabel(
            ver_frame,
            text=f"Nowa wersja:  {self._info['version']}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=(ACCENT, ACCENT),
        ).pack(anchor="w", pady=(2, 0))

        # Separator
        ctk.CTkFrame(self, height=1, fg_color=("gray80", "#2e2e2e")).pack(
            fill="x", padx=28, pady=14
        )

        # Changelog
        ctk.CTkLabel(
            self, text="Co nowego:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", padx=28)

        changelog_box = ctk.CTkTextbox(
            self, height=170, corner_radius=10,
            fg_color=("gray95", "#252525"),
            border_width=1, border_color=("gray80", "#333"),
            font=ctk.CTkFont(size=12),
            wrap="word",
        )
        changelog_box.pack(fill="x", padx=28, pady=(6, 0))
        changelog_box.insert("1.0", self._info.get("changelog", "Brak informacji."))
        changelog_box.configure(state="disabled")

        # Przyciski
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=28, pady=18)

        ctk.CTkButton(
            btn_frame, text="Pobierz aktualizację",
            height=44, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            corner_radius=12, font=ctk.CTkFont(size=13, weight="bold"),
            command=self._download,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="Później",
            height=44, fg_color=("gray88", "#2a2a2a"),
            hover_color=("gray80", "#383838"),
            text_color=("gray20", "gray80"),
            corner_radius=12, font=ctk.CTkFont(size=13),
            command=self.destroy,
        ).pack(side="left", padx=(0, 0))

    def _download(self):
        url = self._info.get("download_url", "")
        if url:
            webbrowser.open(url)
        self.destroy()
