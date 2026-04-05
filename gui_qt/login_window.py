"""
login_window.py — Okno logowania / rejestracji (PyQt6)
======================================================
Widoki zarządzane przez QStackedWidget:
  0 — login
  1 — register (QScrollArea)
  2 — 2FA (TOTP + Push Approve sub-stack)
  3 — setup 2FA (QR kod)
  4 — welcome / import

Sygnały Qt zapewniają thread-safe komunikację z wątkami (WH, Push).
Po udanym logowaniu: self.logged_user + self.crypto ustawione, window zamknięte.
"""

import os
import platform
import threading
import qrcode
from PIL import Image
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QStackedWidget, QScrollArea,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QProgressBar, QFrame, QFileDialog,
    QSizePolicy, QButtonGroup,
)
from PyQt6.QtCore  import Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui   import QPixmap, QIcon, QFont, QImage

from database.db_manager import DatabaseManager
from core.crypto  import CryptoManager
from core.totp    import TOTPManager
from utils.password_strength import check_strength, _build_checklist
from utils.push_auth  import PushAuthClient
from utils.prefs_manager import PrefsManager
import utils.windows_hello as wh
from utils.logger import get_logger

from gui_qt.gradient       import AnimatedGradientWidget
from gui_qt.hex_background import HexBackground
from gui_qt.animations     import shake
from gui_qt.dialogs        import show_error, show_info, show_success
from gui_qt.style          import build_qss

logger = get_logger(__name__)
_prefs = PrefsManager()

_ON_WINDOWS = platform.system() == "Windows"


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


def _make_logo_pixmap(accent: str, size: int = 64) -> QPixmap | None:
    icon_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png"
    )
    try:
        img = Image.open(icon_path).convert("RGBA").resize((size, size), Image.LANCZOS)
        r, g, b = int(accent[1:3], 16), int(accent[3:5], 16), int(accent[5:7], 16)
        pixels = img.load()
        for y in range(img.height):
            for x in range(img.width):
                _, _, _, a = pixels[x, y]
                if a > 10:
                    pixels[x, y] = (r, g, b, a)
        return _pil_to_pixmap(img)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════
# LoginWindow
# ══════════════════════════════════════════════════════════════════════

class LoginWindow(QMainWindow):
    # Sygnały thread-safe (emitowane z wątków, obsługiwane w głównym wątku)
    _wh_ready      = pyqtSignal(bool)           # WH availability check done
    _wh_result     = pyqtSignal(bool, str)      # WH verify done (success, password_or_error)
    _push_started  = pyqtSignal(str, str)       # token, url
    _push_error    = pyqtSignal(str)
    _push_status   = pyqtSignal(str)            # "approved" | "denied" | "expired" | "pending"

    def __init__(self, db_path: str = "aegisvault.db"):
        super().__init__()
        self._accent       = _prefs.get_accent()
        self._accent_hover = _prefs.get_accent_hover()
        dark = (_prefs.get("appearance_mode") or "dark").lower() != "light"

        self.db          = DatabaseManager(db_path)
        self.logged_user = None
        self.crypto      = None
        self._temp_password  = None
        self._pending_user   = None
        self._push_token     = None
        self._push_poll_timer = QTimer(self)
        self._push_poll_timer.setInterval(2000)
        self._wh_available   = False
        self._push_client    = PushAuthClient()

        self.setWindowTitle("AegisVault — Logowanie")
        self.setFixedSize(460, 620)
        self.setStyleSheet(build_qss(accent=self._accent, dark=dark))

        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png"
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._build_ui(dark)
        self._connect_signals()

        logger.info(f"=== LoginWindow uruchomiony | db={db_path} ===")

        # Windows Hello check w tle
        if _ON_WINDOWS:
            threading.Thread(target=self._check_wh, daemon=True).start()

    # ── Budowanie UI ──────────────────────────────────────────────────

    def _build_ui(self, dark: bool):
        central = QWidget()
        self.setCentralWidget(central)

        # HexBackground — pod wszystkim
        self._hex_bg = HexBackground(
            central, hex_size=32, glow_max=3, glow_interval_ms=1600
        )

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Lewy pasek gradientu (10px, pionowy, animowany)
        bg_color = "#212121" if dark else "#f0f0f0"
        self._accent_bar = AnimatedGradientWidget(
            accent=self._accent, base=bg_color,
            anim_mode="slide", fps=15, period_ms=8000,
            n_bands=1, direction="v",
        )
        self._accent_bar.setFixedWidth(10)
        self._accent_bar.start_animation()
        root_layout.addWidget(self._accent_bar)

        # Prawa część — logo + stos widoków
        right = QWidget()
        right.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(30, 24, 30, 24)
        right_layout.setSpacing(0)
        root_layout.addWidget(right, stretch=1)

        # Logo
        self._logo_lbl = QLabel()
        self._logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = _make_logo_pixmap(self._accent, 64)
        if pix:
            self._logo_lbl.setPixmap(pix)
        else:
            self._logo_lbl.setText("🔐")
            self._logo_lbl.setStyleSheet("font-size: 48px;")
        right_layout.addWidget(self._logo_lbl)

        # Tytuł
        title = QLabel("AegisVault")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 26px; font-weight: bold; margin-top: 4px;")
        right_layout.addWidget(title)

        # Podtytuł — zmienny zależnie od widoku
        self._subtitle = QLabel("Zaloguj się do swojego sejfu")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setStyleSheet("color: #888888; font-size: 13px; margin-bottom: 18px;")
        right_layout.addWidget(self._subtitle)

        # QStackedWidget z widokami
        self._stack = QStackedWidget()
        right_layout.addWidget(self._stack, stretch=1)

        self._page_login    = self._build_login_page(dark)
        self._page_register = self._build_register_page(dark)
        self._page_2fa      = self._build_2fa_page(dark)
        self._page_setup2fa = self._build_setup2fa_page(dark)
        self._page_welcome  = self._build_welcome_page(dark)

        for page in [self._page_login, self._page_register,
                     self._page_2fa, self._page_setup2fa, self._page_welcome]:
            self._stack.addWidget(page)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        c = self.centralWidget()
        if c and self._hex_bg:
            self._hex_bg.setGeometry(0, 0, c.width(), c.height())
            self._hex_bg.lower()

    # ── Strona: Logowanie ─────────────────────────────────────────────

    def _build_login_page(self, dark: bool) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setSpacing(4)

        self._login_user = self._make_field(layout, "Nazwa użytkownika",
                                            "Wpisz login...", secret=False)
        self._login_pass = self._make_field(layout, "Hasło masterowe",
                                            "Wpisz hasło...", secret=True)
        self._login_pass.returnPressed.connect(self._on_login)

        last = _prefs.get("last_username")
        if last:
            self._login_user.setText(last)

        layout.addSpacing(14)
        self._btn_login = self._make_btn(layout, "Zaloguj się", self._on_login, primary=True)

        # Windows Hello — tylko Windows
        self._wh_btn = QPushButton("🪟  Windows Hello")
        self._wh_btn.setEnabled(False)
        self._wh_btn.setVisible(_ON_WINDOWS)
        self._apply_secondary_style(self._wh_btn)
        self._wh_btn.clicked.connect(self._on_windows_hello)
        layout.addWidget(self._wh_btn)

        # Divider
        div = QLabel("─────── lub ───────")
        div.setAlignment(Qt.AlignmentFlag.AlignCenter)
        div.setStyleSheet("color: #666; font-size: 11px; margin: 4px 0;")
        layout.addWidget(div)

        self._make_btn(layout, "Utwórz nowe konto",
                       self._show_register, primary=False)
        layout.addStretch()
        return page

    # ── Strona: Rejestracja ───────────────────────────────────────────

    def _build_register_page(self, dark: bool) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        outer.addWidget(scroll)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setSpacing(4)

        self._reg_user  = self._make_field(layout, "Nazwa użytkownika",
                                           "Wymyśl login...", secret=False)
        self._reg_pass  = self._make_field(layout, "Hasło masterowe",
                                           "Min. 8 znaków...", secret=True)

        # Pasek siły
        self._reg_strength_bar = QProgressBar()
        self._reg_strength_bar.setRange(0, 100)
        self._reg_strength_bar.setValue(0)
        self._reg_strength_bar.setFixedHeight(6)
        self._reg_strength_bar.setTextVisible(False)
        self._reg_strength_bar.setStyleSheet(
            "QProgressBar { background:#2a2a2a; border-radius:3px; border:none; }"
            "QProgressBar::chunk { background:#4F8EF7; border-radius:3px; }"
        )
        layout.addWidget(self._reg_strength_bar)

        self._reg_strength_lbl = QLabel()
        self._reg_strength_lbl.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(self._reg_strength_lbl)

        # Checklist wymagań hasła
        checklist_frame = QFrame()
        dark_c = (_prefs.get("appearance_mode") or "dark").lower() != "light"
        checklist_frame.setStyleSheet(
            f"background: {'#252525' if dark_c else '#e8e8e8'};"
            "border-radius: 8px; padding: 4px;"
        )
        cl_layout = QVBoxLayout(checklist_frame)
        cl_layout.setContentsMargins(8, 4, 8, 4)
        cl_layout.setSpacing(2)
        self._checklist_rows: list[QLabel] = []
        for item in _build_checklist(""):
            lbl = QLabel(f"❌  {item['text']}")
            lbl.setStyleSheet("font-size: 11px; color: #666; background: transparent;")
            cl_layout.addWidget(lbl)
            self._checklist_rows.append(lbl)
        layout.addWidget(checklist_frame)

        self._reg_pass2 = self._make_field(layout, "Powtórz hasło",
                                           "Powtórz hasło...", secret=True)
        self._reg_match_lbl = QLabel()
        self._reg_match_lbl.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._reg_match_lbl)

        self._reg_pass.textChanged.connect(self._on_reg_password_change)
        self._reg_pass2.textChanged.connect(self._on_reg_match_change)
        self._reg_pass2.returnPressed.connect(self._on_register)

        layout.addSpacing(8)
        self._make_btn(layout, "Zarejestruj się", self._on_register, primary=True)
        self._make_btn(layout, "← Mam już konto", self._show_login, primary=False)
        layout.addStretch()
        return page

    # ── Strona: 2FA ───────────────────────────────────────────────────

    def _build_2fa_page(self, dark: bool) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setSpacing(8)

        # Przełącznik trybu TOTP / Push
        toggle_row = QHBoxLayout()
        self._btn_totp_tab = QPushButton("Kod TOTP")
        self._btn_push_tab = QPushButton("Push Approve")
        for b in [self._btn_totp_tab, self._btn_push_tab]:
            b.setCheckable(True)
            b.setFixedHeight(34)
            b.setStyleSheet("""
                QPushButton { background:#2a2a2a; color:#aaa; border:none;
                              border-radius:6px; font-size:12px; padding: 0 12px; }
                QPushButton:checked { background:#4F8EF7; color:white; font-weight:600; }
                QPushButton:hover:!checked { background:#333; }
            """)
        self._btn_totp_tab.setChecked(True)
        self._btn_totp_tab.clicked.connect(lambda: self._switch_2fa("totp"))
        self._btn_push_tab.clicked.connect(lambda: self._switch_2fa("push"))
        toggle_row.addWidget(self._btn_totp_tab)
        toggle_row.addWidget(self._btn_push_tab)
        layout.addLayout(toggle_row)

        # Sub-stack: TOTP | Push
        self._2fa_stack = QStackedWidget()
        layout.addWidget(self._2fa_stack, stretch=1)

        # Sub-page 0: TOTP
        totp_page = QWidget()
        totp_page.setStyleSheet("background: transparent;")
        totp_layout = QVBoxLayout(totp_page)
        totp_layout.setSpacing(8)
        desc = QLabel("Otwórz Google Authenticator\nlub Microsoft Authenticator\ni wpisz 6-cyfrowy kod:")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #888; font-size: 12px;")
        totp_layout.addWidget(desc)
        self._totp_entry = QLineEdit()
        self._totp_entry.setPlaceholderText("000000")
        self._totp_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._totp_entry.setFixedHeight(52)
        self._totp_entry.setStyleSheet(
            "font-size: 26px; border-radius: 8px;"
            "background: #252525; color: white; border: 1px solid #333;"
            "letter-spacing: 8px;"
        )
        self._totp_entry.returnPressed.connect(self._on_verify_2fa)
        totp_layout.addWidget(self._totp_entry)
        self._make_btn(totp_layout, "Weryfikuj", self._on_verify_2fa, primary=True)
        totp_layout.addStretch()
        self._2fa_stack.addWidget(totp_page)

        # Sub-page 1: Push
        push_page = QWidget()
        push_page.setStyleSheet("background: transparent;")
        push_layout = QVBoxLayout(push_page)
        push_layout.setSpacing(6)
        self._push_status_lbl = QLabel("⏳ Łączenie z serwerem...")
        self._push_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._push_status_lbl.setStyleSheet("color: #888; font-size: 12px;")
        push_layout.addWidget(self._push_status_lbl)
        self._push_qr_lbl = QLabel()
        self._push_qr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        push_layout.addWidget(self._push_qr_lbl)
        self._push_url_lbl = QLabel()
        self._push_url_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._push_url_lbl.setWordWrap(True)
        self._push_url_lbl.setStyleSheet("color: #666; font-size: 10px;")
        push_layout.addWidget(self._push_url_lbl)
        push_layout.addStretch()
        self._2fa_stack.addWidget(push_page)

        self._make_btn(layout, "← Wróć", self._show_login, primary=False)
        return page

    # ── Strona: Setup 2FA ─────────────────────────────────────────────

    def _build_setup2fa_page(self, dark: bool) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setSpacing(8)

        QLabel("Zeskanuj kod QR w Google Authenticator:").setParent(page)
        desc = QLabel("Zeskanuj kod QR w Google Authenticator:")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("font-size: 12px;")
        layout.addWidget(desc)

        self._setup2fa_qr = QLabel()
        self._setup2fa_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._setup2fa_qr)

        hint = QLabel("Następnie wpisz kod aby potwierdzić:")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(hint)

        self._setup2fa_entry = QLineEdit()
        self._setup2fa_entry.setPlaceholderText("000000")
        self._setup2fa_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._setup2fa_entry.setFixedHeight(45)
        self._setup2fa_entry.setStyleSheet(
            "font-size: 20px; border-radius: 8px;"
            "background: #252525; color: white; border: 1px solid #333;"
            "letter-spacing: 8px;"
        )
        layout.addWidget(self._setup2fa_entry)
        layout.addSpacing(8)
        self._make_btn(layout, "Potwierdź i zaloguj się",
                       self._on_confirm_2fa_setup, primary=True)
        layout.addStretch()
        return page

    # ── Strona: Welcome ───────────────────────────────────────────────

    def _build_welcome_page(self, dark: bool) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        outer.addWidget(scroll)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setSpacing(4)

        emoji = QLabel("🎉")
        emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)
        emoji.setStyleSheet("font-size: 42px; margin-top: 16px;")
        layout.addWidget(emoji)

        self._welcome_name_lbl = QLabel("Konto gotowe!")
        self._welcome_name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._welcome_name_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(self._welcome_name_lbl)

        for txt in [
            "Czy chcesz zaimportować hasła\nz innego menedżera haseł?",
            "Obsługujemy: LastPass, Bitwarden, 1Password\noraz dowolny plik CSV.",
        ]:
            l = QLabel(txt)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setStyleSheet("color: #888; font-size: 12px;")
            layout.addWidget(l)

        self._welcome_status_lbl = QLabel()
        self._welcome_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._welcome_status_lbl.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._welcome_status_lbl)

        self._make_btn(layout, "📥  Importuj hasła",
                       self._welcome_import, primary=True)
        self._welcome_skip_btn = QPushButton("Pomiń, zacznij od zera →")
        self._welcome_skip_btn.setFixedHeight(44)
        self._apply_secondary_style(self._welcome_skip_btn)
        self._welcome_skip_btn.clicked.connect(
            lambda: self._complete_login(self._pending_user, self._temp_password)
        )
        layout.addWidget(self._welcome_skip_btn)
        layout.addStretch()
        return page

    # ── Połączenie sygnałów ───────────────────────────────────────────

    def _connect_signals(self):
        self._wh_ready.connect(self._on_wh_ready)
        self._wh_result.connect(self._on_wh_result)
        self._push_started.connect(self._on_push_started)
        self._push_error.connect(lambda msg: self._push_status_lbl.setText(f"❌ {msg}"))
        self._push_status.connect(self._on_push_poll_result)
        self._push_poll_timer.timeout.connect(self._poll_push)

    # ── Nawigacja między widokami ─────────────────────────────────────

    def _show_login(self):
        self._push_poll_timer.stop()
        self._push_token = None
        self._subtitle.setText("Zaloguj się do swojego sejfu")
        self._stack.setCurrentIndex(0)
        QTimer.singleShot(50, self._login_pass.setFocus
                          if _prefs.get("last_username") else self._login_user.setFocus)

    def _show_register(self):
        self._subtitle.setText("Utwórz nowe konto")
        self._stack.setCurrentIndex(1)
        QTimer.singleShot(50, self._reg_user.setFocus)

    def _show_2fa(self, user):
        self._pending_user = user
        self._subtitle.setText("Weryfikacja dwuetapowa")
        self._stack.setCurrentIndex(2)
        self._switch_2fa("totp")
        QTimer.singleShot(50, self._totp_entry.setFocus)

    def _show_setup2fa(self, user, totp_manager):
        self._pending_user = user
        qr_img = totp_manager.get_qr_image(user.username)
        qr_img = qr_img.resize((180, 180), Image.NEAREST)
        self._setup2fa_qr.setPixmap(_pil_to_pixmap(qr_img))
        self._setup2fa_totp_manager = totp_manager
        self._subtitle.setText("Skonfiguruj 2FA")
        self._stack.setCurrentIndex(3)
        QTimer.singleShot(50, self._setup2fa_entry.setFocus)

    def _show_welcome(self, user):
        self._pending_user = user
        self._welcome_name_lbl.setText(f"Konto '{user.username}' gotowe!")
        self._subtitle.setText("Witaj w AegisVault!")
        self._stack.setCurrentIndex(4)

    def _switch_2fa(self, mode: str):
        self._push_poll_timer.stop()
        self._push_token = None
        if mode == "totp":
            self._btn_totp_tab.setChecked(True)
            self._btn_push_tab.setChecked(False)
            self._2fa_stack.setCurrentIndex(0)
            QTimer.singleShot(50, self._totp_entry.setFocus)
        else:
            self._btn_totp_tab.setChecked(False)
            self._btn_push_tab.setChecked(True)
            self._2fa_stack.setCurrentIndex(1)
            self._push_status_lbl.setText("⏳ Łączenie z serwerem...")
            self._push_qr_lbl.clear()
            self._push_url_lbl.clear()
            threading.Thread(
                target=self._start_push_auth,
                args=(self._pending_user,),
                daemon=True,
            ).start()

    # ── Logika ────────────────────────────────────────────────────────

    def _on_login(self):
        username = self._login_user.text().strip()
        password = self._login_pass.text()
        if not username or not password:
            show_error("Błąd", "Wypełnij wszystkie pola!", parent=self)
            return
        user = self.db.login_user(username, password)
        if not user:
            shake(self)
            show_error("Błąd logowania",
                       "Nieprawidłowa nazwa użytkownika lub hasło.", parent=self)
            return
        if user.totp_secret:
            self._temp_password = password
            self._show_2fa(user)
        else:
            self._complete_login(user, password)

    def _on_verify_2fa(self):
        code = self._totp_entry.text().strip()
        user = self._pending_user
        totp = TOTPManager(secret=user.totp_secret)
        if not totp.verify(code):
            shake(self)
            show_error("Błąd 2FA",
                       "Nieprawidłowy kod!\n\nSprawdź czy zegar systemowy "
                       "jest zsynchronizowany.", parent=self)
            self._totp_entry.clear()
            return
        self._complete_login(user, self._temp_password)

    def _on_register(self):
        username  = self._reg_user.text().strip()
        password  = self._reg_pass.text()
        password2 = self._reg_pass2.text()
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
            show_error("Błąd", f"Użytkownik '{username}' już istnieje!", parent=self)
            return
        totp_manager = TOTPManager()
        self.db.set_totp_secret(user, totp_manager.secret)
        self._temp_password = password
        self._show_setup2fa(user, totp_manager)

    def _on_confirm_2fa_setup(self):
        code = self._setup2fa_entry.text().strip()
        tm   = self._setup2fa_totp_manager
        if not tm.verify(code):
            show_error("Błąd",
                       "Nieprawidłowy kod!\n\nUpewnij się że zegar "
                       "systemowy jest zsynchronizowany.", parent=self)
            return
        self._show_welcome(self._pending_user)

    def _complete_login(self, user, master_password: str):
        _prefs.set("last_username", user.username)
        self.logged_user = user
        self.crypto = CryptoManager(master_password, user.salt)
        self._fade_and_close()

    def _fade_and_close(self):
        """Płynne zanikanie przed zamknięciem."""
        steps = 6
        def _step(i=0):
            self.setWindowOpacity(1.0 - (i + 1) / steps)
            if i + 1 < steps:
                QTimer.singleShot(14, lambda: _step(i + 1))
            else:
                self.close()
        _step()

    # ── Rejestracja — live feedback ───────────────────────────────────

    def _on_reg_password_change(self):
        pwd    = self._reg_pass.text()
        result = check_strength(pwd)
        self._reg_strength_bar.setValue(int(result["percent"]))
        color  = result["color"].replace("#", "")
        self._reg_strength_bar.setStyleSheet(
            "QProgressBar { background:#2a2a2a; border-radius:3px; border:none; height:6px; }"
            f"QProgressBar::chunk {{ background:{result['color']}; border-radius:3px; }}"
        )
        if result["label"]:
            self._reg_strength_lbl.setText(
                f"{result['label']}   •   Entropia: {result['entropy']} bit"
            )
            self._reg_strength_lbl.setStyleSheet(
                f"font-size:11px; color:{result['color']};"
            )
        else:
            self._reg_strength_lbl.clear()

        for item, row in zip(result["checklist"], self._checklist_rows):
            icon  = "✅" if item["met"] else "❌"
            color = "#38a169" if item["met"] else ("#666" if not pwd else "#e53e3e")
            row.setText(f"{icon}  {item['text']}")
            row.setStyleSheet(f"font-size:11px; color:{color}; background:transparent;")

        self._on_reg_match_change()

    def _on_reg_match_change(self):
        pwd  = self._reg_pass.text()
        pwd2 = self._reg_pass2.text()
        if not pwd2:
            self._reg_match_lbl.clear()
            return
        if pwd == pwd2:
            self._reg_match_lbl.setText("✅ Hasła są zgodne")
            self._reg_match_lbl.setStyleSheet("font-size:11px; color:#38a169;")
        else:
            self._reg_match_lbl.setText("❌ Hasła nie są takie same")
            self._reg_match_lbl.setStyleSheet("font-size:11px; color:#e53e3e;")

    # ── Windows Hello ─────────────────────────────────────────────────

    def _check_wh(self):
        available = wh.is_available()
        self._wh_ready.emit(available)

    def _on_wh_ready(self, available: bool):
        self._wh_available = available
        if available:
            self._wh_btn.setEnabled(True)

    def _on_windows_hello(self):
        username = self._login_user.text().strip()
        if not username:
            show_error("Windows Hello", "Wpisz najpierw nazwę użytkownika.", parent=self)
            return
        user = self.db.get_user(username)
        if not user:
            show_error("Windows Hello", f"Nie znaleziono użytkownika '{username}'.", parent=self)
            return
        if not wh.has_credential(username):
            show_error("Windows Hello",
                       "Windows Hello nie jest skonfigurowane dla tego konta.\n\n"
                       "Zaloguj się hasłem, a następnie włącz je w:\nUstawienia → Windows Hello.",
                       parent=self)
            return
        self._wh_btn.setEnabled(False)
        self._wh_btn.setText("⏳  Weryfikacja…")
        self.lower()
        threading.Thread(
            target=self._wh_verify,
            args=(user,),
            daemon=True,
        ).start()

    def _wh_verify(self, user):
        verified = wh.verify("Zaloguj się do AegisVault")
        if not verified:
            self._wh_result.emit(False, "")
            return
        pwd = wh.get_credential(user.username)
        if not pwd:
            self._wh_result.emit(False, "no_cred")
            return
        verified_user = self.db.login_user(user.username, pwd)
        if not verified_user:
            self._wh_result.emit(False, "stale")
            return
        self._wh_result.emit(True, pwd)
        self._pending_user = verified_user

    def _on_wh_result(self, success: bool, pwd_or_err: str):
        self.raise_()
        self.activateWindow()
        if not success:
            self._wh_btn.setEnabled(True)
            self._wh_btn.setText("🪟  Windows Hello")
            msgs = {
                "no_cred": "Nie można odczytać poświadczeń. Spróbuj zalogować się hasłem.",
                "stale":   "Zapisane poświadczenia są nieaktualne.\nWyłącz i ponownie włącz Windows Hello.",
            }
            show_error("Windows Hello",
                       msgs.get(pwd_or_err, "Weryfikacja anulowana lub nieudana."),
                       parent=self)
        else:
            self._complete_login(self._pending_user, pwd_or_err)

    # ── Push Approve ──────────────────────────────────────────────────

    def _start_push_auth(self, user):
        if not self._push_client.is_available():
            self._push_error.emit("Serwer sync niedostępny.\nUruchom go: start_server.bat")
            return
        try:
            data  = self._push_client.create_challenge(user.username)
            token = data["token"]
            url   = self._push_client.get_approve_url(token)
            self._push_token = token
        except Exception as e:
            self._push_error.emit(str(e))
            return

        qr_img = qrcode.make(url).resize((160, 160), Image.LANCZOS)
        pix    = _pil_to_pixmap(qr_img)
        self._push_started.emit(url, "")
        # Pixmap musi być ustawiony w głównym wątku — emitujemy przez sygnał
        # ale pixmap jest thread-local, więc ustawiamy go bezpośrednio tu
        # przez mechanizm Qt (sygnał auto-connection = queued)
        self._push_qr_pixmap = pix
        self._push_started.emit(url, "qr_ready")

    def _on_push_started(self, url: str, flag: str):
        self._push_url_lbl.setText(url)
        self._push_status_lbl.setText(
            "Zeskanuj QR lub otwórz link na telefonie,\nnastępnie zatwierdź logowanie."
        )
        self._push_status_lbl.setStyleSheet("color: #888; font-size: 12px;")
        if flag == "qr_ready" and hasattr(self, "_push_qr_pixmap"):
            self._push_qr_lbl.setPixmap(self._push_qr_pixmap)
        self._push_poll_timer.start()

    def _poll_push(self):
        if self._push_token is None:
            self._push_poll_timer.stop()
            return
        status = self._push_client.poll_status(self._push_token)
        self._push_status.emit(status)

    def _on_push_poll_result(self, status: str):
        if status == "approved":
            self._push_status_lbl.setText("✅ Zatwierdzono! Logowanie...")
            self._push_status_lbl.setStyleSheet("color: #4caf50; font-size: 12px;")
            self._push_poll_timer.stop()
            self._push_token = None
            QTimer.singleShot(400, lambda: self._complete_login(
                self._pending_user, self._temp_password
            ))
        elif status == "denied":
            self._push_status_lbl.setText("❌ Logowanie odrzucone na telefonie.")
            self._push_status_lbl.setStyleSheet("color: #e05252; font-size: 12px;")
            self._push_poll_timer.stop()
        elif status in ("expired", "error"):
            self._push_status_lbl.setText("⏰ Żądanie wygasło. Przełącz tryb, aby spróbować ponownie.")
            self._push_status_lbl.setStyleSheet("color: #f0a500; font-size: 12px;")
            self._push_poll_timer.stop()
        # pending → timer odpyta ponownie za 2s

    # ── Welcome — import ──────────────────────────────────────────────

    def _welcome_import(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Wybierz plik eksportu", "",
            "Obsługiwane formaty (*.csv *.json);;CSV (*.csv);;JSON Bitwarden (*.json);;Wszystkie (*.*)"
        )
        if not filepath:
            return

        self._welcome_status_lbl.setText("⏳ Importowanie...")
        self._welcome_status_lbl.setStyleSheet("font-size:11px; color:#888;")

        try:
            from utils.import_manager import import_file
            items, fmt = import_file(filepath)
            user   = self._pending_user
            crypto = CryptoManager(self._temp_password, user.salt)
            fmt_names = {
                "lastpass": "LastPass", "bitwarden": "Bitwarden",
                "1password": "1Password", "generic": "CSV",
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
            self._welcome_status_lbl.setText(
                f"✅ Zaimportowano {imported} haseł z {fmt_names.get(fmt, fmt)}!"
            )
            self._welcome_status_lbl.setStyleSheet("font-size:11px; color:#4caf50;")
            self._welcome_skip_btn.setText("Zacznij →")
        except Exception as e:
            self._welcome_status_lbl.setText(f"❌ Błąd importu: {e}")
            self._welcome_status_lbl.setStyleSheet("font-size:11px; color:#e05252;")

    # ── Helpers UI ────────────────────────────────────────────────────

    def _make_field(self, layout: QVBoxLayout, label: str,
                    placeholder: str, secret: bool) -> QLineEdit:
        lbl = QLabel(label)
        lbl.setStyleSheet("font-size: 12px; margin-top: 12px; margin-bottom: 2px;")
        layout.addWidget(lbl)
        entry = QLineEdit()
        entry.setPlaceholderText(placeholder)
        entry.setFixedHeight(42)
        if secret:
            entry.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(entry)
        return entry

    def _make_btn(self, layout: QVBoxLayout, text: str,
                  command, primary: bool = True) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(44)
        if primary:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self._accent}; color: white;
                    border: none; border-radius: 10px;
                    font-size: 14px; font-weight: bold;
                    margin-top: 4px;
                }}
                QPushButton:hover {{ background-color: {self._accent_hover}; }}
                QPushButton:pressed {{ background-color: #2d6bc4; }}
            """)
        else:
            self._apply_secondary_style(btn)
        btn.clicked.connect(command)
        layout.addWidget(btn)
        return btn

    def _apply_secondary_style(self, btn: QPushButton):
        btn.setFixedHeight(44)
        btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #aaa;
                border: 1px solid #444; border-radius: 10px;
                font-size: 13px; margin-top: 2px; margin-bottom: 10px;
            }
            QPushButton:hover { background: #2a2a2a; border-color: #666; }
            QPushButton:disabled { color: #555; border-color: #333; }
        """)
