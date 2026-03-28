"""
sync_window.py - Okno konfiguracji i statusu synchronizacji
============================================================
"""

import customtkinter as ctk
import threading
from utils.sync_client import SyncClient

from utils.prefs_manager import PrefsManager as _PrefsManager
from gui.gradient import GradientCanvas, AnimatedGradientCanvas
from gui.animations import slide_fade_in
from gui.hex_background import apply_hex_to_window

_ACCENT       = _PrefsManager().get_accent()
_ACCENT_HOVER = _PrefsManager().get_accent_hover()


def _blend_s(accent: str, base: str, alpha: float) -> str:
    def _p(c):
        c = c.lstrip("#"); return int(c[:2],16), int(c[2:4],16), int(c[4:],16)
    ar,ag,ab = _p(accent); br,bg_,bb = _p(base)
    return f"#{int(br+(ar-br)*alpha):02x}{int(bg_+(ag-bg_)*alpha):02x}{int(bb+(ab-bb)*alpha):02x}"


def _gbg_sync() -> str:
    import customtkinter as _c
    return "#1a1a1a" if _c.get_appearance_mode() == "Dark" else "#f5f5f5"

def _gcard_sync() -> str:
    import customtkinter as _c
    return "#1e1e1e" if _c.get_appearance_mode() == "Dark" else "#fafafa"


class SyncWindow(ctk.CTkToplevel):
    def __init__(self, parent, db, crypto, user, sync_client: SyncClient, on_refresh=None):
        super().__init__(parent)
        self.db = db
        self.crypto = crypto
        self.user = user
        self.sync = sync_client
        self.on_refresh = on_refresh

        self.title("Synchronizacja")
        self.geometry("460x700")
        self.resizable(False, False)
        self.grab_set()
        self.focus()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._check_status()
        self.after(10, lambda: slide_fade_in(self))

    def _build_ui(self):
        apply_hex_to_window(self)
        _accent = _PrefsManager().get_accent()
        _hdr_tint = _blend_s(_accent, _gcard_sync(), 0.18)

        # ── Nagłówek z gradientem ─────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=("gray92", _hdr_tint),
                           corner_radius=0, height=62)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="🔄  Synchronizacja",
            font=ctk.CTkFont(size=19, weight="bold"),
        ).pack(side="left", padx=20, pady=14)

        self._grad_hdr_sep = AnimatedGradientCanvas(
            self,
            accent=_blend_s(_accent, _gcard_sync(), 0.55),
            base=_gbg_sync(),
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

        ctk.CTkLabel(
            self,
            text="Synchronizuj hasła między urządzeniami przez lokalny serwer.",
            font=ctk.CTkFont(size=12), text_color="gray", justify="center"
        ).pack(pady=(12, 8))

        # ── Status serwera ──
        status_frame = ctk.CTkFrame(self, corner_radius=12,
                                    fg_color=("gray92", "#1e1e1e"))
        status_frame.pack(padx=20, fill="x")

        status_row = ctk.CTkFrame(status_frame, fg_color="transparent")
        status_row.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(status_row, text="Status serwera:",
                     font=ctk.CTkFont(size=13), anchor="w").pack(side="left")

        self.status_label = ctk.CTkLabel(
            status_row, text="⏳ Sprawdzanie...",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="gray"
        )
        self.status_label.pack(side="right")

        ctk.CTkLabel(status_frame,
                     text=f"Adres: {self.sync.server_url}",
                     font=ctk.CTkFont(size=11), text_color="gray").pack(
            padx=16, pady=(0, 12), anchor="w"
        )

        ctk.CTkLabel(self, text="", height=8).pack()

        # ── Logowanie do serwera ──
        login_frame = ctk.CTkFrame(self, corner_radius=12,
                                   fg_color=("gray92", "#1e1e1e"))
        login_frame.pack(padx=20, fill="x")

        ctk.CTkLabel(login_frame, text="🔐 Konto synchronizacji",
                     font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(
            padx=16, pady=(14, 4), fill="x"
        )
        ctk.CTkLabel(login_frame,
                     text="Osobne konto na serwerze sync (może być takie samo jak lokalne).",
                     font=ctk.CTkFont(size=11), text_color="gray", anchor="w").pack(
            padx=16, pady=(0, 10), fill="x"
        )

        ctk.CTkLabel(login_frame, text="Login", anchor="w",
                     font=ctk.CTkFont(size=12)).pack(padx=16, pady=(0, 2), fill="x")
        self.entry_user = ctk.CTkEntry(
            login_frame, placeholder_text="Nazwa użytkownika...",
            height=38, corner_radius=10
        )
        self.entry_user.pack(padx=16, fill="x")
        self.entry_user.insert(0, self.user.username)

        ctk.CTkLabel(login_frame, text="Hasło do serwera", anchor="w",
                     font=ctk.CTkFont(size=12)).pack(padx=16, pady=(8, 2), fill="x")
        self.entry_pass = ctk.CTkEntry(
            login_frame, placeholder_text="Hasło...",
            show="•", height=38, corner_radius=10
        )
        self.entry_pass.pack(padx=16, fill="x")

        btn_row = ctk.CTkFrame(login_frame, fg_color="transparent")
        btn_row.pack(padx=16, pady=(10, 14), fill="x")

        ctk.CTkButton(
            btn_row, text="Zarejestruj na serwerze", height=36,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"),
            hover_color=("gray85", "#2a2a2a"),
            text_color=("gray20", "gray80"),
            corner_radius=10, font=ctk.CTkFont(size=12),
            command=self._register_account
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))

        ctk.CTkButton(
            btn_row, text="Zaloguj", height=36,
            fg_color=_accent, hover_color=_PrefsManager().get_accent_hover(),
            corner_radius=10, font=ctk.CTkFont(size=12, weight="bold"),
            command=self._login
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

        self.auth_label = ctk.CTkLabel(
            login_frame, text="",
            font=ctk.CTkFont(size=11)
        )
        self.auth_label.pack(padx=16, pady=(0, 8))

        ctk.CTkLabel(self, text="", height=8).pack()

        # ── Przyciski sync ──
        sync_frame = ctk.CTkFrame(self, corner_radius=12,
                                  fg_color=("gray92", "#1e1e1e"))
        sync_frame.pack(padx=20, fill="x")

        ctk.CTkLabel(sync_frame, text="🔄 Synchronizacja danych",
                     font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(
            padx=16, pady=(14, 10), fill="x"
        )

        sync_btn_row = ctk.CTkFrame(sync_frame, fg_color="transparent")
        sync_btn_row.pack(padx=16, pady=(0, 14), fill="x")

        ctk.CTkButton(
            sync_btn_row, text="📤 Wyślij na serwer", height=40,
            fg_color=("#ddeeff", "#1a3a5c"),
            hover_color=("#cce0ff", "#1e4a70"),
            text_color=(_accent, "#7ab8f5"),
            corner_radius=10, font=ctk.CTkFont(size=12, weight="bold"),
            command=self._push
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))

        ctk.CTkButton(
            sync_btn_row, text="📥 Pobierz z serwera", height=40,
            fg_color=("#ddeeff", "#1a3a5c"),
            hover_color=("#cce0ff", "#1e4a70"),
            text_color=(_accent, "#7ab8f5"),
            corner_radius=10, font=ctk.CTkFont(size=12, weight="bold"),
            command=self._pull
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

        self.sync_status_label = ctk.CTkLabel(
            sync_frame, text="",
            font=ctk.CTkFont(size=11), text_color="gray"
        )
        self.sync_status_label.pack(padx=16, pady=(0, 10))

        ctk.CTkLabel(self, text="", height=8).pack()

        ctk.CTkButton(
            self, text="Zamknij", height=40,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"),
            hover_color=("gray85", "#2a2a2a"),
            text_color=("gray20", "gray80"),
            corner_radius=10, command=self._on_close
        ).pack(padx=20, fill="x", pady=(0, 20))

    def _on_close(self):
        try:
            self._grad_hdr_sep.stop_animation()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def _check_status(self):
        def check():
            connected = self.sync.is_connected()
            self.after(0, lambda: self.status_label.configure(
                text="🟢 Połączony" if connected else "🔴 Niedostępny",
                text_color="#38a169" if connected else "#e53e3e"
            ))
        threading.Thread(target=check, daemon=True).start()

    def _register_account(self):
        username = self.entry_user.get().strip()
        password = self.entry_pass.get()
        if not username or not password:
            self.auth_label.configure(text="Wypełnij oba pola!", text_color="#e53e3e")
            return
        try:
            self.sync.register(username, password)
            self.auth_label.configure(text="✅ Konto utworzone! Możesz się zalogować.",
                                      text_color="#38a169")
        except Exception as e:
            self.auth_label.configure(text=f"❌ {str(e)}", text_color="#e53e3e")

    def _login(self):
        username = self.entry_user.get().strip()
        password = self.entry_pass.get()
        if not username or not password:
            self.auth_label.configure(text="Wypełnij oba pola!", text_color="#e53e3e")
            return
        try:
            success = self.sync.login(username, password)
            if success:
                self.auth_label.configure(
                    text=f"✅ Zalogowano jako {username}",
                    text_color="#38a169"
                )
            else:
                self.auth_label.configure(text="❌ Błędne dane logowania",
                                          text_color="#e53e3e")
        except Exception as e:
            self.auth_label.configure(text=f"❌ Brak połączenia z serwerem",
                                      text_color="#e53e3e")

    def _push(self):
        if not self.sync.token:
            self.sync_status_label.configure(
                text="⚠️ Najpierw zaloguj się do serwera!", text_color="#dd6b20"
            )
            return

        self.sync_status_label.configure(text="⏳ Wysyłanie...", text_color="gray")

        def do_push():
            import time
            t = time.time()
            try:
                result = self.sync.push(self.db, self.crypto, self.user)
                print(f"Sync Push: {(time.time() - t) * 1000:.1f}ms")
                print(f"Odpowiedź serwera: {result}")
                msg = f"✅ Wysłano: {result.get('created', 0)} nowych, zaktualizowano: {result.get('updated', 0)}"
                self.after(0, lambda: self.sync_status_label.configure(
                    text=msg, text_color="#38a169"
                ))
            except Exception as e:
                import traceback
                traceback.print_exc()  # ← pokaże pełny błąd w konsoli
                self.after(0, lambda err=e: self.sync_status_label.configure(
                    text=f"❌ Błąd: {err}", text_color="#e53e3e"
                ))

        threading.Thread(target=do_push, daemon=True).start()

    def _pull(self):
        if not self.sync.token:
            self.sync_status_label.configure(
                text="⚠️ Najpierw zaloguj się do serwera!", text_color="#dd6b20"
            )
            return

        self.sync_status_label.configure(text="⏳ Pobieranie...", text_color="gray")

        def do_pull():
            import time
            t = time.time()
            try:
                result = self.sync.pull(self.db, self.crypto, self.user)
                print(f"Sync Pull: {(time.time() - t) * 1000:.1f}ms")
                msg = (f"✅ Zaimportowano: {result['imported']} nowych, "
                       f"pominięto: {result['skipped']}")
                self.after(0, lambda: self.sync_status_label.configure(
                    text=msg, text_color="#38a169"
                ))
                if self.on_refresh:
                    self.after(0, self.on_refresh)
            except Exception as e:                          # ← except na tym samym poziomie co try
                self.after(0, lambda err=e: self.sync_status_label.configure(
                    text=f"❌ Błąd: {err}", text_color="#e53e3e"
                ))

        threading.Thread(target=do_pull, daemon=True).start()
