"""
login_window.py — Okno logowania / rejestracji (PyQt6)
======================================================
Widoki zarządzane przez QStackedWidget:
  0 — login
  1 — register (QScrollArea)
  2 — 2FA (TOTP + Push Approve sub-stack)
  3 — setup 2FA (QR kod)
  4 — welcome / import
  5 — reset masterhasła (3 kroki: użytkownik → TOTP → nowe hasło)

Sygnały Qt zapewniają thread-safe komunikację z wątkami (WH, Push).
Po udanym logowaniu: self.logged_user + self.crypto ustawione, window zamknięte.
"""

import os
import platform
import threading
import time
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
from core.crypto  import CryptoManager, KDF_PBKDF2
from core.totp    import TOTPManager
from utils.password_strength import check_strength, _build_checklist
from utils.push_auth  import PushAuthClient
from utils.prefs_manager import PrefsManager
import utils.windows_hello as wh
from utils.logger import get_logger

from gui_qt.gradient       import AnimatedGradientWidget
from gui_qt.hex_background import HexBackground
from gui_qt.animations     import shake
from gui_qt.dialogs        import show_error, show_info, show_success, show_warning
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
        self._check_db_integrity()
        self.logged_user = None
        self.crypto      = None
        self._temp_password  = None
        self._pending_user   = None
        self._push_token     = None
        self._push_poll_timer = QTimer(self)
        self._push_poll_timer.setInterval(2000)
        self._wh_available   = False
        self._push_client    = PushAuthClient()

        # Limit prób logowania (w pamięci, reset przy restarcie)
        self._login_attempts  = 0   # błędne próby masterhasła
        self._totp_attempts   = 0   # błędne próby kodu TOTP
        self._lockout_until   = 0.0 # timestamp końca lockoutu (time.monotonic)
        self._lockout_timer   = QTimer(self)
        self._lockout_timer.setInterval(1000)
        self._lockout_timer.timeout.connect(self._tick_lockout)

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

    # ── Integrity check ───────────────────────────────────────────────

    def _check_db_integrity(self):
        """Sprawdza integralność bazy SQLite przy starcie. Ostrzega gdy baza jest uszkodzona."""
        import os
        db_path = getattr(self.db, "db_path", None)
        if not db_path or not os.path.exists(db_path):
            return  # nowa baza — nic do sprawdzenia
        try:
            error = self.db.integrity_check()
            if error:
                get_logger().error(f"DB integrity check failed: {error}")
                show_warning(
                    "Baza danych — ostrzeżenie",
                    f"Wykryto problem z plikiem bazy danych:\n\n{error}\n\n"
                    "Zaleca się przywrócenie backupu. Aplikacja spróbuje kontynuować,\n"
                    "ale niektóre dane mogą być niedostępne.",
                )
        except Exception as e:
            get_logger().warning(f"DB integrity check exception: {e}")

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
        self._page_reset    = self._build_reset_page(dark)

        for page in [self._page_login, self._page_register,
                     self._page_2fa, self._page_setup2fa, self._page_welcome,
                     self._page_reset]:
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

        # Komunikat o lockoucie / pozostałych próbach
        self._lockout_lbl = QLabel("")
        self._lockout_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lockout_lbl.setStyleSheet("color: #e53e3e; font-size: 11px; background: transparent; border: none;")
        self._lockout_lbl.setVisible(False)
        layout.addWidget(self._lockout_lbl)

        layout.addSpacing(8)
        self._btn_login = self._make_btn(layout, "Zaloguj się", self._on_login, primary=True)

        forgot_btn = QPushButton("Nie pamiętam hasła")
        forgot_btn.setFixedHeight(28)
        forgot_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; "
            "color: #666; font-size: 12px; text-decoration: underline; }"
            "QPushButton:hover { color: #aaa; }"
        )
        forgot_btn.clicked.connect(self._show_reset)
        layout.addWidget(forgot_btn, alignment=Qt.AlignmentFlag.AlignCenter)

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

        self._totp_lockout_lbl = QLabel("")
        self._totp_lockout_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._totp_lockout_lbl.setStyleSheet("color: #e53e3e; font-size: 11px; background: transparent; border: none;")
        self._totp_lockout_lbl.setVisible(False)
        totp_layout.addWidget(self._totp_lockout_lbl)

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

    # ── Strona: Reset masterhasła ─────────────────────────────────────

    def _build_reset_page(self, dark: bool) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Wewnętrzny stos: krok1 | krok2 | krok3
        self._reset_stack = QStackedWidget()
        self._reset_stack.setStyleSheet("background: transparent;")
        outer.addWidget(self._reset_stack)

        # ── Krok 1: nazwa użytkownika ──────────────────────────────────
        step1 = QWidget()
        step1.setStyleSheet("background: transparent;")
        s1l = QVBoxLayout(step1)
        s1l.setSpacing(4)

        h = QLabel("Resetuj hasło masterowe")
        h.setStyleSheet("font-size: 15px; font-weight: bold; margin-bottom: 4px;")
        s1l.addWidget(h)

        desc = QLabel("Podaj nazwę użytkownika.\nReset wymaga aktywnego 2FA (kod z aplikacji authenticator).")
        desc.setAlignment(Qt.AlignmentFlag.AlignLeft)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 12px; margin-bottom: 8px;")
        s1l.addWidget(desc)

        self._reset_user_e = self._make_field(s1l, "Nazwa użytkownika", "Wpisz login...", secret=False)
        self._reset_user_e.returnPressed.connect(self._on_reset_step1)
        self._reset_step1_err = QLabel("")
        self._reset_step1_err.setStyleSheet("color: #e53e3e; font-size: 11px;")
        self._reset_step1_err.setVisible(False)
        s1l.addWidget(self._reset_step1_err)
        s1l.addSpacing(8)
        self._make_btn(s1l, "Dalej →", self._on_reset_step1, primary=True)
        back1 = QPushButton("← Wróć do logowania")
        back1.setFixedHeight(36)
        back1.setStyleSheet(
            "QPushButton { background: transparent; border: none; "
            "color: #666; font-size: 12px; }"
            "QPushButton:hover { color: #aaa; }"
        )
        back1.clicked.connect(self._show_login)
        s1l.addWidget(back1, alignment=Qt.AlignmentFlag.AlignCenter)
        s1l.addStretch()

        # ── Krok 2: weryfikacja TOTP ───────────────────────────────────
        step2 = QWidget()
        step2.setStyleSheet("background: transparent;")
        s2l = QVBoxLayout(step2)
        s2l.setSpacing(4)

        h2 = QLabel("Weryfikacja 2FA")
        h2.setStyleSheet("font-size: 15px; font-weight: bold; margin-bottom: 4px;")
        s2l.addWidget(h2)

        # Zakładki: TOTP | Klucz recovery
        tab_row = QWidget()
        tab_row.setStyleSheet("background: transparent;")
        trl = QHBoxLayout(tab_row)
        trl.setContentsMargins(0, 0, 0, 4)
        trl.setSpacing(6)
        self._reset_tab_totp = QPushButton("📱 Kod 2FA")
        self._reset_tab_rec  = QPushButton("🔑 Klucz recovery")
        for btn in (self._reset_tab_totp, self._reset_tab_rec):
            btn.setFixedHeight(32)
            btn.setCheckable(True)
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: #888; border: 1px solid #444; border-radius: 8px; font-size: 12px; }}"
                f"QPushButton:checked {{ background: {self._accent}22; color: {self._accent}; border-color: {self._accent}; }}"
            )
        self._reset_tab_totp.setChecked(True)
        self._reset_tab_totp.clicked.connect(lambda: self._switch_reset_tab("totp"))
        self._reset_tab_rec.clicked.connect(lambda: self._switch_reset_tab("recovery"))
        trl.addWidget(self._reset_tab_totp)
        trl.addWidget(self._reset_tab_rec)
        trl.addStretch()
        s2l.addWidget(tab_row)

        # Sub-stack: TOTP | Recovery
        self._reset_verify_stack = QStackedWidget()
        self._reset_verify_stack.setStyleSheet("background: transparent;")

        # Sub-page 0: TOTP
        totp_sub = QWidget()
        totp_sub.setStyleSheet("background: transparent;")
        tsub_l = QVBoxLayout(totp_sub)
        tsub_l.setContentsMargins(0, 0, 0, 0)
        tsub_l.setSpacing(4)
        desc_totp = QLabel("Podaj aktualny 6-cyfrowy kod\nz aplikacji authenticator.")
        desc_totp.setWordWrap(True)
        desc_totp.setStyleSheet("color: #888; font-size: 12px; margin-bottom: 4px;")
        tsub_l.addWidget(desc_totp)
        self._reset_totp_e = QLineEdit()
        self._reset_totp_e.setPlaceholderText("000000")
        self._reset_totp_e.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._reset_totp_e.setFixedHeight(48)
        self._reset_totp_e.setMaxLength(6)
        self._reset_totp_e.setStyleSheet(
            "font-size: 22px; border-radius: 8px; letter-spacing: 8px;"
            "background: #252525; color: white; border: 1px solid #333;"
        )
        self._reset_totp_e.returnPressed.connect(self._on_reset_step2)
        tsub_l.addWidget(self._reset_totp_e)
        tsub_l.addStretch()

        # Sub-page 1: Recovery key
        rec_sub = QWidget()
        rec_sub.setStyleSheet("background: transparent;")
        rsub_l = QVBoxLayout(rec_sub)
        rsub_l.setContentsMargins(0, 0, 0, 0)
        rsub_l.setSpacing(4)
        desc_rec = QLabel("Wpisz klucz recovery zapisany przy konfiguracji konta.\nFormat: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX")
        desc_rec.setWordWrap(True)
        desc_rec.setStyleSheet("color: #888; font-size: 12px; margin-bottom: 4px;")
        rsub_l.addWidget(desc_rec)
        self._reset_rec_e = QLineEdit()
        self._reset_rec_e.setPlaceholderText("XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX")
        self._reset_rec_e.setFixedHeight(42)
        self._reset_rec_e.setStyleSheet(
            "font-size: 13px; border-radius: 8px; letter-spacing: 2px;"
            "background: #252525; color: white; border: 1px solid #333; padding: 0 10px;"
        )
        self._reset_rec_e.returnPressed.connect(self._on_reset_step2)
        rsub_l.addWidget(self._reset_rec_e)
        rsub_l.addStretch()

        self._reset_verify_stack.addWidget(totp_sub)
        self._reset_verify_stack.addWidget(rec_sub)
        s2l.addWidget(self._reset_verify_stack)

        self._reset_step2_err = QLabel("")
        self._reset_step2_err.setStyleSheet("color: #e53e3e; font-size: 11px;")
        self._reset_step2_err.setVisible(False)
        s2l.addWidget(self._reset_step2_err)
        s2l.addSpacing(8)
        self._make_btn(s2l, "Zweryfikuj →", self._on_reset_step2, primary=True)
        back2 = QPushButton("← Wróć")
        back2.setFixedHeight(36)
        back2.setStyleSheet(
            "QPushButton { background: transparent; border: none; "
            "color: #666; font-size: 12px; }"
            "QPushButton:hover { color: #aaa; }"
        )
        back2.clicked.connect(lambda: self._reset_stack.setCurrentIndex(0))
        s2l.addWidget(back2, alignment=Qt.AlignmentFlag.AlignCenter)
        s2l.addStretch()

        # ── Krok 3: nowe hasło ─────────────────────────────────────────
        step3 = QWidget()
        step3.setStyleSheet("background: transparent;")
        s3l = QVBoxLayout(step3)
        s3l.setSpacing(4)

        h3 = QLabel("Nowe hasło masterowe")
        h3.setStyleSheet("font-size: 15px; font-weight: bold; margin-bottom: 4px;")
        s3l.addWidget(h3)

        desc3 = QLabel("Tożsamość potwierdzona.\nUstaw nowe hasło masterowe.")
        desc3.setWordWrap(True)
        desc3.setStyleSheet("color: #4caf50; font-size: 12px; margin-bottom: 8px;")
        s3l.addWidget(desc3)

        self._reset_pwd1_e  = self._make_field(s3l, "Nowe hasło", "Min. 8 znaków...", secret=True)
        self._reset_pwd2_e  = self._make_field(s3l, "Powtórz hasło", "Powtórz nowe hasło...", secret=True)
        self._reset_pwd2_e.returnPressed.connect(self._on_reset_step3)

        # Pasek siły
        self._reset_str_bar = QProgressBar()
        self._reset_str_bar.setRange(0, 100)
        self._reset_str_bar.setValue(0)
        self._reset_str_bar.setFixedHeight(6)
        self._reset_str_bar.setTextVisible(False)
        self._reset_str_bar.setStyleSheet(
            "QProgressBar { background: #3a3a3a; border-radius: 3px; border: none; }"
            "QProgressBar::chunk { background: #718096; }"
        )
        s3l.addWidget(self._reset_str_bar)
        self._reset_str_lbl = QLabel("")
        self._reset_str_lbl.setStyleSheet("font-size: 11px; color: #888;")
        s3l.addWidget(self._reset_str_lbl)
        self._reset_pwd1_e.textChanged.connect(self._update_reset_strength)

        self._reset_step3_err = QLabel("")
        self._reset_step3_err.setStyleSheet("color: #e53e3e; font-size: 11px;")
        self._reset_step3_err.setVisible(False)
        s3l.addWidget(self._reset_step3_err)
        s3l.addSpacing(8)
        self._reset_btn = self._make_btn(s3l, "Zmień hasło i zaloguj", self._on_reset_step3, primary=True)
        s3l.addStretch()

        for step in (step1, step2, step3):
            self._reset_stack.addWidget(step)

        return page

    def _update_reset_strength(self, text: str):
        if not text:
            self._reset_str_bar.setValue(0)
            self._reset_str_lbl.setText("")
            return
        sc = check_strength(text)
        color = sc.get("color", "#718096")
        self._reset_str_bar.setStyleSheet(
            "QProgressBar { background: #3a3a3a; border-radius: 3px; border: none; }"
            f"QProgressBar::chunk {{ background: {color}; }}"
        )
        self._reset_str_bar.setValue(sc.get("percent", 0))
        self._reset_str_lbl.setText(sc.get("label", ""))
        self._reset_str_lbl.setStyleSheet(f"font-size: 11px; color: {color};")

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

    def _show_reset(self):
        self._reset_user_e.setText(self._login_user.text())
        self._reset_stack.setCurrentIndex(0)
        self._reset_step1_err.setVisible(False)
        self._subtitle.setText("Resetuj hasło masterowe")
        self._stack.setCurrentIndex(5)
        QTimer.singleShot(50, self._reset_user_e.setFocus)

    # ── Reset masterhasła — logika kroków ────────────────────────────

    def _switch_reset_tab(self, mode: str):
        if mode == "totp":
            self._reset_tab_totp.setChecked(True)
            self._reset_tab_rec.setChecked(False)
            self._reset_verify_stack.setCurrentIndex(0)
            QTimer.singleShot(50, self._reset_totp_e.setFocus)
        else:
            self._reset_tab_totp.setChecked(False)
            self._reset_tab_rec.setChecked(True)
            self._reset_verify_stack.setCurrentIndex(1)
            QTimer.singleShot(50, self._reset_rec_e.setFocus)

    def _on_reset_step1(self):
        username = self._reset_user_e.text().strip()
        if not username:
            self._reset_step1_err.setText("Podaj nazwę użytkownika.")
            self._reset_step1_err.setVisible(True)
            return
        user = self.db.get_user(username)
        if not user:
            self._reset_step1_err.setText("Nie znaleziono użytkownika.")
            self._reset_step1_err.setVisible(True)
            return
        has_totp     = bool(user.totp_secret)
        has_recovery = self.db.has_recovery_key(user)
        if not has_totp and not has_recovery:
            self._reset_step1_err.setText(
                "To konto nie ma skonfigurowanego 2FA ani klucza recovery.\n"
                "Reset hasła jest niemożliwy — skonfiguruj jedną z tych\n"
                "metod weryfikacji zanim zapomnisz hasła."
            )
            self._reset_step1_err.setVisible(True)
            return
        self._reset_pending_user = user
        self._reset_step1_err.setVisible(False)
        self._reset_totp_e.clear()
        self._reset_rec_e.clear()
        self._reset_step2_err.setVisible(False)
        # Pokaż/ukryj zakładki zależnie od dostępnych metod
        self._reset_tab_totp.setVisible(has_totp)
        self._reset_tab_rec.setVisible(has_recovery)
        if has_totp:
            self._switch_reset_tab("totp")
        else:
            self._switch_reset_tab("recovery")
        self._reset_stack.setCurrentIndex(1)

    def _on_reset_step2(self):
        user = self._reset_pending_user
        using_recovery = self._reset_verify_stack.currentIndex() == 1

        if using_recovery:
            phrase = self._reset_rec_e.text().strip()
            if not phrase:
                self._reset_step2_err.setText("Wpisz klucz recovery.")
                self._reset_step2_err.setVisible(True)
                return
            from utils.recovery import decrypt_with_recovery
            old_master = decrypt_with_recovery(
                user.recovery_encrypted_master, phrase, user.recovery_salt
            )
            if old_master is None:
                self._reset_step2_err.setText("Nieprawidłowy klucz recovery.")
                self._reset_step2_err.setVisible(True)
                shake(self._reset_rec_e)
                return
            self._reset_verified_phrase = phrase
        else:
            code = self._reset_totp_e.text().strip()
            if len(code) != 6 or not code.isdigit():
                self._reset_step2_err.setText("Kod musi mieć dokładnie 6 cyfr.")
                self._reset_step2_err.setVisible(True)
                return
            if not TOTPManager(secret=user.totp_secret).verify(code):
                self._reset_step2_err.setText("Nieprawidłowy kod 2FA.")
                self._reset_step2_err.setVisible(True)
                shake(self._reset_totp_e)
                self._reset_totp_e.clear()
                return
            self._reset_verified_phrase = None

        self._reset_step2_err.setVisible(False)
        self._reset_using_recovery = using_recovery
        self._reset_pwd1_e.clear()
        self._reset_pwd2_e.clear()
        self._reset_step3_err.setVisible(False)
        self._reset_stack.setCurrentIndex(2)
        QTimer.singleShot(50, self._reset_pwd1_e.setFocus)

    def _on_reset_step3(self):
        pwd1 = self._reset_pwd1_e.text()
        pwd2 = self._reset_pwd2_e.text()
        if len(pwd1) < 8:
            self._reset_step3_err.setText("Hasło musi mieć co najmniej 8 znaków.")
            self._reset_step3_err.setVisible(True)
            return
        if pwd1 != pwd2:
            self._reset_step3_err.setText("Hasła nie są identyczne.")
            self._reset_step3_err.setVisible(True)
            shake(self._reset_pwd2_e)
            return
        self._reset_btn.setEnabled(False)
        self._reset_btn.setText("Zmieniam hasło…")
        user            = self._reset_pending_user
        using_recovery  = getattr(self, "_reset_using_recovery", False)
        phrase          = getattr(self, "_reset_verified_phrase", None)

        def _do_reset():
            try:
                if using_recovery and phrase:
                    # Recovery: mamy stare masterhasło → pełne re-szyfrowanie
                    new_crypto = self.db.reset_with_recovery_key(user, phrase, pwd1)
                    data_kept  = True
                else:
                    # TOTP: nie mamy starego klucza → usuwamy wpisy
                    from database.models import Password, PasswordHistory
                    from core.crypto import generate_salt, hash_master_password, KDF_ARGON2ID
                    new_salt   = generate_salt(32)
                    new_crypto = CryptoManager(pwd1, new_salt, kdf_version=KDF_ARGON2ID)
                    self.db.session.query(PasswordHistory).filter(
                        PasswordHistory.password_id.in_(
                            self.db.session.query(Password.id).filter_by(user_id=user.id)
                        )
                    ).delete(synchronize_session=False)
                    self.db.session.query(Password).filter_by(user_id=user.id).delete()
                    user.master_password_hash      = hash_master_password(pwd1, version=KDF_ARGON2ID)
                    user.salt                      = new_salt
                    user.kdf_version               = KDF_ARGON2ID
                    user.recovery_salt             = None
                    user.recovery_encrypted_master = None
                    self.db.session.commit()
                    data_kept = False

                self.crypto      = new_crypto
                self.logged_user = user
                QTimer.singleShot(0, lambda: self._after_reset_success(data_kept))
            except Exception as e:
                self.db.session.rollback()
                QTimer.singleShot(0, lambda: self._after_reset_error(str(e)))

        threading.Thread(target=_do_reset, daemon=True).start()

    def _after_reset_success(self, data_kept: bool):
        self._reset_btn.setEnabled(True)
        self._reset_btn.setText("Zmień hasło i zaloguj")
        if data_kept:
            msg = "Hasło masterowe zostało zmienione.\nWszystkie hasła zostały zachowane i re-zaszyfrowane."
        else:
            msg = ("Hasło masterowe zostało zmienione.\n\n"
                   "⚠️ Istniejące hasła zostały usunięte — niemożliwe było\n"
                   "ich re-szyfrowanie bez klucza recovery.")
        show_success("Hasło zmienione", msg, parent=self)
        self._complete_login(self.logged_user, self._reset_pwd1_e.text())

    def _after_reset_error(self, msg: str):
        self._reset_btn.setEnabled(True)
        self._reset_btn.setText("Zmień hasło i zaloguj")
        self._reset_step3_err.setText(f"Błąd: {msg}")
        self._reset_step3_err.setVisible(True)

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

    # ── Lockout ───────────────────────────────────────────────────────

    _MAX_LOGIN_ATTEMPTS = 5
    _MAX_TOTP_ATTEMPTS  = 3
    # Progi lockoutu: po N próbach → X sekund blokady
    _LOCKOUT_STEPS = [(5, 30), (10, 300), (15, None)]  # (próby, sekundy | None=stały)

    def _is_locked_out(self) -> bool:
        return time.monotonic() < self._lockout_until

    def _remaining_lockout(self) -> int:
        return max(0, int(self._lockout_until - time.monotonic()))

    def _apply_lockout(self, attempts: int):
        for threshold, secs in self._LOCKOUT_STEPS:
            if attempts >= threshold:
                duration = secs if secs is not None else 9999999
                self._lockout_until = time.monotonic() + duration
        self._lockout_timer.start()
        self._update_lockout_ui()

    def _tick_lockout(self):
        remaining = self._remaining_lockout()
        self._update_lockout_ui()
        if remaining == 0:
            self._lockout_timer.stop()
            self._update_lockout_ui()

    def _update_lockout_ui(self):
        remaining = self._remaining_lockout()
        locked = remaining > 0

        # Przycisk logowania
        if hasattr(self, "_btn_login"):
            self._btn_login.setEnabled(not locked)

        # Label na stronie logowania
        if hasattr(self, "_lockout_lbl"):
            if locked:
                self._lockout_lbl.setText(f"🔒 Zbyt wiele prób — odblokowanie za {remaining}s")
                self._lockout_lbl.setVisible(True)
            elif self._login_attempts > 0:
                left = self._MAX_LOGIN_ATTEMPTS - self._login_attempts
                self._lockout_lbl.setText(f"Pozostało prób: {left}")
                self._lockout_lbl.setVisible(True)
            else:
                self._lockout_lbl.setVisible(False)

        # Label na stronie TOTP
        if hasattr(self, "_totp_lockout_lbl"):
            if locked:
                self._totp_lockout_lbl.setText(f"🔒 Zbyt wiele prób — odblokowanie za {remaining}s")
                self._totp_lockout_lbl.setVisible(True)
            elif self._totp_attempts > 0:
                left = self._MAX_TOTP_ATTEMPTS - self._totp_attempts
                self._totp_lockout_lbl.setText(f"Pozostało prób: {left}")
                self._totp_lockout_lbl.setVisible(True)
            else:
                self._totp_lockout_lbl.setVisible(False)

    # ── Logowanie ─────────────────────────────────────────────────────

    def _on_login(self):
        if self._is_locked_out():
            shake(self)
            return

        username = self._login_user.text().strip()
        password = self._login_pass.text()
        if not username or not password:
            show_error("Błąd", "Wypełnij wszystkie pola!", parent=self)
            return

        user = self.db.login_user(username, password)
        if not user:
            self._login_attempts += 1
            self._apply_lockout(self._login_attempts)
            shake(self)
            remaining_attempts = self._MAX_LOGIN_ATTEMPTS - self._login_attempts
            if self._is_locked_out():
                msg = f"Zbyt wiele błędnych prób.\nOdblokowanie za {self._remaining_lockout()}s."
            elif remaining_attempts <= 2:
                msg = f"Nieprawidłowe hasło.\nPozostało prób: {remaining_attempts}."
            else:
                msg = "Nieprawidłowa nazwa użytkownika lub hasło."
            show_error("Błąd logowania", msg, parent=self)
            return

        # Udane logowanie — resetuj licznik
        self._login_attempts = 0
        self._update_lockout_ui()

        if user.totp_secret:
            self._temp_password = password
            self._show_2fa(user)
        else:
            self._complete_login(user, password)

    def _on_verify_2fa(self):
        if self._is_locked_out():
            shake(self)
            return

        code = self._totp_entry.text().strip()
        user = self._pending_user
        totp = TOTPManager(secret=user.totp_secret)
        if not totp.verify(code):
            self._totp_attempts += 1
            self._apply_lockout(self._totp_attempts)
            shake(self)
            remaining_attempts = self._MAX_TOTP_ATTEMPTS - self._totp_attempts
            if self._is_locked_out():
                msg = f"Zbyt wiele błędnych prób.\nOdblokowanie za {self._remaining_lockout()}s."
            elif remaining_attempts <= 1:
                msg = f"Nieprawidłowy kod!\nPozostało prób: {remaining_attempts}."
            else:
                msg = "Nieprawidłowy kod!\n\nSprawdź czy zegar systemowy jest zsynchronizowany."
            show_error("Błąd 2FA", msg, parent=self)
            self._totp_entry.clear()
            return

        # Udana weryfikacja — resetuj licznik
        self._totp_attempts = 0
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
        from core.crypto import KDF_PBKDF2
        kdf_v = user.kdf_version if user.kdf_version is not None else KDF_PBKDF2
        self.crypto = CryptoManager(master_password, user.salt, kdf_version=kdf_v)
        self.db.log_event(user, "login_ok")
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
