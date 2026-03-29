"""
login_window.py - Okno logowania / rejestracji (redesign)
"""

import customtkinter as ctk
import tkinter as tk
import threading
import qrcode
from PIL import Image
from gui.dialogs import show_error, show_info, show_success
from database.db_manager import DatabaseManager
from core.crypto import CryptoManager
from core.totp import TOTPManager
from utils.password_strength import check_strength
from utils.push_auth import PushAuthClient
from utils.prefs_manager import PrefsManager
import utils.windows_hello as wh
from gui.animations import shake, pulse_label
from gui.gradient import GradientCanvas, AnimatedGradientCanvas
from gui.hex_background import HexBackground, apply_hex_to_scrollable, apply_hex_to_window
from utils.logger import get_logger

logger = get_logger(__name__)

_prefs = PrefsManager()

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT       = _prefs.get_accent()
ACCENT_HOVER = _prefs.get_accent_hover()


class LoginWindow(ctk.CTk):
    def __init__(self, db_path: str = "aegisvault.db"):
        super().__init__()
        self._accent       = _prefs.get_accent()
        self._accent_hover = _prefs.get_accent_hover()

        self.title("AegisVault — Logowanie")
        self.geometry("460x600")
        self.resizable(False, False)

        self.db = DatabaseManager(db_path)
        self.logged_user = None
        self.crypto = None
        self._temp_password = None
        self._pending_user = None
        self._current_view = "login"
        self._push_poll_id = None
        self._push_token   = None
        self._push_client  = PushAuthClient()
        self._wh_available = False   # uzupełniane asynchronicznie
        self._wh_btn       = None    # referencja do przycisku WH

        logger.info(f"=== LoginWindow uruchomiony | db={db_path} ===")
        self._build_ui()
        # Sprawdź WH w tle — nie blokuj startu UI
        threading.Thread(target=self._check_wh_availability, daemon=True).start()

    def destroy(self):
        try:
            self._accent_bar.stop_animation()
        except Exception:
            pass
        # Anuluj wszystkie zaplanowane after() tego okna (CTk wewnętrzne + nasze)
        # — zapobiega błędom "invalid command name" po zniszczeniu widgetu.
        try:
            for after_id in self.tk.eval("after info").split():
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
        except Exception:
            pass
        super().destroy()

    def _make_logo_image(self, accent: str, size: int = 64) -> ctk.CTkImage:
        """Ładuje icon.png i rekoloruje nieprzezroczyste piksele na kolor akcentu."""
        import os as _os
        _icon_path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "assets", "icon.png")
        try:
            img = Image.open(_icon_path).convert("RGBA").resize((size, size), Image.LANCZOS)
            r = int(accent[1:3], 16)
            g = int(accent[3:5], 16)
            b = int(accent[5:7], 16)
            pixels = img.load()
            for y in range(img.height):
                for x in range(img.width):
                    _, _, _, a = pixels[x, y]
                    if a > 10:
                        pixels[x, y] = (r, g, b, a)
            return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
        except Exception:
            return None

    def _build_ui(self):
        # Lewy gradient — od koloru akcentu do tła okna (adaptive dark/light)
        _login_bg = "#212121" if ctk.get_appearance_mode() == "Dark" else "#f0f0f0"
        self._accent_bar = AnimatedGradientCanvas(
            self,
            accent=self._accent,
            base=_login_bg,
            anim_mode="slide",
            fps=15,
            period_ms=8000,
            n_bands=1,
            direction="v",
            width=10,
        )
        self._accent_bar.pack(side="left", fill="y")
        self._accent_bar.start_animation()

        # Główna zawartość
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(side="left", fill="both", expand=True, padx=30, pady=30)

        # Hexagonalne tło całego okna — widoczne w obszarze ikony/tytułu
        apply_hex_to_window(self, hex_size=32, glow_max=3, glow_interval_ms=1600)

        # Logo i tytuł — ładuje icon.png z assets/, rekoloruje na kolor akcentu
        import os as _os
        _icon_path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "assets", "icon.png")
        _has_logo = _os.path.exists(_icon_path)
        if _has_logo:
            _ctk_img = self._make_logo_image(self._accent, size=64)
            self.label_icon = ctk.CTkLabel(self.main_frame, image=_ctk_img, text="")
        else:
            self.label_icon = ctk.CTkLabel(
                self.main_frame, text="🔐", font=ctk.CTkFont(size=48)
            )
        self.label_icon.pack(pady=(10, 0))
        # Pulse działa tylko dla trybu tekstowego (font size animation)
        if not _has_logo:
            self.after(200, lambda: pulse_label(self.label_icon, sizes=[48, 52, 56, 53, 49, 47, 48]))

        self.label_title = ctk.CTkLabel(
            self.main_frame, text="AegisVault",
            font=ctk.CTkFont(size=26, weight="bold")
        )
        self.label_title.pack(pady=(4, 2))

        self.label_subtitle = ctk.CTkLabel(
            self.main_frame, text="Zaloguj się do swojego sejfu",
            font=ctk.CTkFont(size=13),
            text_color="gray"
        )
        self.label_subtitle.pack(pady=(0, 25))

        # Ramka formularza
        self.form_frame = ctk.CTkFrame(self.main_frame, corner_radius=16, fg_color=("gray90", "#1e1e1e"))
        self.form_frame.pack(fill="both", expand=True)
        self._add_form_hex()

        self._show_login_view()

    def _add_form_hex(self):
        """Dodaje hex do form_frame — wywoływane po każdym _clear_form."""
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg = "#1e1e1e" if is_dark else "#f0f0f0"
        _h = HexBackground(self.form_frame, hex_size=32, animate=True,
                           glow_max=2, glow_interval_ms=1600, bg_color=bg)
        _h.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        try:
            self.form_frame.tk.call("lower", _h._w)
        except Exception:
            pass

    def _clear_form(self):
        for w in self.form_frame.winfo_children():
            w.destroy()
        self._add_form_hex()

    # ── LOGOWANIE ──

    def _stop_push_poll(self):
        if self._push_poll_id is not None:
            try:
                self.after_cancel(self._push_poll_id)
            except Exception:
                pass
            self._push_poll_id = None
        self._push_token = None

    def _show_login_view(self):
        logger.info(">>> Ekran logowania wyświetlony")
        self._stop_push_poll()
        self._current_view = "login"
        self._clear_form()
        self.label_subtitle.configure(text="Zaloguj się do swojego sejfu")

        self._field(self.form_frame, "Nazwa użytkownika", "Wpisz login...", False, "entry_username")
        self._field(self.form_frame, "Hasło masterowe", "Wpisz hasło...", True, "entry_password")
        self.entry_password.bind("<Return>", lambda e: self._on_login())

        last = _prefs.get("last_username")
        if last:
            self.entry_username.insert(0, last)
            self.after(100, self.entry_password.focus_set)
        else:
            self.after(100, self.entry_username.focus_set)

        self._btn(self.form_frame, "Zaloguj się", self._on_login, primary=True, top_pad=20)

        # Przycisk Windows Hello — widoczny gdy WH jest dostępne
        self._wh_btn = ctk.CTkButton(
            self.form_frame,
            text="🪟  Windows Hello",
            height=44,
            fg_color=("gray85", "#252525"),
            hover_color=("gray78", "#2e2e2e"),
            text_color=("gray20", "gray80"),
            border_width=1,
            border_color=("gray70", "gray40"),
            corner_radius=10,
            font=ctk.CTkFont(size=13),
            command=self._on_windows_hello,
            state="disabled"
        )
        self._wh_btn.pack(padx=20, pady=(4, 4), fill="x")

        # Pokaż/ukryj przycisk WH zależnie od stanu asynchronicznego sprawdzenia
        if self._wh_available:
            self._wh_btn.configure(state="normal")

        self._divider(self.form_frame)
        self._btn(self.form_frame, "Utwórz nowe konto", self._show_register_view, primary=False)

    def _check_wh_availability(self):
        """Sprawdza dostępność WH w tle i aktualizuje przycisk."""
        available = wh.is_available()
        self._wh_available = available
        if available and self._wh_btn and self._current_view == "login":
            try:
                self.after(0, lambda: self._wh_btn.configure(state="normal"))
            except Exception:
                pass

    def _on_windows_hello(self):
        username = self.entry_username.get().strip()
        if not username:
            show_error("Windows Hello", "Wpisz najpierw nazwę użytkownika.", parent=self)
            return

        user = self.db.get_user(username)
        if not user:
            show_error("Windows Hello", f"Nie znaleziono użytkownika '{username}'.", parent=self)
            return

        if not wh.has_credential(username):
            show_error(
                "Windows Hello",
                "Windows Hello nie jest skonfigurowane dla tego konta.\n\n"
                "Zaloguj się hasłem, a następnie włącz je w:\nUstawienia → Windows Hello.",
                parent=self
            )
            return

        # Blokuj przycisk, cofnij okno w Z-order, uruchom weryfikację w tle
        self._wh_btn.configure(state="disabled", text="⏳  Weryfikacja…")
        # Oderwij focus od pól tekstowych — PIN z WH nie może trafiać do entry_password.
        self._wh_btn.focus_set()
        self.lower()  # opuść okno poniżej dialogu WH żeby był widoczny
        threading.Thread(
            target=self._wh_verify_and_login,
            args=(user,),
            daemon=True
        ).start()

    def _wh_verify_and_login(self, user):
        verified = wh.verify("Zaloguj się do AegisVault")
        # Przywróć okno na wierzch po zamknięciu dialogu WH
        self.after(0, self.lift)
        self.after(0, self.focus_force)
        if not verified:
            self.after(0, self._wh_reset_btn)
            self.after(0, lambda: show_error(
                "Windows Hello",
                "Weryfikacja anulowana lub nieudana.",
                parent=self
            ))
            return

        master_password = wh.get_credential(user.username)
        if not master_password:
            self.after(0, self._wh_reset_btn)
            self.after(0, lambda: show_error(
                "Windows Hello",
                "Nie można odczytać poświadczeń. Spróbuj zalogować się hasłem.",
                parent=self
            ))
            return

        # Weryfikuj hasło w bazie (spójność)
        verified_user = self.db.login_user(user.username, master_password)
        if not verified_user:
            self.after(0, self._wh_reset_btn)
            self.after(0, lambda: show_error(
                "Windows Hello",
                "Zapisane poświadczenia są nieaktualne.\nWyłącz i ponownie włącz Windows Hello w Ustawieniach.",
                parent=self
            ))
            return

        # Windows Hello zastępuje 2FA — loguj bezpośrednio
        self.after(0, lambda: self._complete_login(verified_user, master_password))

    def _wh_reset_btn(self):
        if self._wh_btn:
            try:
                self._wh_btn.configure(state="normal", text="🪟  Windows Hello")
            except Exception:
                pass

    # ── REJESTRACJA ──

    def _show_register_view(self):
        logger.info(">>> Ekran rejestracji wyświetlony")
        self._stop_push_poll()
        self._current_view = "register"
        self._clear_form()
        self.label_subtitle.configure(text="Utwórz nowe konto")

        # Scrollowany kontener zamiast zwykłej ramki
        scroll = ctk.CTkScrollableFrame(self.form_frame, corner_radius=0, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        apply_hex_to_scrollable(scroll, hex_size=32, glow_max=2, glow_interval_ms=1600)

        self._field(scroll, "Nazwa użytkownika", "Wymyśl login...", False, "entry_username")
        self._field(scroll, "Hasło masterowe", "Min. 8 znaków...", True, "entry_password")
        self.after(100, self.entry_username.focus_set)

        # Pasek siły hasła
        self.reg_strength_bar = ctk.CTkProgressBar(
            scroll, height=6, corner_radius=3
        )
        self.reg_strength_bar.pack(padx=20, pady=(6, 0), fill="x")
        self.reg_strength_bar.set(0)

        self.reg_strength_label = ctk.CTkLabel(
            scroll, text="",
            font=ctk.CTkFont(size=11), anchor="w"
        )
        self.reg_strength_label.pack(padx=20, fill="x")

        # Checklist wymagań
        from utils.password_strength import _build_checklist
        checklist_frame = ctk.CTkFrame(
            scroll, fg_color=("gray88", "#252525"), corner_radius=8
        )
        checklist_frame.pack(padx=20, pady=(4, 0), fill="x")

        self._reg_checklist_rows = []
        for item in _build_checklist(""):
            lbl = ctk.CTkLabel(
                checklist_frame,
                text=f"❌  {item['text']}",
                font=ctk.CTkFont(size=11),
                text_color="gray50",
                anchor="w"
            )
            lbl.pack(padx=10, pady=1, fill="x")
            self._reg_checklist_rows.append(lbl)

        self._field(scroll, "Powtórz hasło", "Powtórz hasło...", True, "entry_password2")

        # Etykieta zgodności haseł
        self.reg_match_label = ctk.CTkLabel(
            scroll, text="",
            font=ctk.CTkFont(size=11), anchor="w"
        )
        self.reg_match_label.pack(padx=20, fill="x")

        # Bindingi na żywo
        self.entry_password.bind("<KeyRelease>", lambda e: self._on_reg_password_change())
        self.entry_password2.bind("<KeyRelease>", lambda e: self._on_reg_match_change())
        self.entry_password2.bind("<Return>", lambda e: self._on_register())

        self._btn(scroll, "Zarejestruj się", self._on_register, primary=True, top_pad=12)
        self._btn(scroll, "← Mam już konto", self._show_login_view, primary=False)

    def _on_reg_password_change(self):
        pwd = self.entry_password.get()
        result = check_strength(pwd)
        self.reg_strength_bar.set(result["percent"] / 100)
        self.reg_strength_bar.configure(progress_color=result["color"])
        if result["label"]:
            self.reg_strength_label.configure(
                text=f"{result['label']}   •   Entropia: {result['entropy']} bit",
                text_color=result["color"]
            )
        else:
            self.reg_strength_label.configure(text="")

        # Aktualizuj checklistę
        for item, row in zip(result["checklist"], self._reg_checklist_rows):
            icon  = "✅" if item["met"] else "❌"
            color = "#38a169" if item["met"] else ("gray50" if not pwd else "#e53e3e")
            row.configure(text=f"{icon}  {item['text']}", text_color=color)

        self._on_reg_match_change()

    def _on_reg_match_change(self):
        pwd = self.entry_password.get()
        pwd2 = self.entry_password2.get()
        if not pwd2:
            self.reg_match_label.configure(text="")
            return
        if pwd == pwd2:
            self.reg_match_label.configure(text="✅ Hasła są zgodne", text_color="#38a169")
        else:
            self.reg_match_label.configure(text="❌ Hasła nie są takie same", text_color="#e53e3e")

    # ── 2FA weryfikacja ──

    def _show_2fa_view(self, user):
        self._stop_push_poll()
        self._current_view = "2fa"
        self._pending_user = user
        self._clear_form()
        self.label_subtitle.configure(text="Weryfikacja dwuetapowa")

        # Przełącznik trybu
        self._2fa_mode_var = ctk.StringVar(value="totp")
        seg = ctk.CTkSegmentedButton(
            self.form_frame,
            values=["Kod TOTP", "Push Approve"],
            variable=self._2fa_mode_var,
            font=ctk.CTkFont(size=12),
            command=lambda m: self._switch_2fa_mode(m, user),
        )
        seg.pack(padx=20, pady=(16, 8), fill="x")

        # Kontener na dynamiczną zawartość
        self._2fa_content = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        self._2fa_content.pack(fill="both", expand=True)

        self._show_totp_content(user)
        self._btn(self.form_frame, "← Wróć", self._show_login_view, primary=False)

    def _switch_2fa_mode(self, mode: str, user):
        self._stop_push_poll()
        for w in self._2fa_content.winfo_children():
            w.destroy()
        if mode == "Kod TOTP":
            self._show_totp_content(user)
        else:
            self._show_push_content(user)

    # ── TOTP ──

    def _show_totp_content(self, user):
        frame = self._2fa_content

        ctk.CTkLabel(
            frame,
            text="Otwórz Google Authenticator\nlub Microsoft Authenticator\ni wpisz 6-cyfrowy kod:",
            font=ctk.CTkFont(size=12), justify="center", text_color="gray"
        ).pack(pady=(12, 8))

        self.entry_totp = ctk.CTkEntry(
            frame, placeholder_text="000000",
            height=52, font=ctk.CTkFont(size=26), justify="center"
        )
        self.entry_totp.pack(padx=20, fill="x")
        self.entry_totp.bind("<Return>", lambda e: self._on_verify_2fa())
        self.entry_totp.focus()

        self._btn(frame, "Weryfikuj", self._on_verify_2fa, primary=True, top_pad=14)

    # ── Push Approve ──

    def _show_push_content(self, user):
        frame = self._2fa_content

        self._push_status_label = ctk.CTkLabel(
            frame,
            text="⏳ Łączenie z serwerem...",
            font=ctk.CTkFont(size=12), text_color="gray", justify="center"
        )
        self._push_status_label.pack(pady=(14, 6))

        self._push_qr_label = ctk.CTkLabel(frame, text="")
        self._push_qr_label.pack()

        self._push_url_label = ctk.CTkLabel(
            frame, text="",
            font=ctk.CTkFont(size=10), text_color="gray",
            wraplength=360, justify="center"
        )
        self._push_url_label.pack(pady=(4, 0))

        # Start w wątku żeby nie blokować UI
        threading.Thread(
            target=self._start_push_auth,
            args=(user,),
            daemon=True
        ).start()

    def _start_push_auth(self, user):
        """Wywołany w wątku — tworzy wyzwanie i uruchamia polling."""
        if not self._push_client.is_available():
            self.after(0, lambda: self._push_status_label.configure(
                text="❌ Serwer sync niedostępny.\nUruchom go poleceniem: start_server.bat",
                text_color="#e05252"
            ))
            return

        try:
            data  = self._push_client.create_challenge(user.username)
            token = data["token"]
            url   = self._push_client.get_approve_url(token)
            self._push_token = token
        except Exception as e:
            self.after(0, lambda: self._push_status_label.configure(
                text=f"❌ Błąd: {e}", text_color="#e05252"
            ))
            return

        # Generuj QR kod
        qr_img = qrcode.make(url).resize((160, 160), Image.LANCZOS)
        qr_ctk = ctk.CTkImage(light_image=qr_img, dark_image=qr_img, size=(160, 160))

        def _update_ui():
            self._push_qr_label.configure(image=qr_ctk, text="")
            self._push_qr_label.image = qr_ctk  # zapobieg GC
            self._push_url_label.configure(text=url)
            self._push_status_label.configure(
                text="Zeskanuj QR lub otwórz link na telefonie,\nnastępnie zatwierdź logowanie.",
                text_color="gray"
            )
            self._poll_push_status(user)

        self.after(0, _update_ui)

    def _poll_push_status(self, user):
        """Odpytuje serwer co 2s — wywoływane z wątku głównego przez after()."""
        if self._push_token is None:
            return

        status = self._push_client.poll_status(self._push_token)

        if status == "approved":
            self._push_status_label.configure(
                text="✅ Zatwierdzono! Logowanie...", text_color="#4caf50"
            )
            self._stop_push_poll()
            self.after(400, lambda: self._complete_login(user, self._temp_password))

        elif status == "denied":
            self._push_status_label.configure(
                text="❌ Logowanie odrzucone na telefonie.", text_color="#e05252"
            )
            self._stop_push_poll()

        elif status in ("expired", "error"):
            self._push_status_label.configure(
                text="⏰ Żądanie wygasło. Przełącz tryb, aby spróbować ponownie.",
                text_color="#f0a500"
            )
            self._stop_push_poll()

        else:
            # pending — sprawdź ponownie za 2 sekundy
            self._push_poll_id = self.after(2000, lambda: self._poll_push_status(user))

    # ── 2FA setup ──

    def _show_setup_2fa_view(self, user, totp_manager):
        logger.info(f"Wyświetlanie kodu QR setup 2FA: użytkownik={user.username}")
        self._current_view = "setup_2fa"
        self._clear_form()
        self.label_subtitle.configure(text="Skonfiguruj 2FA")

        ctk.CTkLabel(
            self.form_frame,
            text="Zeskanuj kod QR w Google Authenticator:",
            font=ctk.CTkFont(size=12), justify="center"
        ).pack(pady=(15, 8))

        qr_img = totp_manager.get_qr_image(user.username)
        qr_img = qr_img.resize((180, 180), Image.NEAREST)
        logger.debug(f"QR resize do (180,180) NEAREST: rozmiar po resize={qr_img.size}, tryb={qr_img.mode}")
        qr_ctk = ctk.CTkImage(light_image=qr_img, dark_image=qr_img, size=(180, 180))
        ctk.CTkLabel(self.form_frame, image=qr_ctk, text="").pack()

        ctk.CTkLabel(
            self.form_frame,
            text="Następnie wpisz kod aby potwierdzić:",
            font=ctk.CTkFont(size=12), text_color="gray"
        ).pack(pady=(10, 4))

        self.entry_totp_setup = ctk.CTkEntry(
            self.form_frame, placeholder_text="000000",
            height=45, font=ctk.CTkFont(size=20), justify="center"
        )
        self.entry_totp_setup.pack(padx=20, fill="x")
        self.entry_totp_setup.bind("<Return>", lambda e: self._on_confirm_2fa_setup(user, totp_manager))

        self._btn(self.form_frame, "Potwierdź i zaloguj się", lambda: self._on_confirm_2fa_setup(user, totp_manager), primary=True, top_pad=12)

    # ── HELPERS UI ──

    def _field(self, parent, label, placeholder, secret, attr):
        ctk.CTkLabel(parent, text=label, anchor="w", font=ctk.CTkFont(size=12)).pack(
            padx=20, pady=(14, 2), fill="x"
        )
        entry = ctk.CTkEntry(
            parent, placeholder_text=placeholder,
            show="•" if secret else "", height=42,
            corner_radius=10
        )
        entry.pack(padx=20, fill="x")
        setattr(self, attr, entry)

    def _btn(self, parent, text, command, primary=True, top_pad=8):
        if primary:
            ctk.CTkButton(
                parent, text=text, height=44,
                fg_color=self._accent, hover_color=self._accent_hover,
                corner_radius=10,
                font=ctk.CTkFont(size=14, weight="bold"),
                command=command
            ).pack(padx=20, pady=(top_pad, 4), fill="x")
        else:
            ctk.CTkButton(
                parent, text=text, height=44,
                fg_color="transparent", border_width=1,
                border_color=("gray70", "gray40"),
                hover_color=("gray85", "#2a2a2a"),
                text_color=("gray20", "gray80"),
                corner_radius=10,
                font=ctk.CTkFont(size=13),
                command=command
            ).pack(padx=20, pady=(4, 14), fill="x")

    def _divider(self, parent):
        ctk.CTkLabel(
            parent, text="─────── lub ───────",
            text_color="gray", font=ctk.CTkFont(size=11)
        ).pack(pady=2)

    # ── LOGIKA ──

    def _on_login(self):
        username = self.entry_username.get().strip()
        password = self.entry_password.get()
        logger.info(f"Próba logowania: użytkownik={username!r}, hasło={'[puste]' if not password else '[podane]'}")
        if not username or not password:
            logger.warning("Logowanie przerwane — puste pola")
            show_error("Błąd", "Wypełnij wszystkie pola!", parent=self)
            return
        user = self.db.login_user(username, password)
        if not user:
            logger.warning(f"Logowanie nieudane — błędne dane dla: {username!r}")
            shake(self)
            show_error("Błąd logowania", "Nieprawidłowa nazwa użytkownika lub hasło.", parent=self)
            return
        logger.info(f"Hasło poprawne: użytkownik={username!r}, ma_2FA={bool(user.totp_secret)}")
        if user.totp_secret:
            self._temp_password = password
            self._show_2fa_view(user)
        else:
            self._complete_login(user, password)

    def _on_verify_2fa(self):
        code = self.entry_totp.get().strip()
        user = self._pending_user
        logger.info(f"Próba weryfikacji 2FA logowania: użytkownik={user.username!r}, kod={code!r} (długość={len(code)})")
        totp = TOTPManager(secret=user.totp_secret)
        if not totp.verify(code):
            logger.warning(f"Błędny kod 2FA: użytkownik={user.username!r}, wpisany kod={code!r}")
            shake(self)
            show_error(
                "Błąd 2FA",
                "Nieprawidłowy kod!\n\n"
                "Jeśli kod w aplikacji wygląda poprawnie, sprawdź\n"
                "czy zegar systemowy jest zsynchronizowany:\n"
                "Ustawienia → Czas i język → Ustaw czas automatycznie",
                parent=self
            )
            self.entry_totp.delete(0, "end")
            return
        logger.info(f"Weryfikacja 2FA zakończona sukcesem: użytkownik={user.username!r}")
        self._complete_login(user, self._temp_password)

    def _complete_login(self, user, master_password):
        _prefs.set("last_username", user.username)
        self.logged_user = user
        self.crypto = CryptoManager(master_password, user.salt)
        self._fade_out_destroy()

    def _fade_out_destroy(self, step: int = 0, steps: int = 6):
        """Płynne zanikanie okna logowania przed zniszczeniem — ukrywa flash przejścia."""
        try:
            self.attributes("-alpha", 1.0 - (step + 1) / steps)
        except Exception:
            pass
        if step + 1 < steps:
            self.after(14, lambda: self._fade_out_destroy(step + 1, steps))
        else:
            self.destroy()

    def _on_register(self):
        username = self.entry_username.get().strip()
        password = self.entry_password.get()
        password2 = self.entry_password2.get()
        logger.info(f"Próba rejestracji: użytkownik={username}")
        if not username or not password or not password2:
            show_error("Błąd", "Wypełnij wszystkie pola!", parent=self)
            return
        if len(password) < 8:
            show_error("Błąd", "Hasło musi mieć co najmniej 8 znaków!", parent=self)
            return
        if password != password2:
            show_error("Błąd", "Hasła nie są identyczne!", parent=self)
            return
        user = self.db.register_user(username, password)
        if not user:
            logger.warning(f"Rejestracja nieudana — użytkownik już istnieje: {username}")
            show_error("Błąd", f"Użytkownik '{username}' już istnieje!", parent=self)
            return
        logger.info(f"Konto utworzone: użytkownik={username}, generowanie TOTP...")
        totp_manager = TOTPManager()
        self.db.set_totp_secret(user, totp_manager.secret)
        self._temp_password = password
        self._show_setup_2fa_view(user, totp_manager)

    def _on_confirm_2fa_setup(self, user, totp_manager):
        code = self.entry_totp_setup.get().strip()
        logger.info(f"Próba potwierdzenia setup 2FA: użytkownik={user.username!r}, kod={code!r} (długość={len(code)})")
        if not totp_manager.verify(code):
            logger.warning(f"Błędny kod przy setup 2FA: użytkownik={user.username!r}, wpisany kod={code!r}")
            show_error(
                "Błąd",
                "Nieprawidłowy kod!\n\n"
                "Upewnij się że zegar systemowy jest zsynchronizowany:\n"
                "Ustawienia → Czas i język → Ustaw czas automatycznie",
                parent=self
            )
            return
        logger.info(f"Setup 2FA zakończony sukcesem: użytkownik={user.username!r}")
        self._show_welcome_view(user)

    # ── Ekran powitalny (po rejestracji) ──

    def _show_welcome_view(self, user):
        self._current_view = "welcome"
        self._clear_form()
        self.label_subtitle.configure(text="Witaj w AegisVault!")

        scroll = ctk.CTkScrollableFrame(self.form_frame, corner_radius=0, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        apply_hex_to_scrollable(scroll, hex_size=32, glow_max=2, glow_interval_ms=1600)

        ctk.CTkLabel(scroll, text="🎉",
                     font=ctk.CTkFont(size=42)).pack(pady=(16, 4))
        ctk.CTkLabel(scroll, text=f"Konto '{user.username}' gotowe!",
                     font=ctk.CTkFont(size=15, weight="bold")).pack()
        ctk.CTkLabel(
            scroll,
            text="Czy chcesz zaimportować hasła\nz innego menedżera haseł?",
            font=ctk.CTkFont(size=12), text_color="gray", justify="center"
        ).pack(pady=(6, 2))
        ctk.CTkLabel(
            scroll,
            text="Obsługujemy: LastPass, Bitwarden, 1Password\noraz dowolny plik CSV.",
            font=ctk.CTkFont(size=11), text_color="gray", justify="center"
        ).pack(pady=(0, 12))

        # Status importu (ukryty na start)
        self._welcome_status = ctk.CTkLabel(
            scroll, text="", font=ctk.CTkFont(size=11), justify="center"
        )
        self._welcome_status.pack(fill="x", padx=20)

        ctk.CTkButton(
            scroll, text="📥  Importuj hasła", height=44,
            fg_color=self._accent, hover_color=self._accent_hover,
            corner_radius=10, font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._welcome_import(user)
        ).pack(padx=20, pady=(8, 4), fill="x")

        self._welcome_skip_btn = ctk.CTkButton(
            scroll, text="Pomiń, zacznij od zera →", height=44,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"),
            hover_color=("gray85", "#2a2a2a"),
            text_color=("gray20", "gray80"),
            corner_radius=10, font=ctk.CTkFont(size=13),
            command=lambda: self._complete_login(user, self._temp_password)
        )
        self._welcome_skip_btn.pack(padx=20, pady=(4, 14), fill="x")

    def _welcome_import(self, user):
        from tkinter import filedialog
        filepath = filedialog.askopenfilename(
            title="Wybierz plik eksportu",
            filetypes=[
                ("Obsługiwane formaty", "*.csv *.json"),
                ("CSV", "*.csv"),
                ("JSON (Bitwarden)", "*.json"),
                ("Wszystkie pliki", "*.*"),
            ]
        )
        if not filepath:
            return

        self._welcome_status.configure(text="⏳ Importowanie...", text_color="gray")
        self.update()

        try:
            from utils.import_manager import import_file
            from core.crypto import CryptoManager

            items, fmt = import_file(filepath)
            crypto = CryptoManager(self._temp_password, user.salt)

            fmt_names = {
                "lastpass": "LastPass", "bitwarden": "Bitwarden",
                "1password": "1Password", "generic": "CSV"
            }
            imported = 0
            for item in items:
                self.db.add_password(
                    user, crypto,
                    title=item["title"],
                    username=item.get("username", ""),
                    plaintext_password=item.get("password", ""),
                    url=item.get("url", ""),
                    notes=item.get("notes", ""),
                    category=item.get("category", "Inne"),
                )
                imported += 1

            self._welcome_status.configure(
                text=f"✅ Zaimportowano {imported} haseł z {fmt_names.get(fmt, fmt)}!",
                text_color="#4caf50"
            )
            self._welcome_skip_btn.configure(text="Zacznij →")

        except Exception as e:
            self._welcome_status.configure(
                text=f"❌ Błąd importu: {e}", text_color="#e05252"
            )


if __name__ == "__main__":
    app = LoginWindow()
    app.mainloop()
