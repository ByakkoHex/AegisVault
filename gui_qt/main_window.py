"""
main_window.py — Główne okno AegisVault (PyQt6)
================================================
Struktura:
  Topbar (logo, tytuł, breadcrumb, szukaj, sync dot, update btn, theme, user, score ring)
  Separator (2px animowany gradient)
  Body:
    Sidebar (175px) — kategorie, specjalne, backup, generator
    Content — toolbar + QScrollArea z PasswordRowWidget

Powiązane klasy:
  PasswordFormDialog  — dialog dodawania / edycji hasła
  CategoryDialog      — nowa kategoria (emoji + kolor)
  TrashDialog         — okno kosza
  MainWindow          — okno główne
"""

import os
import platform
import threading
import time
import webbrowser
import pyperclip
from datetime import datetime, timezone
from PIL import Image

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QLineEdit, QScrollArea, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTextEdit, QComboBox, QSlider, QCheckBox, QDialog,
    QSizePolicy, QStackedWidget, QProgressBar, QFileDialog,
    QButtonGroup, QApplication,
)
from PyQt6.QtCore import (
    Qt, QTimer, QSize, QRect, pyqtSignal,
    QPropertyAnimation, QEasingCurve,
)
from PyQt6.QtGui import (
    QColor, QFont, QPixmap, QImage, QIcon, QPainter,
    QKeySequence, QShortcut,
)

from database.db_manager import DatabaseManager
from database.models import DEFAULT_CATEGORIES
from core.crypto import CryptoManager, generate_password, verify_master_password
from utils.password_strength import check_strength, _build_checklist
from utils.prefs_manager import PrefsManager, THEMES
from utils.sync_client import SyncClient
from utils import security_score as _sec_score
from utils.updater import check_for_update
import pyotp
import utils.windows_hello as wh
import utils.autostart as autostart
from utils.logger import get_logger

from gui_qt.gradient       import AnimatedGradientWidget
from gui_qt.hex_background import HexBackground
from gui_qt.score_ring     import AnimatedScoreRing
from gui_qt.animations     import shake, fade_in
from gui_qt.dialogs        import show_error, show_info, show_success, ask_yes_no
from gui_qt.toast          import ToastManager
from gui_qt.app            import apply_theme, get_app
from gui_qt.style          import build_qss

logger = get_logger(__name__)

_ON_WINDOWS = platform.system() == "Windows"
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
_ARROW_SVG  = os.path.normpath(os.path.join(_ASSETS_DIR, "arrow_down.svg")).replace("\\", "/")

# ── Kategorie domyślne ────────────────────────────────────────────────
CATEGORIES = {
    "Wszystkie":    {"icon": "📋", "color": None},
    "Social Media": {"icon": "💬", "color": "#E53E3E"},
    "Praca":        {"icon": "💼", "color": "#D69E2E"},
    "Bankowość":    {"icon": "🏦", "color": "#38A169"},
    "Rozrywka":     {"icon": "🎮", "color": "#805AD5"},
    "Inne":         {"icon": "📁", "color": "#718096"},
    "Wygasające":   {"icon": "⏰", "color": None},
    "Notatki":      {"icon": "📝", "color": "#5a67d8"},
}

_EMOJI_PICKER = [
    "🏠", "💼", "🏦", "🎮", "🎵", "📱", "💻", "🛒",
    "✈️", "🏋️", "📚", "🔐", "🌐", "💰", "🎯", "🎨",
    "🔧", "🏥", "🍕", "🚗", "👤", "❤️", "⭐", "🔑",
    "📧", "🛡️", "🎁", "📷", "🎓", "🏆", "🌿", "🔬",
]
_CAT_PRESET_COLORS = [
    "#E53E3E", "#DD6B20", "#D69E2E", "#38A169",
    "#3182CE", "#0F52BA", "#805AD5", "#D53F8C",
    "#2D3748", "#718096",
]


# ── Helpers ───────────────────────────────────────────────────────────

def _blend(accent: str, base: str, alpha: float) -> str:
    def _p(c):
        c = c.lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    ar, ag, ab = _p(accent)
    br, bg, bb = _p(base)
    return (f"#{int(br+(ar-br)*alpha):02x}"
            f"{int(bg+(ag-bg)*alpha):02x}"
            f"{int(bb+(ab-bb)*alpha):02x}")


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qi = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qi)


def _accent_icon(accent: str, size: int = 28) -> QPixmap | None:
    """Ładuje icon.png i koloryzuje wszystkie nieprzezroczyste piksele kolorem akcentu."""
    icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png")
    try:
        img = Image.open(icon_path).convert("RGBA").resize((size, size), Image.LANCZOS)
        r, g, b = int(accent[1:3], 16), int(accent[3:5], 16), int(accent[5:7], 16)
        px = img.load()
        for y in range(img.height):
            for x in range(img.width):
                _, _, _, a = px[x, y]
                if a > 10:
                    px[x, y] = (r, g, b, a)
        return _pil_to_pixmap(img)
    except Exception:
        return None


def _score_color(score: int) -> str:
    if score >= 4:   return "#4caf50"
    elif score >= 2: return "#f0a500"
    return "#e05252"


# ══════════════════════════════════════════════════════════════════════
# PasswordFormDialog — dodaj / edytuj hasło
# ══════════════════════════════════════════════════════════════════════

class PasswordFormDialog(QDialog):
    def __init__(self, parent, db, crypto, user, entry=None):
        super().__init__(parent)
        self.db     = db
        self.crypto = crypto
        self.user   = user
        self.entry  = entry
        self.result = False

        self.setWindowTitle("Edytuj hasło" if entry else "Dodaj nowe hasło")
        self.setFixedWidth(480)
        self.setMinimumHeight(560)
        _p    = PrefsManager()
        accent = _p.get_accent()
        dark   = (_p.get("appearance_mode") or "dark").lower() != "light"

        bg        = "#161616" if dark else "#f2f2f2"
        bg_rgba   = "rgba(18, 18, 18, 0.92)"  if dark else "rgba(240, 240, 240, 0.92)"
        bg_input  = "#2e2e2e" if dark else "#ffffff"
        bdr       = "#525252" if dark else "#c0c0c0"
        text_col  = "#f0f0f0" if dark else "#1a1a1a"
        lbl_col   = "#aaaaaa" if dark else "#555555"

        # Zapisujemy jako atrybuty, żeby _field() mógł z nich korzystać
        self._fi_bg   = bg_input
        self._fi_bdr  = bdr
        self._fi_text = text_col
        self._fi_acc  = accent

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.setStyleSheet(f"""
            QDialog {{ background: {bg_rgba}; color: {text_col}; border-radius: 14px; }}
            QLabel  {{ color: {text_col}; font-size: 13px; background: transparent; border: none; }}
            QLabel[role="field-label"] {{
                color: {lbl_col}; font-size: 11px; font-weight: 600;
                text-transform: uppercase; letter-spacing: 0.5px;
            }}
            QLineEdit, QTextEdit {{
                background: {bg_input}; color: {text_col};
                border: 1.5px solid {bdr}; border-radius: 8px;
                padding: 8px 12px; font-size: 13px;
            }}
            QLineEdit:hover, QTextEdit:hover {{
                border-color: {'#888888' if dark else '#909090'};
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border-color: {accent}; border-width: 2px;
            }}
            QLineEdit:disabled {{ color: {'#555' if dark else '#aaa'}; }}
            QComboBox {{
                background: {bg_input}; color: {text_col};
                border: 1.5px solid {bdr}; border-radius: 8px;
                padding: 8px 12px; font-size: 13px;
            }}
            QComboBox:hover {{ border-color: {'#888888' if dark else '#909090'}; }}
            QComboBox:focus {{ border-color: {accent}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: {bg_input}; color: {text_col};
                selection-background-color: {accent};
                border: 1px solid {bdr}; border-radius: 6px;
            }}
            QScrollBar:vertical {{ background: transparent; width: 6px; }}
            QScrollBar::handle:vertical {{
                background: {'#444' if dark else '#ccc'}; border-radius: 3px; min-height: 20px;
            }}
        """)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(20, 16, 20, 16)
        vl.setSpacing(8)

        title_lbl = QLabel("Edytuj hasło" if entry else "Dodaj hasło")
        title_lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {text_col};")
        vl.addWidget(title_lbl)

        sep = AnimatedGradientWidget(accent=accent, base=bg, direction="h", anim_mode="slide")
        sep.setFixedHeight(2)
        sep.start_animation()
        vl.addWidget(sep)

        # Scroll area dla pól
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.viewport().setStyleSheet("background: transparent;")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        fl = QVBoxLayout(inner)
        fl.setSpacing(6)

        # Pola
        self._title_e    = self._field(fl, "Nazwa serwisu", "np. Gmail, GitHub...")
        self._username_e = self._field(fl, "Login / Email", "Login lub email...")

        _lbl_col  = "#aaaaaa" if dark else "#555555"
        _bar_bg   = "#3a3a3a" if dark else "#e0e0e0"
        _eye_bdr  = "#525252" if dark else "#c0c0c0"

        def _section_label(text):
            l = QLabel(text.upper())
            l.setProperty("role", "field-label")
            l.setStyleSheet(
                f"color: {_lbl_col}; font-size: 11px; font-weight: 600; "
                "background: transparent; border: none;"
            )
            return l

        fl.addWidget(_section_label("Hasło"))
        pwd_row = QWidget()
        pwd_row.setStyleSheet("background: transparent;")
        prl = QHBoxLayout(pwd_row)
        prl.setContentsMargins(0, 0, 0, 0)
        prl.setSpacing(6)
        self._pwd_e = QLineEdit()
        self._pwd_e.setEchoMode(QLineEdit.EchoMode.Password)
        self._pwd_e.setPlaceholderText("Hasło...")
        self._pwd_e.setFixedHeight(40)
        self._pwd_e.setStyleSheet(
            f"background: {bg_input}; color: {text_col}; "
            f"border: 1.5px solid {bdr}; border-radius: 8px; "
            "padding: 8px 12px; font-size: 13px;"
        )
        prl.addWidget(self._pwd_e)
        eye_btn = QPushButton("👁")
        eye_btn.setFixedSize(40, 40)
        eye_btn.setStyleSheet(
            f"background: transparent; border: 1.5px solid {_eye_bdr}; "
            "border-radius: 8px; font-size: 15px; min-height: 0; padding: 0;"
        )
        eye_btn.clicked.connect(self._toggle_pwd)
        prl.addWidget(eye_btn)
        fl.addWidget(pwd_row)

        # Generuj + HIBP
        action_row = QWidget()
        action_row.setStyleSheet("background: transparent;")
        arl = QHBoxLayout(action_row)
        arl.setContentsMargins(0, 2, 0, 2)
        arl.setSpacing(8)
        gen_btn = QPushButton("⚡ Generuj")
        gen_btn.setFixedHeight(38)
        gen_btn.setStyleSheet(
            f"background: {'#1a3a5c' if dark else '#ddeeff'}; "
            f"color: {'#7ab8f5' if dark else '#1a5080'}; "
            "border-radius: 8px; font-size: 13px; font-weight: bold; "
            "padding: 0 14px; min-height: 0;"
        )
        gen_btn.clicked.connect(self._generate)
        arl.addWidget(gen_btn)
        hibp_btn = QPushButton("🔍 Sprawdź wyciek")
        hibp_btn.setFixedHeight(38)
        hibp_btn.setStyleSheet(
            f"background: {'#2a1a00' if dark else '#fff3e0'}; "
            f"color: {'#ffb74d' if dark else '#8a5000'}; "
            "border-radius: 8px; font-size: 13px; font-weight: bold; "
            "padding: 0 14px; min-height: 0;"
        )
        hibp_btn.clicked.connect(self._check_hibp)
        arl.addWidget(hibp_btn)
        arl.addStretch()
        fl.addWidget(action_row)

        self._hibp_lbl = QLabel("")
        self._hibp_lbl.setStyleSheet("font-size: 11px; background: transparent; border: none;")
        fl.addWidget(self._hibp_lbl)

        # Pasek siły
        self._str_bar = QProgressBar()
        self._str_bar.setRange(0, 100)
        self._str_bar.setValue(0)
        self._str_bar.setFixedHeight(6)
        self._str_bar.setTextVisible(False)
        self._str_bar.setStyleSheet(
            f"QProgressBar {{ background: {_bar_bg}; border-radius: 3px; border: none; }}"
            "QProgressBar::chunk { background: #718096; }"
        )
        fl.addWidget(self._str_bar)

        self._str_lbl = QLabel("")
        self._str_lbl.setStyleSheet(f"font-size: 11px; color: {'#888' if dark else '#666'}; background: transparent; border: none;")
        fl.addWidget(self._str_lbl)

        self._pwd_e.textChanged.connect(self._update_strength)

        self._url_e = self._field(fl, "URL (opcjonalnie)", "https://...")

        fl.addWidget(_section_label("Kategoria"))
        self._cat_combo = QComboBox()
        all_cats = db.get_all_categories(user)
        self._cat_combo.addItems(all_cats)
        self._cat_combo.setFixedHeight(34)
        self._cat_combo.setStyleSheet(
            f"QComboBox {{ background: {bg_input}; color: {text_col}; "
            f"border: 1.5px solid {bdr}; border-radius: 8px; "
            f"padding: 4px 12px; font-size: 13px; }}"
            f"QComboBox::drop-down {{ border: none; width: 28px; subcontrol-origin: padding; subcontrol-position: right center; }}"
            f"QComboBox::down-arrow {{ image: url({_ARROW_SVG}); width: 10px; height: 6px; }}"
            f"QComboBox QAbstractItemView {{ background: {bg_input}; color: {text_col}; "
            f"selection-background-color: {accent}; border: 1px solid {bdr}; border-radius: 6px; }}"
        )
        fl.addWidget(self._cat_combo)

        self._expires_e = self._field(fl, "Data wygaśnięcia (opcjonalnie)", "2026-12-31")

        fl.addWidget(_section_label("Notatki"))
        self._notes_e = QTextEdit()
        self._notes_e.setFixedHeight(80)
        self._notes_e.setStyleSheet(
            f"background: {bg_input}; color: {text_col}; "
            f"border: 1.5px solid {bdr}; border-radius: 8px; "
            "padding: 6px 10px; font-size: 13px;"
        )
        fl.addWidget(self._notes_e)

        # OTP Secret
        fl.addWidget(_section_label("Klucz OTP (opcjonalnie)"))
        otp_row = QWidget()
        otp_row.setStyleSheet("background: transparent;")
        otprl = QHBoxLayout(otp_row)
        otprl.setContentsMargins(0, 0, 0, 0)
        otprl.setSpacing(6)
        self._otp_e = QLineEdit()
        self._otp_e.setPlaceholderText("Sekret Base32 lub otpauth://... URI")
        self._otp_e.setFixedHeight(40)
        self._otp_e.setStyleSheet(
            f"background: {bg_input}; color: {text_col}; "
            f"border: 1.5px solid {bdr}; border-radius: 8px; "
            "padding: 8px 12px; font-size: 13px;"
        )
        otprl.addWidget(self._otp_e)
        self._otp_preview_lbl = QLabel("")
        self._otp_preview_lbl.setFixedWidth(68)
        self._otp_preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._otp_preview_lbl.setStyleSheet(
            f"background: {'#1a2a1a' if dark else '#d4f0d4'}; "
            f"color: {'#7ec87e' if dark else '#2a6e2a'}; "
            "border-radius: 8px; font-size: 14px; font-weight: bold; border: none;"
        )
        otprl.addWidget(self._otp_preview_lbl)
        fl.addWidget(otp_row)
        self._otp_e.textChanged.connect(self._update_otp_preview)

        fl.addStretch()
        scroll.setWidget(inner)
        vl.addWidget(scroll)

        # Przyciski dołu
        btn_row = QWidget()
        brl = QHBoxLayout(btn_row)
        brl.setContentsMargins(0, 4, 0, 0)
        cancel = QPushButton("Anuluj")
        cancel.setFixedHeight(42)
        cancel.setStyleSheet(
            f"background: transparent; border: 1.5px solid {bdr}; "
            f"color: {lbl_col}; border-radius: 10px; font-size: 13px;"
        )
        cancel.clicked.connect(self.reject)
        brl.addWidget(cancel)
        save_btn = QPushButton("Zapisz")
        save_btn.setFixedHeight(42)
        save_btn.setStyleSheet(f"background: {accent}; color: white; border-radius: 10px; font-size: 13px; font-weight: bold;")
        save_btn.clicked.connect(self._save)
        brl.addWidget(save_btn)
        vl.addWidget(btn_row)

        # Wypełnij jeśli edycja
        if entry:
            self._title_e.setText(entry.title or "")
            self._username_e.setText(entry.username or "")
            self._url_e.setText(entry.url or "")
            self._notes_e.setPlainText(entry.notes or "")
            self._pwd_e.setText(db.decrypt_password(entry, crypto))
            idx = self._cat_combo.findText(entry.category or "Inne")
            if idx >= 0:
                self._cat_combo.setCurrentIndex(idx)
            if entry.expires_at:
                self._expires_e.setText(entry.expires_at.strftime("%Y-%m-%d"))
            if entry.otp_secret:
                self._otp_e.setText(entry.otp_secret)

        # Hex background — drawn behind all widgets
        self._hex = HexBackground(self, hex_size=32, glow_max=2, glow_interval_ms=2000)
        self._hex.setGeometry(0, 0, self.width(), self.height())
        self._hex.lower()
        QTimer.singleShot(0, lambda: self._hex and (
            self._hex.setGeometry(0, 0, self.width(), self.height()),
            self._hex.lower()
        ))

        QTimer.singleShot(200, self._title_e.setFocus)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_hex'):
            self._hex.setGeometry(0, 0, self.width(), self.height())
            self._hex.lower()

    def _field(self, layout, label, placeholder):
        lbl = QLabel(label.upper())
        lbl.setProperty("role", "field-label")
        lbl.style().unpolish(lbl)
        lbl.style().polish(lbl)
        layout.addWidget(lbl)
        e = QLineEdit()
        e.setPlaceholderText(placeholder)
        e.setFixedHeight(40)
        e.setStyleSheet(
            f"background: {self._fi_bg}; color: {self._fi_text}; "
            f"border: 1.5px solid {self._fi_bdr}; border-radius: 8px; "
            "padding: 8px 12px; font-size: 13px;"
        )
        layout.addWidget(e)
        return e

    def _update_otp_preview(self, text):
        """Pokazuje podgląd kodu TOTP na żywo obok pola OTP."""
        from utils.import_manager import _parse_otp_secret
        secret = _parse_otp_secret(text.strip())
        if not secret:
            self._otp_preview_lbl.setText("")
            return
        try:
            code = pyotp.TOTP(secret).now()
            self._otp_preview_lbl.setText(code)
        except Exception:
            self._otp_preview_lbl.setText("")

    def _toggle_pwd(self):
        if self._pwd_e.echoMode() == QLineEdit.EchoMode.Password:
            self._pwd_e.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self._pwd_e.setEchoMode(QLineEdit.EchoMode.Password)

    def _update_strength(self):
        pwd = self._pwd_e.text()
        if not pwd:
            self._str_bar.setValue(0)
            self._str_lbl.setText("")
            return
        sc      = check_strength(pwd)
        percent = sc.get("percent", 0)
        label   = sc.get("label", "")
        color   = sc.get("color", "#718096")
        self._str_bar.setStyleSheet(
            f"QProgressBar {{ background: {'#3a3a3a'}; border-radius: 3px; border: none; }}"
            f"QProgressBar::chunk {{ background: {color}; }}"
        )
        self._str_bar.setValue(percent)
        self._str_lbl.setText(label)
        self._str_lbl.setStyleSheet(f"font-size: 11px; color: {color}; background: transparent; border: none;")

    def _generate(self):
        pwd = generate_password(length=20)
        self._pwd_e.setText(pwd)
        self._pwd_e.setEchoMode(QLineEdit.EchoMode.Normal)
        try:
            pyperclip.copy(pwd)
        except Exception:
            pass
        show_success("Generator", f"Wygenerowano i skopiowano!\n\n{pwd}", parent=self)

    def _check_hibp(self):
        pwd = self._pwd_e.text()
        if not pwd:
            self._hibp_lbl.setText("Najpierw wpisz hasło.")
            return
        self._hibp_lbl.setText("Sprawdzanie...")

        def _run():
            from utils.hibp import check_password
            breached, count = check_password(pwd)
            if count == -1:
                msg, color = "Brak połączenia z HIBP.", "#f0a500"
            elif breached:
                msg, color = f"Hasło wyciekło {count:,} razy!", "#e05252"
            else:
                msg, color = "Nie znaleziono w wyciekach.", "#4caf50"
            QTimer.singleShot(0, lambda: (
                self._hibp_lbl.setText(msg),
                self._hibp_lbl.setStyleSheet(f"font-size: 11px; color: {color}; background: transparent; border: none;"),
            ))

        threading.Thread(target=_run, daemon=True).start()

    def _save(self):
        title    = self._title_e.text().strip()
        username = self._username_e.text().strip()
        password = self._pwd_e.text()
        url      = self._url_e.text().strip()
        notes    = self._notes_e.toPlainText().strip()
        category = self._cat_combo.currentText()

        if not title:
            show_error("Błąd", "Nazwa serwisu jest wymagana!", parent=self)
            return
        if not password:
            show_error("Błąd", "Hasło jest wymagane!", parent=self)
            return

        expires = None
        raw_exp = self._expires_e.text().strip()
        if raw_exp:
            for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                try:
                    expires = datetime.strptime(raw_exp, fmt)
                    break
                except ValueError:
                    continue
            if expires is None:
                show_error("Błąd daty", f"Nierozpoznany format: '{raw_exp}'\n(użyj RRRR-MM-DD)", parent=self)
                return

        from utils.import_manager import _parse_otp_secret
        otp_raw    = self._otp_e.text().strip()
        otp_secret = _parse_otp_secret(otp_raw) if otp_raw else None

        if self.entry:
            self.db.update_password(
                self.entry, self.crypto,
                title=title, username=username, plaintext_password=password,
                url=url, notes=notes, category=category, expires_at=expires,
                otp_secret=otp_secret,
            )
        else:
            self.db.add_password(
                self.user, self.crypto,
                title=title, username=username, plaintext_password=password,
                url=url, notes=notes, category=category, expires_at=expires,
                otp_secret=otp_secret,
            )
        self.result = True
        self.accept()


# ══════════════════════════════════════════════════════════════════════
# ExportDialog — wybór formatu i eksport haseł
# ══════════════════════════════════════════════════════════════════════

class ExportDialog(QDialog):
    _FORMATS = [
        ("aegis",    "🔒 AegisVault (.aegis)",       "Zaszyfrowany backup — tylko dla AegisVault.",             "aegisvault_backup.aegis",    "AegisVault Backup (*.aegis)"),
        ("csv",      "📄 Generic CSV (.csv)",         "Kompatybilny z większością menedżerów haseł.",           "export_aegisvault.csv",      "CSV (*.csv)"),
        ("bitwarden","🔵 Bitwarden JSON (.json)",     "Import bezpośrednio do Bitwarden.",                       "bitwarden_export.json",      "JSON (*.json)"),
        ("1password","🔑 1Password CSV (.csv)",       "Import do 1Password przez File → Import.",               "1password_export.csv",       "CSV (*.csv)"),
        ("keepass",  "🟢 KeePass XML (.xml)",         "Import do KeePass 2 / KeePassXC.",                       "keepass_export.xml",         "XML (*.xml)"),
    ]

    def __init__(self, parent, db, crypto, user):
        super().__init__(parent)
        self.db     = db
        self.crypto = crypto
        self.user   = user

        self.setWindowTitle("Eksport haseł")
        self.setFixedSize(480, 480)

        _p    = PrefsManager()
        accent = _p.get_accent()
        dark   = (_p.get("appearance_mode") or "dark").lower() != "light"
        bg_rgba  = "rgba(18,18,18,0.92)" if dark else "rgba(240,240,240,0.92)"
        bg_card  = "#242424" if dark else "#f8f8f8"
        bg_sel   = "#1a2a3a" if dark else "#ddeeff"
        bdr_sel  = accent
        bdr_norm = "#3a3a3a" if dark else "#dddddd"
        text_col = "#f0f0f0" if dark else "#1a1a1a"
        muted    = "#888888" if dark else "#666666"

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(f"""
            QDialog {{ background: {bg_rgba}; border-radius: 14px; }}
            QLabel  {{ background: transparent; border: none; color: {text_col}; }}
        """)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(20, 16, 20, 16)
        vl.setSpacing(10)

        title_lbl = QLabel("Eksport haseł")
        title_lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {text_col};")
        vl.addWidget(title_lbl)

        sep = AnimatedGradientWidget(accent=accent, base="#161616" if dark else "#f2f2f2",
                                     direction="h", anim_mode="slide")
        sep.setFixedHeight(2)
        sep.start_animation()
        vl.addWidget(sep)

        hint = QLabel("Wybierz format eksportu:")
        hint.setStyleSheet(f"font-size: 12px; color: {muted};")
        vl.addWidget(hint)

        # Karty formatów
        self._selected = "aegis"
        self._cards: dict[str, QFrame] = {}

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.viewport().setStyleSheet("background: transparent;")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        fl = QVBoxLayout(inner)
        fl.setSpacing(6)
        fl.setContentsMargins(0, 0, 0, 0)

        for fmt_id, fmt_name, fmt_desc, _, _ in self._FORMATS:
            card = QFrame()
            card.setFixedHeight(62)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            self._cards[fmt_id] = card
            cl = QHBoxLayout(card)
            cl.setContentsMargins(12, 8, 12, 8)
            cl.setSpacing(10)
            text_w = QWidget()
            text_w.setStyleSheet("background: transparent; border: none;")
            tl = QVBoxLayout(text_w)
            tl.setContentsMargins(0, 0, 0, 0)
            tl.setSpacing(2)
            name_lbl = QLabel(fmt_name)
            name_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {text_col};")
            desc_lbl = QLabel(fmt_desc)
            desc_lbl.setStyleSheet(f"font-size: 11px; color: {muted};")
            tl.addWidget(name_lbl)
            tl.addWidget(desc_lbl)
            cl.addWidget(text_w, stretch=1)
            fl.addWidget(card)
            card.mousePressEvent = lambda _, fid=fmt_id: self._select(fid)

        fl.addStretch()
        scroll.setWidget(inner)
        vl.addWidget(scroll, stretch=1)

        # Ostrzeżenie (plaintext)
        self._warn_lbl = QLabel("⚠️  Ten format zawiera hasła w postaci niezaszyfrowanej.\nPrzechowuj plik w bezpiecznym miejscu i usuń po użyciu.")
        self._warn_lbl.setWordWrap(True)
        self._warn_lbl.setStyleSheet(
            f"color: #f0a500; font-size: 11px; font-weight: bold; "
            f"background: {'#2a1e00' if dark else '#fff8e1'}; border-radius: 8px; padding: 8px 10px;"
        )
        self._warn_lbl.setVisible(False)
        vl.addWidget(self._warn_lbl)

        # Przyciski
        btn_row = QWidget()
        brl = QHBoxLayout(btn_row)
        brl.setContentsMargins(0, 0, 0, 0)
        brl.setSpacing(8)
        cancel = QPushButton("Anuluj")
        cancel.setFixedHeight(42)
        cancel.setStyleSheet(
            f"background: transparent; border: 1.5px solid {'#525252' if dark else '#c0c0c0'}; "
            f"color: {muted}; border-radius: 10px; font-size: 13px;"
        )
        cancel.clicked.connect(self.reject)
        brl.addWidget(cancel)
        self._export_btn = QPushButton("Eksportuj →")
        self._export_btn.setFixedHeight(42)
        self._export_btn.setStyleSheet(
            f"background: {accent}; color: white; border-radius: 10px; "
            "font-size: 13px; font-weight: bold;"
        )
        self._export_btn.clicked.connect(self._do_export)
        brl.addWidget(self._export_btn)
        vl.addWidget(btn_row)

        # Zapamiętaj stale używane kolory
        self._bg_card = bg_card
        self._bg_sel  = bg_sel
        self._bdr_sel = bdr_sel
        self._bdr_norm = bdr_norm
        self._accent = accent

        self._hex = HexBackground(self, hex_size=32, glow_max=2, glow_interval_ms=2000)
        self._hex.setGeometry(0, 0, self.width(), self.height())
        self._hex.lower()
        QTimer.singleShot(0, lambda: self._hex and (
            self._hex.setGeometry(0, 0, self.width(), self.height()), self._hex.lower()
        ))

        self._select("aegis")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_hex"):
            self._hex.setGeometry(0, 0, self.width(), self.height())
            self._hex.lower()

    def _select(self, fmt_id: str):
        self._selected = fmt_id
        for fid, card in self._cards.items():
            sel = (fid == fmt_id)
            card.setStyleSheet(
                f"QFrame {{ background: {self._bg_sel if sel else self._bg_card}; "
                f"border: {'2px' if sel else '1px'} solid {self._bdr_sel if sel else self._bdr_norm}; "
                f"border-radius: 10px; }}"
            )
        self._warn_lbl.setVisible(fmt_id != "aegis")

    def _do_export(self):
        fmt_dict = {f[0]: f for f in self._FORMATS}
        _, _, _, default_name, file_filter = fmt_dict[self._selected]

        path, _ = QFileDialog.getSaveFileName(self, "Eksport haseł", default_name, file_filter)
        if not path:
            return

        self._export_btn.setEnabled(False)
        self._export_btn.setText("Eksportuję…")

        def _run():
            try:
                from utils.export_manager import collect_entries, export_csv, export_bitwarden_json, export_1password_csv, export_keepass_xml
                count = 0
                if self._selected == "aegis":
                    count = self.db.export_passwords(self.user, self.crypto, path)
                else:
                    entries = collect_entries(self.db, self.crypto, self.user)
                    if self._selected == "csv":
                        count = export_csv(entries, path)
                    elif self._selected == "bitwarden":
                        count = export_bitwarden_json(entries, path)
                    elif self._selected == "1password":
                        count = export_1password_csv(entries, path)
                    elif self._selected == "keepass":
                        count = export_keepass_xml(entries, path)
                QTimer.singleShot(0, lambda: self._done(count, path))
            except Exception as e:
                QTimer.singleShot(0, lambda: self._error(str(e)))

        threading.Thread(target=_run, daemon=True).start()

    def _done(self, count: int, path: str):
        self._export_btn.setEnabled(True)
        self._export_btn.setText("Eksportuj →")
        show_success("Eksport zakończony",
                     f"Wyeksportowano {count} haseł.\n\n{os.path.basename(path)}",
                     parent=self)
        self.accept()

    def _error(self, msg: str):
        self._export_btn.setEnabled(True)
        self._export_btn.setText("Eksportuj →")
        show_error("Błąd eksportu", msg, parent=self)


# ══════════════════════════════════════════════════════════════════════
# NoteFormDialog — dodawanie / edycja zaszyfrowanej notatki
# ══════════════════════════════════════════════════════════════════════

class NoteFormDialog(QDialog):
    def __init__(self, parent, db, user, entry=None):
        super().__init__(parent)
        self.db     = db
        self.user   = user
        self.entry  = entry
        self.result = False

        self.setWindowTitle("Edytuj notatkę" if entry else "Nowa notatka")
        self.setFixedWidth(460)
        self.setMinimumHeight(400)

        _p    = PrefsManager()
        accent = _p.get_accent()
        dark   = (_p.get("appearance_mode") or "dark").lower() != "light"

        bg_rgba  = "rgba(18,18,18,0.92)" if dark else "rgba(240,240,240,0.92)"
        bg_input = "#2e2e2e" if dark else "#ffffff"
        bdr      = "#525252" if dark else "#c0c0c0"
        text_col = "#f0f0f0" if dark else "#1a1a1a"
        lbl_col  = "#aaaaaa" if dark else "#555555"

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(f"""
            QDialog {{ background: {bg_rgba}; color: {text_col}; border-radius: 14px; }}
            QLabel  {{ color: {text_col}; font-size: 13px; background: transparent; border: none; }}
            QLineEdit, QTextEdit {{
                background: {bg_input}; color: {text_col};
                border: 1.5px solid {bdr}; border-radius: 8px;
                padding: 8px 12px; font-size: 13px;
            }}
            QLineEdit:focus, QTextEdit:focus {{ border-color: {accent}; border-width: 2px; }}
        """)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(20, 16, 20, 16)
        vl.setSpacing(8)

        title_lbl = QLabel("Edytuj notatkę" if entry else "Nowa notatka")
        title_lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {text_col};")
        vl.addWidget(title_lbl)

        sep = AnimatedGradientWidget(accent=accent, base="#161616" if dark else "#f2f2f2",
                                     direction="h", anim_mode="slide")
        sep.setFixedHeight(2)
        sep.start_animation()
        vl.addWidget(sep)

        # Tytuł
        lbl_t = QLabel("TYTUŁ")
        lbl_t.setStyleSheet(f"color: {lbl_col}; font-size: 11px; font-weight: 600;")
        vl.addWidget(lbl_t)
        self._title_e = QLineEdit()
        self._title_e.setPlaceholderText("Tytuł notatki...")
        self._title_e.setFixedHeight(40)
        self._title_e.setStyleSheet(
            f"background: {bg_input}; color: {text_col}; "
            f"border: 1.5px solid {bdr}; border-radius: 8px; padding: 8px 12px; font-size: 13px;"
        )
        vl.addWidget(self._title_e)

        # Treść
        lbl_c = QLabel("TREŚĆ")
        lbl_c.setStyleSheet(f"color: {lbl_col}; font-size: 11px; font-weight: 600;")
        vl.addWidget(lbl_c)
        self._content_e = QTextEdit()
        self._content_e.setPlaceholderText("Zawartość notatki...")
        self._content_e.setMinimumHeight(180)
        self._content_e.setStyleSheet(
            f"background: {bg_input}; color: {text_col}; "
            f"border: 1.5px solid {bdr}; border-radius: 8px; padding: 8px 10px; font-size: 13px;"
        )
        vl.addWidget(self._content_e, stretch=1)

        # Przyciski
        btn_row = QWidget()
        brl = QHBoxLayout(btn_row)
        brl.setContentsMargins(0, 4, 0, 0)
        cancel = QPushButton("Anuluj")
        cancel.setFixedHeight(42)
        cancel.setStyleSheet(
            f"background: transparent; border: 1.5px solid {bdr}; "
            f"color: {lbl_col}; border-radius: 10px; font-size: 13px;"
        )
        cancel.clicked.connect(self.reject)
        brl.addWidget(cancel)
        save_btn = QPushButton("Zapisz")
        save_btn.setFixedHeight(42)
        save_btn.setStyleSheet(
            f"background: {accent}; color: white; border-radius: 10px; "
            "font-size: 13px; font-weight: bold;"
        )
        save_btn.clicked.connect(self._save)
        brl.addWidget(save_btn)
        vl.addWidget(btn_row)

        # Wypełnij przy edycji
        if entry:
            self._title_e.setText(entry.title or "")
            self._content_e.setPlainText(entry.notes or "")

        self._hex = HexBackground(self, hex_size=32, glow_max=2, glow_interval_ms=2000)
        self._hex.setGeometry(0, 0, self.width(), self.height())
        self._hex.lower()
        QTimer.singleShot(0, lambda: self._hex and (
            self._hex.setGeometry(0, 0, self.width(), self.height()),
            self._hex.lower()
        ))
        QTimer.singleShot(200, self._title_e.setFocus)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_hex"):
            self._hex.setGeometry(0, 0, self.width(), self.height())
            self._hex.lower()

    def _save(self):
        title   = self._title_e.text().strip()
        content = self._content_e.toPlainText().strip()
        if not title:
            show_error("Błąd", "Tytuł notatki jest wymagany!", parent=self)
            return
        if self.entry:
            self.db.update_note(self.entry, title, content)
        else:
            self.db.add_note(self.user, title, content)
        self.result = True
        self.accept()


# ══════════════════════════════════════════════════════════════════════
# CategoryDialog — nowa kategoria (emoji + kolor)
# ══════════════════════════════════════════════════════════════════════

class CategoryDialog(QDialog):
    def __init__(self, parent, db, user, on_created=None):
        super().__init__(parent)
        self.db         = db
        self.user       = user
        self.on_created = on_created
        self._icon  = _EMOJI_PICKER[0]
        self._color = _CAT_PRESET_COLORS[5]
        self.result = None

        self.setWindowTitle("Nowa kategoria")
        self.setFixedSize(430, 480)
        _p = PrefsManager()
        accent = _p.get_accent()
        dark   = (_p.get("appearance_mode") or "dark").lower() != "light"

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(f"""
            QDialog {{ background: {'rgba(18,18,18,0.92)' if dark else 'rgba(240,240,240,0.92)'}; color: {'#f0f0f0' if dark else '#1a1a1a'}; border-radius: 14px; }}
            QLabel  {{ color: {'#f0f0f0' if dark else '#1a1a1a'}; font-size: 13px; background: transparent; border: none; }}
        """)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(20, 16, 20, 16)
        vl.setSpacing(8)

        QLabel_title = QLabel("Nowa kategoria")
        QLabel_title.setStyleSheet("font-size: 17px; font-weight: bold;")
        vl.addWidget(QLabel_title)

        sep = AnimatedGradientWidget(accent=accent, base="#161616" if dark else "#f2f2f2", direction="h", anim_mode="slide")
        sep.setFixedHeight(2)
        sep.start_animation()
        vl.addWidget(sep)

        # Podgląd
        self._preview = QLabel(f"{self._icon}  Nowa kategoria")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setFixedHeight(40)
        self._preview.setStyleSheet(
            f"background: {self._color}; color: white; border-radius: 10px; font-size: 13px; font-weight: bold;"
        )
        vl.addWidget(self._preview)

        # Nazwa
        vl.addWidget(QLabel("Nazwa"))
        self._name_e = QLineEdit()
        self._name_e.setPlaceholderText("np. Praca, Gaming...")
        self._name_e.setFixedHeight(38)
        self._name_e.setStyleSheet(
            f"background: {'#2e2e2e' if dark else '#ffffff'}; color: {'#f0f0f0' if dark else '#1a1a1a'}; "
            f"border: 1.5px solid {accent}; border-radius: 8px; padding: 6px 10px; font-size: 13px;"
        )
        self._name_e.textChanged.connect(self._update_preview)
        vl.addWidget(self._name_e)

        # Emoji
        vl.addWidget(QLabel("Ikona"))
        emoji_w = QWidget()
        emoji_w.setStyleSheet(f"background: {'rgba(40,40,40,0.95)' if dark else 'rgba(220,220,220,0.95)'}; border-radius: 10px; border: none;")
        eg = QGridLayout(emoji_w)
        eg.setContentsMargins(6, 6, 6, 6)
        eg.setSpacing(2)
        COLS = 8
        self._emoji_btns = []
        for idx, em in enumerate(_EMOJI_PICKER):
            r, c = divmod(idx, COLS)
            b = QPushButton(em)
            b.setFixedSize(36, 32)
            b.setStyleSheet("background: transparent; border: none; border-radius: 6px; font-size: 14px;")
            b.clicked.connect(lambda _, e=em, i=idx: self._pick_emoji(e, i))
            eg.addWidget(b, r, c)
            self._emoji_btns.append(b)
        self._emoji_btns[0].setStyleSheet(f"background: {accent}; border: none; border-radius: 6px; font-size: 14px;")
        vl.addWidget(emoji_w)

        # Kolory
        vl.addWidget(QLabel("Kolor"))
        color_w = QWidget()
        color_w.setStyleSheet(f"background: {'rgba(40,40,40,0.95)' if dark else 'rgba(220,220,220,0.95)'}; border-radius: 10px; border: none;")
        crl = QHBoxLayout(color_w)
        crl.setContentsMargins(8, 8, 8, 8)
        self._color_btns = []
        for i, col in enumerate(_CAT_PRESET_COLORS):
            b = QPushButton()
            b.setFixedSize(32, 32)
            brd = "border: 2px solid white;" if i == 5 else f"border: 2px solid {col};"
            b.setStyleSheet(f"background: {col}; border-radius: 16px; {brd}")
            b.clicked.connect(lambda _, c=col, idx=i: self._pick_color(c, idx))
            crl.addWidget(b)
            self._color_btns.append(b)
        crl.addStretch()
        vl.addWidget(color_w)

        vl.addStretch()

        # Przyciski
        br = QWidget()
        brl = QHBoxLayout(br)
        brl.setContentsMargins(0, 0, 0, 0)
        cancel = QPushButton("Anuluj")
        cancel.setFixedHeight(38)
        cancel.setStyleSheet(f"background: transparent; border: 1.5px solid {'#525252' if dark else '#b0b0b0'}; color: {'#aaaaaa' if dark else '#555555'}; border-radius: 8px;")
        cancel.clicked.connect(self.reject)
        brl.addWidget(cancel)
        ok_btn = QPushButton("Utwórz")
        ok_btn.setFixedHeight(38)
        ok_btn.setStyleSheet(f"background: {accent}; color: white; border-radius: 8px; font-weight: bold;")
        ok_btn.clicked.connect(self._create)
        brl.addWidget(ok_btn)
        vl.addWidget(br)

        QTimer.singleShot(200, self._name_e.setFocus)

    def _update_preview(self):
        name = self._name_e.text() or "Nowa kategoria"
        self._preview.setText(f"{self._icon}  {name}")
        self._preview.setStyleSheet(
            f"background: {self._color}; color: white; border-radius: 10px; font-size: 13px; font-weight: bold;"
        )

    def _pick_emoji(self, em, idx):
        self._icon = em
        self._update_preview()
        accent = PrefsManager().get_accent()
        for b in self._emoji_btns:
            b.setStyleSheet("background: transparent; border: none; border-radius: 6px; font-size: 14px;")
        self._emoji_btns[idx].setStyleSheet(f"background: {accent}; border: none; border-radius: 6px; font-size: 14px;")

    def _pick_color(self, col, idx):
        self._color = col
        self._update_preview()
        for i, b in enumerate(self._color_btns):
            c = _CAT_PRESET_COLORS[i]
            brd = "border: 2px solid white;" if i == idx else f"border: 2px solid {c};"
            b.setStyleSheet(f"background: {c}; border-radius: 16px; {brd}")

    def _create(self):
        name = self._name_e.text().strip()
        if not name:
            show_error("Błąd", "Podaj nazwę kategorii!", parent=self)
            return
        try:
            self.db.add_custom_category(self.user, name, self._icon, self._color)
            self.result = name
            if self.on_created:
                self.on_created(name)
            self.accept()
        except Exception as e:
            show_error("Błąd", str(e), parent=self)


# ══════════════════════════════════════════════════════════════════════
# TrashDialog — okno kosza
# ══════════════════════════════════════════════════════════════════════

class TrashDialog(QDialog):
    def __init__(self, parent, db, crypto, user, on_refresh):
        super().__init__(parent)
        self.db         = db
        self.crypto     = crypto
        self.user       = user
        self.on_refresh = on_refresh
        accent = PrefsManager().get_accent()

        self.setWindowTitle("Kosz")
        self.setFixedSize(580, 500)
        self.setStyleSheet("""
            QDialog { background: #1a1a1a; color: #f0f0f0; }
            QLabel  { color: #f0f0f0; background: transparent; border: none; }
        """)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setFixedHeight(60)
        hdr.setStyleSheet(f"background: {_blend(accent, '#1e1e1e', 0.18)}; border: none;")
        hrl = QHBoxLayout(hdr)
        hrl.setContentsMargins(20, 0, 20, 0)
        title_lbl = QLabel("Kosz")
        title_lbl.setStyleSheet("font-size: 19px; font-weight: bold;")
        hrl.addWidget(title_lbl)
        hrl.addStretch()
        purge_btn = QPushButton("Wyczyść kosz")
        purge_btn.setFixedHeight(34)
        purge_btn.setStyleSheet("background: #4a1a1a; color: #ff8080; border-radius: 8px; font-size: 12px;")
        purge_btn.clicked.connect(self._purge_all)
        hrl.addWidget(purge_btn)
        vl.addWidget(hdr)

        sep = AnimatedGradientWidget(accent=accent, base="#1a1a1a", direction="h", anim_mode="slide")
        sep.setFixedHeight(2)
        sep.start_animation()
        vl.addWidget(sep)

        info = QLabel("Hasła w koszu są trwale usuwane po 30 dniach.")
        info.setStyleSheet("color: #888; font-size: 11px; padding: 8px 20px 4px 20px;")
        vl.addWidget(info)

        # Lista
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("background: #1a1a1a; border: none;")
        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: #1a1a1a;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(20, 8, 20, 8)
        self._list_layout.setSpacing(6)
        self._scroll.setWidget(self._list_widget)
        vl.addWidget(self._scroll)

        self._load()

    def _load(self):
        # Wyczyść
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        entries = self.db.get_trashed_passwords(self.user)
        if not entries:
            empty = QLabel("Kosz jest pusty.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #888; font-size: 13px; padding: 40px;")
            self._list_layout.addWidget(empty)
            self._list_layout.addStretch()
            return

        accent = PrefsManager().get_accent()
        for entry in entries:
            row = QFrame()
            row.setStyleSheet("background: #2a2a2a; border-radius: 10px; border: none;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 8, 8, 8)

            info_w = QWidget()
            info_w.setStyleSheet("background: transparent; border: none;")
            il = QVBoxLayout(info_w)
            il.setSpacing(2)
            il.setContentsMargins(0, 0, 0, 0)
            t = QLabel(entry.title or "—")
            t.setStyleSheet("font-size: 13px; font-weight: bold;")
            il.addWidget(t)
            days_txt = ""
            if entry.deleted_at:
                from database.db_manager import TRASH_DAYS
                removed = (datetime.now(timezone.utc) - entry.deleted_at).days
                left = TRASH_DAYS - removed
                days_txt = f"Usunięto: {entry.deleted_at.strftime('%d.%m.%Y')}  •  Pozostało {left} dni"
            d = QLabel(days_txt)
            d.setStyleSheet("font-size: 10px; color: #888;")
            il.addWidget(d)
            rl.addWidget(info_w, stretch=1)

            restore_btn = QPushButton("Przywróć")
            restore_btn.setFixedHeight(30)
            restore_btn.setStyleSheet(f"background: {accent}; color: white; border-radius: 6px; font-size: 11px; font-weight: bold;")
            restore_btn.clicked.connect(lambda _, e=entry: self._restore(e))
            rl.addWidget(restore_btn)

            del_btn = QPushButton("Usuń")
            del_btn.setFixedHeight(30)
            del_btn.setStyleSheet("background: #4a1a1a; color: #ff8080; border-radius: 6px; font-size: 11px;")
            del_btn.clicked.connect(lambda _, e=entry: self._delete_perm(e))
            rl.addWidget(del_btn)

            self._list_layout.addWidget(row)
        self._list_layout.addStretch()

    def _restore(self, entry):
        self.db.restore_password(entry)
        self.on_refresh()
        self._load()

    def _delete_perm(self, entry):
        if ask_yes_no("Usuń permanentnie",
                      f"Trwale usunąć '{entry.title}'?",
                      parent=self, yes_text="Usuń", destructive=True):
            self.db.delete_password(entry)
            self._load()

    def _purge_all(self):
        entries = self.db.get_trashed_passwords(self.user)
        if not entries:
            return
        if ask_yes_no("Wyczyść kosz",
                      f"Trwale usunąć wszystkie {len(entries)} haseł?",
                      parent=self, yes_text="Wyczyść", destructive=True):
            for e in entries:
                self.db.delete_password(e)
            self._load()


# ══════════════════════════════════════════════════════════════════════
# PasswordRowWidget — wiersz hasła
# ══════════════════════════════════════════════════════════════════════

class PasswordRowWidget(QFrame):
    def __init__(self, parent, entry, db, crypto, user,
                 on_refresh, on_copy, on_autotype=None,
                 strength_color="#718096", strength_score=2,
                 cat_color="#718096", compact=False):
        super().__init__(parent)
        self.entry          = entry
        self.db             = db
        self.crypto         = crypto
        self.user           = user
        self.on_refresh     = on_refresh
        self.on_copy        = on_copy
        self.on_autotype    = on_autotype
        self.strength_color = strength_color
        self.strength_score = strength_score
        self.cat_color      = cat_color
        self.compact        = compact
        _p = PrefsManager()
        self._accent        = _p.get_accent()
        self._dark          = (_p.get("appearance_mode") or "dark").lower() != "light"

        self.setFrameShape(QFrame.Shape.NoFrame)
        _row_bg    = "#2a2a2a" if self._dark else "#ffffff"
        _row_hover = "#303030" if self._dark else "#f0f0f0"
        _row_bdr   = "#3a3a3a" if self._dark else "#dddddd"
        self.setStyleSheet(f"""
            PasswordRowWidget {{
                background: {_row_bg}; border-radius: 12px;
                border: 1px solid {_row_bdr};
            }}
            PasswordRowWidget:hover {{ background: {_row_hover}; border-color: {self._accent}44; }}
        """)
        self._build()

    def _build(self):
        if getattr(self.entry, "entry_type", "password") == "note":
            self._build_note()
            return
        entry   = self.entry
        accent  = self._accent
        compact = self.compact
        height  = 44 if compact else 72
        self.setFixedHeight(height)

        rl = QHBoxLayout(self)
        rl.setContentsMargins(6, 6, 8, 6)
        rl.setSpacing(0)

        # Pasek siły (lewy edge)
        str_bar = QFrame()
        str_bar.setFixedWidth(4)
        str_bar.setStyleSheet(f"background: {self.strength_color}; border-radius: 2px; margin: 6px 0;")
        rl.addWidget(str_bar)
        rl.addSpacing(6)

        # Avatar z inicjałem
        avatar_size = 30 if compact else 38
        avatar = QLabel((entry.title or "?")[0].upper())
        avatar.setFixedSize(avatar_size, avatar_size)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background: {self.cat_color}; color: white; "
            f"border-radius: {avatar_size//2 - 2}px; font-size: {avatar_size//2 - 2}px; "
            f"font-weight: bold; border: none;"
        )
        rl.addWidget(avatar)
        rl.addSpacing(10)

        # Info
        info = QWidget()
        info.setStyleSheet("background: transparent; border: none;")
        il = QVBoxLayout(info)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(1)

        _text_col = "#f0f0f0" if self._dark else "#1a1a1a"
        if compact:
            title_row = QWidget()
            title_row.setStyleSheet("background: transparent; border: none;")
            trl = QHBoxLayout(title_row)
            trl.setContentsMargins(0, 0, 0, 0)
            trl.setSpacing(6)
            t = QLabel(entry.title or "—")
            t.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {_text_col}; background: transparent; border: none;")
            trl.addWidget(t)
            if entry.username:
                u = QLabel(f"  ·  {entry.username}")
                u.setStyleSheet("font-size: 11px; color: #888; background: transparent; border: none;")
                trl.addWidget(u)
            trl.addStretch()
            il.addWidget(title_row)
        else:
            title_row = QWidget()
            title_row.setStyleSheet("background: transparent; border: none;")
            trl = QHBoxLayout(title_row)
            trl.setContentsMargins(0, 0, 0, 0)
            trl.setSpacing(6)
            t = QLabel(entry.title or "—")
            t.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {_text_col}; background: transparent; border: none;")
            trl.addWidget(t)
            # Expiry badge
            exp = getattr(entry, "expiry_status", None)
            if exp in ("expired", "soon"):
                days = max(0, (entry.expires_at - datetime.now(timezone.utc)).days) if entry.expires_at else 0
                exp_lbl = QLabel("Wygasłe" if exp == "expired" else f"Za {days}d")
                bg_col = "#4a1a1a" if exp == "expired" else "#4a3a00"
                tc_col = "#ff8080" if exp == "expired" else "#ffcc00"
                exp_lbl.setStyleSheet(f"background: {bg_col}; color: {tc_col}; border-radius: 4px; font-size: 10px; padding: 1px 5px; border: none;")
                trl.addWidget(exp_lbl)
            trl.addStretch()
            il.addWidget(title_row)

            sub = entry.username or "—"
            if entry.url:
                sub += f"   •   {entry.url[:40]}"
            sub_lbl = QLabel(sub)
            sub_lbl.setStyleSheet("font-size: 11px; color: #888; background: transparent; border: none;")
            il.addWidget(sub_lbl)

            cat_lbl = QLabel(f"  {entry.category or 'Inne'}  ")
            cat_lbl.setStyleSheet(f"background: {self.cat_color}; color: white; border-radius: 6px; font-size: 10px; border: none;")
            il.addWidget(cat_lbl, alignment=Qt.AlignmentFlag.AlignLeft)

        rl.addWidget(info, stretch=1)

        # Przyciski
        btns = QWidget()
        btns.setStyleSheet("background: transparent; border: none;")
        btns.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        brl = QHBoxLayout(btns)
        brl.setContentsMargins(0, 0, 0, 0)
        brl.setSpacing(4)

        btn_h = 30 if compact else 36
        btn_w = 46 if compact else 100  # jednolita szerokość wszystkich przycisków

        # ── Ulubione ─────────────────────────────────────────────────
        fav_active = bool(getattr(entry, "is_favorite", 0))
        fav_btn = QPushButton("★")
        fav_btn.setFixedSize(36, btn_h)
        _fav_bg  = ("#2a2200" if self._dark else "#fff3cc") if fav_active else ("transparent" if self._dark else "transparent")
        _fav_col = "#f0a500" if fav_active else ("#666666" if self._dark else "#bbbbbb")
        _fav_bdr = f"1px solid {'#f0a500' if fav_active else ('#444' if self._dark else '#ccc')}"
        fav_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: {_fav_bg}; color: {_fav_col};"
            f"  border: {_fav_bdr}; border-radius: 6px;"
            f"  font-size: 16px;"
            f"  font-family: 'Segoe UI Symbol','Arial Unicode MS',sans-serif;"
            f"  padding: 0; min-height: 0; min-width: 0;"
            f"}}"
            f"QPushButton:hover {{ border-color: #f0a500; color: #f0a500; }}"
        )
        fav_btn.setToolTip("Dodaj do ulubionych" if not fav_active else "Usuń z ulubionych")
        fav_btn.clicked.connect(self._toggle_fav)
        brl.addWidget(fav_btn)

        def _action_btn(text_compact, text_full, bg, fg, callback, tooltip=""):
            b = QPushButton(text_compact if compact else text_full)
            b.setFixedSize(btn_w, btn_h)
            b.setStyleSheet(
                f"QPushButton {{"
                f"  background: {bg}; color: {fg};"
                f"  border: none; border-radius: 6px;"
                f"  font-size: {'11px' if compact else '12px'}; font-weight: 500;"
                f"  padding: 0 {'6px' if compact else '10px'}; min-height: 0; min-width: 0;"
                f"}}"
            )
            if tooltip:
                b.setToolTip(tooltip)
            b.clicked.connect(callback)
            brl.addWidget(b)
            return b

        # ── Kopiuj hasło ─────────────────────────────────────────────
        _action_btn("📋", "📋 Kopiuj", accent, "#ffffff", self._copy, "Kopiuj hasło (Ctrl+C)")

        # ── Kopiuj login ─────────────────────────────────────────────
        _bg_green = "#1e3a1e" if self._dark else "#d4f0d4"
        _fg_green = "#7ec87e" if self._dark else "#2a6e2a"
        _action_btn("👤", "👤 Login", _bg_green, _fg_green, self._copy_username, "Kopiuj nazwę użytkownika")

        # ── Auto-type (tylko pełny widok) ────────────────────────────
        if not compact:
            _action_btn("", "⌨ Auto-type", _bg_green, _fg_green, self._autotype, "Auto-type")

        # ── Otwórz URL (tylko gdy wpis ma URL) ───────────────────────
        if getattr(entry, "url", None):
            url_btn = QPushButton("🌐")
            url_btn.setFixedSize(36, btn_h)
            url_btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {'#7ab8f5' if self._dark else '#1a5080'};"
                f" border: 1px solid {'#444' if self._dark else '#ccc'}; border-radius: 6px;"
                f" font-size: 15px; padding: 0; min-height: 0; min-width: 0; }}"
                f"QPushButton:hover {{ border-color: {self._accent}; }}"
            )
            url_btn.setToolTip(f"Otwórz: {entry.url}")
            url_btn.clicked.connect(self._open_url)
            brl.addWidget(url_btn)

        # ── OTP (tylko gdy wpis ma sekret) ───────────────────────────
        if getattr(entry, "otp_secret", None):
            self._otp_btn = QPushButton("🔑 ···")
            self._otp_btn.setFixedSize(btn_w + 14 if not compact else btn_w, btn_h)
            _otp_bg = "#1a2a3a" if self._dark else "#d4eaff"
            _otp_fg = "#7ab8f5" if self._dark else "#1a4a80"
            self._otp_btn.setStyleSheet(
                f"QPushButton {{"
                f"  background: {_otp_bg}; color: {_otp_fg};"
                f"  border: none; border-radius: 6px;"
                f"  font-size: {'11px' if compact else '12px'}; font-weight: bold;"
                f"  padding: 0 {'4px' if compact else '8px'}; min-height: 0; min-width: 0;"
                f"}}"
            )
            self._otp_btn.setToolTip("Kopiuj kod OTP (TOTP)")
            self._otp_btn.clicked.connect(self._copy_otp)
            brl.addWidget(self._otp_btn)
            # Live OTP timer
            self._otp_timer = QTimer(self)
            self._otp_timer.timeout.connect(self._refresh_otp_btn)
            self._otp_timer.start(1000)
            self._refresh_otp_btn()

        # ── Edytuj ───────────────────────────────────────────────────
        _bg_edit = "#2a2a2a" if self._dark else "#e8e8e8"
        _fg_edit = "#cccccc" if self._dark else "#444444"
        _action_btn("✎", "✎ Edytuj", _bg_edit, _fg_edit, self._edit, "Edytuj wpis")

        # ── Kosz ─────────────────────────────────────────────────────
        _action_btn("🗑", "🗑 Kosz", "#3a1a1a" if self._dark else "#fde8e8",
                    "#ff7070" if self._dark else "#c0392b", self._trash, "Przenieś do kosza")

        rl.addWidget(btns)

    def _open_url(self):
        url = self.entry.url or ""
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        if url:
            webbrowser.open(url)

    def _refresh_otp_btn(self):
        """Aktualizuje przycisk OTP — kod + pozostałe sekundy."""
        try:
            secret = self.entry.otp_secret
            totp   = pyotp.TOTP(secret)
            code   = totp.now()
            secs   = 30 - int(time.time()) % 30
            self._otp_btn.setText(f"🔑 {code[:3]} {code[3:]}  {secs}s" if not self.compact
                                  else f"🔑 {secs}s")
        except Exception:
            pass

    def _copy_otp(self):
        try:
            code = pyotp.TOTP(self.entry.otp_secret).now()
            pyperclip.copy(code)
            if self.on_copy:
                self.on_copy(f"{self.entry.title} (OTP)")
        except Exception:
            pass

    def _build_note(self):
        """Wariant wiersza dla zaszyfrowanej notatki."""
        entry = self.entry
        self.setFixedHeight(56 if not self.compact else 44)

        rl = QHBoxLayout(self)
        rl.setContentsMargins(6, 6, 8, 6)
        rl.setSpacing(0)

        # Pasek koloru (fiolet notatek)
        bar = QFrame()
        bar.setFixedWidth(4)
        bar.setStyleSheet("background: #5a67d8; border-radius: 2px; margin: 6px 0;")
        rl.addWidget(bar)
        rl.addSpacing(6)

        # Avatar
        av_size = 30 if self.compact else 38
        avatar = QLabel("📝")
        avatar.setFixedSize(av_size, av_size)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            "background: #3c3d7a; border-radius: {}px; font-size: {}px; border: none;".format(
                av_size // 2 - 2, av_size // 2 - 2
            )
        )
        rl.addWidget(avatar)
        rl.addSpacing(10)

        # Info
        info = QWidget()
        info.setStyleSheet("background: transparent; border: none;")
        il = QVBoxLayout(info)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(2)

        _text_col = "#f0f0f0" if self._dark else "#1a1a1a"
        t = QLabel(entry.title or "—")
        t.setStyleSheet(f"font-size: {'12px' if self.compact else '13px'}; font-weight: bold; color: {_text_col}; background: transparent; border: none;")
        il.addWidget(t)

        if not self.compact and entry.notes:
            preview = entry.notes[:80].replace("\n", " ")
            if len(entry.notes) > 80:
                preview += "…"
            sub = QLabel(preview)
            sub.setStyleSheet("font-size: 11px; color: #888; background: transparent; border: none;")
            il.addWidget(sub)

        rl.addWidget(info, stretch=1)

        # Przyciski: tylko Edytuj + Kosz
        btns = QWidget()
        btns.setStyleSheet("background: transparent; border: none;")
        brl = QHBoxLayout(btns)
        brl.setContentsMargins(0, 0, 0, 0)
        brl.setSpacing(4)
        btn_h = 30 if self.compact else 36
        btn_w = 46 if self.compact else 100

        _bg_edit = "#2a2a2a" if self._dark else "#e8e8e8"
        _fg_edit = "#cccccc" if self._dark else "#444444"
        for txt_c, txt_f, bg, fg, cb, tip in [
            ("✎", "✎ Edytuj", _bg_edit, _fg_edit, self._edit_note, "Edytuj notatkę"),
            ("🗑", "🗑 Kosz", "#3a1a1a" if self._dark else "#fde8e8",
             "#ff7070" if self._dark else "#c0392b", self._trash, "Przenieś do kosza"),
        ]:
            b = QPushButton(txt_c if self.compact else txt_f)
            b.setFixedSize(btn_w, btn_h)
            b.setStyleSheet(
                f"QPushButton {{ background: {bg}; color: {fg}; border: none; border-radius: 6px;"
                f" font-size: {'11px' if self.compact else '12px'}; font-weight: 500;"
                f" padding: 0 {'6px' if self.compact else '10px'}; min-height: 0; min-width: 0; }}"
            )
            b.setToolTip(tip)
            b.clicked.connect(cb)
            brl.addWidget(b)

        rl.addWidget(btns)

    def _edit_note(self):
        dlg = NoteFormDialog(self.window(), self.db, self.on_refresh.__self__.user
                             if hasattr(self.on_refresh, "__self__") else None,
                             self.entry)
        # Pobierz user z MainWindow
        win = self.window()
        if hasattr(win, "user"):
            dlg.user = win.user
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result:
            self.on_refresh()

    def _copy(self):
        try:
            plaintext = self.db.decrypt_password(self.entry, self.crypto)
            pyperclip.copy(plaintext)
            self.db.mark_used(self.entry)
            if self.on_copy:
                self.on_copy(self.entry.title)
        except Exception:
            pass

    def _copy_username(self):
        if self.entry.username:
            try:
                pyperclip.copy(self.entry.username)
                if self.on_copy:
                    self.on_copy(f"{self.entry.title} (login)")
            except Exception:
                pass

    def _autotype(self):
        if self.on_autotype:
            self.on_autotype(self.entry)

    def _toggle_fav(self):
        try:
            new_val = 0 if getattr(self.entry, "is_favorite", 0) else 1
            self.entry.is_favorite = new_val
            self.db.session.commit()
            self.on_refresh()
        except Exception:
            pass

    def _edit(self):
        dlg = PasswordFormDialog(self.window(), self.db, self.crypto, self.user, self.entry)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result:
            self.on_refresh()

    def _trash(self):
        if ask_yes_no("Kosz", f"Przenieść '{self.entry.title}' do kosza?",
                      parent=self.window(), yes_text="Do kosza"):
            self.db.trash_password(self.entry)
            self.on_refresh()


# ══════════════════════════════════════════════════════════════════════
# MainWindow
# ══════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    # Thread-safe signals
    _update_found_sig  = pyqtSignal(dict)
    _sync_status_sig   = pyqtSignal(bool)
    _score_ready_sig   = pyqtSignal(int)

    def __init__(self, db: DatabaseManager, crypto: CryptoManager, user):
        super().__init__()
        self.db     = db
        self.crypto = crypto
        self.user   = user
        self._prefs = PrefsManager()

        self._active_category    = "Wszystkie"
        self._compact_mode       = self._prefs.get("compact_mode") or False
        self._last_activity      = time.time()
        self._locked             = False
        self._clipboard_timer    = None
        self._clipboard_secs     = 0
        self._score_ring: AnimatedScoreRing | None = None
        self._settings_panel     = None
        self._tray               = None
        self._toast: ToastManager | None = None
        self._update_btn: QPushButton | None = None
        self._update_info        = None
        self._sync_connected     = None
        self._strength_cache: dict = {}
        self._cat_colors_cache   = None
        self._cat_cache          = None
        self._search_timer       = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._on_search)
        self._lock_timer         = QTimer(self)
        self._lock_timer.setInterval(10000)
        self._lock_timer.timeout.connect(self._check_lock)
        self._clipboard_qt_timer = QTimer(self)
        self._clipboard_qt_timer.setInterval(1000)
        self._clipboard_qt_timer.timeout.connect(self._tick_clipboard)
        self._clipboard_entry_title = ""

        # Generator state
        self._gen_length  = 16
        self._gen_upper   = True
        self._gen_digits  = True
        self._gen_special = True
        self._gen_pwd     = ""

        # Connect signals
        self._update_found_sig.connect(self._on_update_found)
        self._sync_status_sig.connect(self._on_sync_status)
        self._score_ready_sig.connect(self._on_score_ready)

        self.setWindowTitle(f"AegisVault — {user.username}")
        self.resize(960, 660)
        self.setMinimumSize(800, 520)

        self._build_ui()

        # Post-build
        self._toast = ToastManager(self.centralWidget())
        self._setup_tray()
        self._setup_shortcuts()
        self._load_passwords(animate=False)
        self._lock_timer.start()
        self._compute_security_score()

        # Background tasks
        threading.Thread(target=lambda: self.db.purge_old_trash(self.user), daemon=True).start()
        threading.Thread(target=self._bg_check_update, daemon=True).start()
        QTimer.singleShot(2000, self._sync_ping)
        QTimer.singleShot(4000, self._check_auto_backup)
        QTimer.singleShot(800, self._maybe_show_changelog)

        # Settings panel (deferred 1.5s)
        QTimer.singleShot(1500, self._precreate_settings)

        # Fade-in
        self.setWindowOpacity(0.0)
        self._fade_in_step(1, 8)

    # ── Fade-in ───────────────────────────────────────────────────────

    def _fade_in_step(self, i, steps):
        self.setWindowOpacity(i / steps)
        if i < steps:
            QTimer.singleShot(15, lambda: self._fade_in_step(i + 1, steps))
        else:
            self.setWindowOpacity(1.0)

    # ── Tray ─────────────────────────────────────────────────────────

    def _setup_tray(self):
        try:
            from gui_qt.tray import TrayIcon
            self._tray = TrayIcon(
                username=self.user.username,
                on_show=self._tray_show,
                on_lock=self._lock,
                on_quit=self._quit_app,
            )
            self._tray.show()
        except Exception:
            self._tray = None

    def _tray_show(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self._tray:
            self.hide()
            event.ignore()
        else:
            self._cleanup()
            event.accept()

    def _quit_app(self):
        self._cleanup()
        QApplication.quit()

    def _cleanup(self):
        self._lock_timer.stop()
        self._clipboard_qt_timer.stop()
        try:
            if self._tray:
                self._tray.hide()
        except Exception:
            pass

    # ── Build UI ──────────────────────────────────────────────────────

    def _build_ui(self):
        accent = self._prefs.get_accent()
        dark   = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
        bg     = "#1a1a1a" if dark else "#f5f5f5"
        hdr_bg = _blend(accent, "#1e1e1e" if dark else "#f0f0f0", 0.18)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Topbar ────────────────────────────────────────────────────
        topbar = QFrame()
        topbar.setFixedHeight(64)
        topbar.setStyleSheet(f"background: {hdr_bg}; border: none;")
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(16, 0, 12, 0)

        # Logo + tytuł
        pix = _accent_icon(accent, 28)
        if pix:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(pix)
            icon_lbl.setFixedSize(30, 30)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setStyleSheet("background: transparent; border: none;")
            tl.addWidget(icon_lbl)
            tl.addSpacing(4)
        logo_lbl = QLabel("AegisVault")
        logo_lbl.setStyleSheet(f"color: {accent}; font-size: 17px; font-weight: bold; background: transparent; border: none;")
        tl.addWidget(logo_lbl)

        # Breadcrumb
        self._breadcrumb_sep = QLabel(" › ")
        self._breadcrumb_sep.setStyleSheet("color: #666; font-size: 14px; background: transparent; border: none;")
        self._breadcrumb_sep.setVisible(False)
        tl.addWidget(self._breadcrumb_sep)
        self._breadcrumb_lbl = QLabel("")
        self._breadcrumb_lbl.setStyleSheet(f"color: {accent}; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        self._breadcrumb_lbl.setVisible(False)
        tl.addWidget(self._breadcrumb_lbl)

        tl.addStretch()

        # Szukaj
        self._search_entry = QLineEdit()
        self._search_entry.setPlaceholderText("Szukaj haseł...")
        self._search_entry.setFixedSize(220, 36)
        self._search_entry.setStyleSheet(f"""
            QLineEdit {{
                background: {'#252525' if dark else '#fff'};
                color: {'#f0f0f0' if dark else '#1a1a1a'};
                border: 1px solid {'#444' if dark else '#ccc'};
                border-radius: 18px; padding: 0 14px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {accent}; }}
        """)
        self._search_entry.textChanged.connect(lambda _: self._search_timer.start())
        tl.addWidget(self._search_entry)
        tl.addSpacing(8)

        # Sync dot
        self._sync_dot = QLabel("●")
        self._sync_dot.setFixedSize(16, 16)
        self._sync_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sync_dot.setStyleSheet("color: #555; font-size: 10px; background: transparent; border: none;")
        self._sync_dot.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sync_dot.mousePressEvent = lambda e: self._open_sync()
        tl.addWidget(self._sync_dot)

        # Update btn (ukryty)
        self._update_btn = QPushButton("⬆")
        self._update_btn.setFixedSize(36, 36)
        self._update_btn.setStyleSheet("background: #b87800; color: white; border-radius: 18px; font-size: 15px; font-weight: bold; border: none;")
        self._update_btn.clicked.connect(self._open_update_dialog)
        self._update_btn.setVisible(False)
        tl.addWidget(self._update_btn)

        # Theme toggle
        self._theme_btn = QPushButton("🌙" if dark else "☀")
        self._theme_btn.setFixedSize(36, 36)
        self._theme_btn.setStyleSheet(
            f"background: {_blend(accent, '#1e1e1e', 0.22)}; border: 1px solid {accent}; "
            f"border-radius: 18px; font-size: 16px; color: {accent}; "
            f"font-family: 'Segoe UI Emoji', 'Segoe UI Symbol', 'Apple Color Emoji', sans-serif; "
            f"padding: 0; min-height: 0;"
        )
        self._theme_btn.clicked.connect(self._toggle_theme)
        tl.addWidget(self._theme_btn)

        # User button
        self.user_btn = QPushButton(f"  {self.user.username}  ▾")
        self.user_btn.setFixedHeight(36)
        self.user_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {accent};
                border-radius: 18px; color: {accent}; font-size: 13px; padding: 0 14px;
            }}
            QPushButton:hover {{ background: {_blend(accent, '#1e1e1e', 0.15)}; }}
        """)
        self.user_btn.clicked.connect(self._toggle_user_menu)
        tl.addWidget(self.user_btn)

        # Score ring
        self._score_ring = AnimatedScoreRing(topbar, size=44, bg_color=hdr_bg, is_dark=dark)
        self._score_ring.start_pulse()
        self._score_ring.setCursor(Qt.CursorShape.PointingHandCursor)
        self._score_ring.mousePressEvent = lambda e: self._open_analysis()
        tl.addWidget(self._score_ring)

        root.addWidget(topbar)

        # Gradient separator
        self._top_sep = AnimatedGradientWidget(accent=accent, base=bg, direction="h", anim_mode="slide", fps=20, period_ms=6000)
        self._top_sep.setFixedHeight(2)
        self._top_sep.start_animation()
        root.addWidget(self._top_sep)

        # ── Body ──────────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet(f"background: {bg}; border: none;")
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        root.addWidget(body, stretch=1)

        # Sidebar
        self._sidebar = QFrame()
        self._sidebar.setFixedWidth(175)
        self._sidebar.setStyleSheet(f"background: {'#161616' if dark else '#f0f0f0'}; border: none;")
        self._sidebar_layout = QVBoxLayout(self._sidebar)
        self._sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self._sidebar_layout.setSpacing(0)
        self._build_sidebar()
        bl.addWidget(self._sidebar)

        # Separator pionowy
        vsep = QFrame()
        vsep.setFixedWidth(1)
        vsep.setStyleSheet(f"background: {'#2e2e2e' if dark else '#d0d0d0'}; border: none;")
        bl.addWidget(vsep)

        # Content
        content = QWidget()
        content.setStyleSheet(f"background: {bg}; border: none;")
        self._content_widget = content

        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        bl.addWidget(content, stretch=1)

        # Toolbar
        toolbar = QFrame()
        toolbar.setFixedHeight(56)
        toolbar.setStyleSheet(f"background: {bg}; border: none;")
        toll = QHBoxLayout(toolbar)
        toll.setContentsMargins(16, 8, 16, 8)

        self._count_lbl = QLabel("0 haseł")
        self._count_lbl.setStyleSheet(f"color: {'#888' if dark else '#666'}; font-size: 12px; background: transparent; border: none;")
        toll.addWidget(self._count_lbl)
        toll.addStretch()

        # Clipboard label
        self._clipboard_lbl = QLabel("")
        self._clipboard_lbl.setStyleSheet(f"color: {accent}; font-size: 12px; background: transparent; border: none;")
        toll.addWidget(self._clipboard_lbl)
        toll.addSpacing(12)

        # Widok
        self._view_btn = QPushButton("Kompaktowy" if self._compact_mode else "Normalny")
        self._view_btn.setFixedHeight(32)
        self._view_btn.setStyleSheet(f"background: {'#2a2a2a' if dark else '#e8e8e8'}; color: {'#f0f0f0' if dark else '#1a1a1a'}; border-radius: 8px; font-size: 12px; padding: 0 12px; border: none;")
        self._view_btn.clicked.connect(self._toggle_compact)
        toll.addWidget(self._view_btn)

        # Dodaj hasło / notatkę (zależnie od aktywnej kategorii)
        self._add_btn = QPushButton("+ Dodaj")
        self._add_btn.setFixedHeight(32)
        self._add_btn.setStyleSheet(f"background: {accent}; color: white; border-radius: 8px; font-size: 12px; font-weight: bold; padding: 0 12px; border: none;")
        self._add_btn.clicked.connect(self._add_smart)
        toll.addWidget(self._add_btn)

        cl.addWidget(toolbar)

        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background: {'#2a2a2a' if dark else '#d0d0d0'}; border: none;")
        cl.addWidget(sep2)

        # Password list
        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_scroll.setStyleSheet("background: transparent; border: none;")
        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_vl = QVBoxLayout(self._list_container)
        self._list_vl.setContentsMargins(12, 8, 12, 8)
        self._list_vl.setSpacing(4)
        self._list_scroll.setWidget(self._list_container)
        self._list_scroll.viewport().setStyleSheet("background: transparent;")
        # Hex is a child of viewport (not _list_container) so it always fills
        # the visible area regardless of how many password rows are loaded.
        self._content_hex = HexBackground(self._list_scroll.viewport(), hex_size=28, glow_max=2, glow_interval_ms=1800)
        self._content_hex.setGeometry(0, 0, self._list_scroll.viewport().width(), self._list_scroll.viewport().height())
        self._content_hex.lower()
        cl.addWidget(self._list_scroll, stretch=1)

    # ── Sidebar ───────────────────────────────────────────────────────

    def _build_sidebar(self):
        # Wyczyść
        while self._sidebar_layout.count():
            item = self._sidebar_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        dark   = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
        accent = self._prefs.get_accent()
        bg_sb  = "#161616" if dark else "#f0f0f0"

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background: {bg_sb}; border: none;")
        inner = QWidget()
        inner.setStyleSheet(f"background: {bg_sb};")
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(0, 8, 0, 8)
        vl.setSpacing(0)

        # Oblicz liczniki
        all_entries = self.db.get_all_passwords(self.user)
        counts: dict[str, int] = {}
        for e in all_entries:
            cat = e.category or "Inne"
            counts[cat] = counts.get(cat, 0) + 1
        counts["Wszystkie"] = len(all_entries)

        # Sekcja KATEGORIE
        self._cat_section_label(vl, "KATEGORIE", dark)
        if self._cat_cache is None:
            self._cat_cache = self.db.get_all_categories(self.user)
        cat_icons = self.db.get_category_icons(self.user)
        default_set = set(DEFAULT_CATEGORIES)

        self._cat_buttons: dict[str, QPushButton] = {}
        for cat in ["Wszystkie"] + self._cat_cache:
            icon     = CATEGORIES.get(cat, {}).get("icon") or cat_icons.get(cat, "🏷")
            n        = counts.get(cat, 0)
            label    = f"{icon} {cat}  ({n})" if n > 0 else f"{icon} {cat}"
            deletable = cat not in default_set and cat != "Wszystkie"
            self._add_cat_btn(vl, cat, label, deletable, dark, accent)

        # Dodaj kategorię
        new_cat_btn = self._sidebar_btn("+ Nowa kategoria", "#888", dark)
        new_cat_btn.clicked.connect(self._add_category)
        vl.addWidget(new_cat_btn)
        self._sidebar_sep(vl, dark)

        # SPECJALNE
        self._cat_section_label(vl, "SPECJALNE", dark)

        notes_count = len(self.db.get_all_notes(self.user))
        notes_txt   = f"📝 Notatki" + (f"  ({notes_count})" if notes_count else "")
        notes_btn   = self._sidebar_btn(notes_txt, "#5a67d8" if notes_count else "#888", dark)
        notes_btn.clicked.connect(lambda: self._filter_category("Notatki"))
        vl.addWidget(notes_btn)

        exp_count = len(self.db.get_expiring_passwords(self.user))
        exp_txt   = f"⏰ Wygasające" + (f"  ({exp_count})" if exp_count else "")
        exp_btn   = self._sidebar_btn(exp_txt, "#f0a500" if exp_count else "#888", dark)
        exp_btn.clicked.connect(lambda: self._filter_category("Wygasające"))
        vl.addWidget(exp_btn)

        trash_count = len(self.db.get_trashed_passwords(self.user))
        trash_txt   = f"🗑️ Kosz" + (f"  ({trash_count})" if trash_count else "")
        trash_btn   = self._sidebar_btn(trash_txt, "#e05252" if trash_count else "#888", dark)
        trash_btn.clicked.connect(self._open_trash)
        vl.addWidget(trash_btn)
        self._sidebar_sep(vl, dark)

        # BACKUP
        self._cat_section_label(vl, "BACKUP", dark)
        for txt, cmd in [
            ("📤 Eksport",           self._export),
            ("📥 Import .aegis",     self._import_aegis),
            ("📥 Import zewnętrzny", self._import_external),
        ]:
            b = self._sidebar_btn(txt, "#888", dark)
            b.clicked.connect(cmd)
            vl.addWidget(b)
        self._sidebar_sep(vl, dark)

        # GENERATOR
        self._cat_section_label(vl, "GENERATOR", dark)
        self._build_gen_panel(vl, dark, accent)

        vl.addStretch()
        scroll.setWidget(inner)
        self._sidebar_layout.addWidget(scroll)

        # Ustaw aktywny
        if self._active_category in self._cat_buttons:
            self._cat_buttons[self._active_category].setStyleSheet(
                self._cat_btn_style(
                    CATEGORIES.get(self._active_category, {}).get("color") or accent,
                    True, dark, accent
                )
            )

    def _cat_section_label(self, vl, text, dark):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: #888; font-size: 10px; font-weight: bold; padding: 14px 16px 4px 16px; background: transparent; border: none;")
        vl.addWidget(lbl)

    def _sidebar_sep(self, vl, dark):
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {'#2e2e2e' if dark else '#d0d0d0'}; margin: 6px 10px; border: none;")
        vl.addWidget(sep)

    def _sidebar_btn(self, text, color, dark) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(34)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; text-align: left;
                color: {color}; font-size: 12px; padding: 0 10px; border-radius: 8px;
            }}
            QPushButton:hover {{ background: {'#2a2a2a' if dark else '#e0e0e0'}; }}
        """)
        return btn

    @staticmethod
    def _cat_btn_style(cat_color, active, dark, accent):
        if active:
            return f"""
                QPushButton {{
                    background: {_blend(cat_color or accent, '#161616' if dark else '#f0f0f0', 0.25)};
                    border-left: 3px solid {cat_color or accent};
                    border-right: none; border-top: none; border-bottom: none;
                    text-align: left; color: {'#f0f0f0' if dark else '#1a1a1a'};
                    font-size: 12px; padding: 0 10px; border-radius: 0;
                }}
            """
        return f"""
            QPushButton {{
                background: transparent; border: none; text-align: left;
                color: {'#d0d0d0' if dark else '#333'}; font-size: 12px;
                padding: 0 10px; border-radius: 8px;
            }}
            QPushButton:hover {{ background: {'#2a2a2a' if dark else '#e0e0e0'}; }}
        """

    def _add_cat_btn(self, vl, cat, label, deletable, dark, accent):
        btn = QPushButton(label)
        btn.setFixedHeight(36)
        cat_color = CATEGORIES.get(cat, {}).get("color") or \
                    self._get_cat_color_from_db(cat)
        active = (cat == self._active_category)
        btn.setStyleSheet(self._cat_btn_style(cat_color, active, dark, accent))
        btn.clicked.connect(lambda _, c=cat: self._filter_category(c))
        vl.addWidget(btn)
        self._cat_buttons[cat] = btn

    def _get_cat_color_from_db(self, cat: str) -> str:
        if self._cat_colors_cache is None:
            try:
                self._cat_colors_cache = {
                    c.name: c.color for c in
                    self.db.session.query(
                        __import__('database.models', fromlist=['CustomCategory']).CustomCategory
                    ).filter_by(user_id=self.user.id).all()
                }
            except Exception:
                self._cat_colors_cache = {}
        return self._cat_colors_cache.get(cat, "#718096")

    # ── Generator panel ───────────────────────────────────────────────

    def _build_gen_panel(self, vl, dark, accent):
        gen = QFrame()
        gen.setStyleSheet(f"background: {'#222' if dark else '#e8e8e8'}; border-radius: 10px; border: none;")
        gl = QVBoxLayout(gen)
        gl.setContentsMargins(10, 8, 10, 10)
        gl.setSpacing(4)

        # Długość
        len_row = QWidget()
        len_row.setStyleSheet("background: transparent; border: none;")
        lrl = QHBoxLayout(len_row)
        lrl.setContentsMargins(0, 0, 0, 0)
        len_lbl = QLabel("Długość:")
        len_lbl.setStyleSheet(f"color: {'#f0f0f0' if dark else '#1a1a1a'}; font-size: 11px; background: transparent; border: none;")
        lrl.addWidget(len_lbl)
        lrl.addStretch()
        self._gen_len_lbl = QLabel(str(self._gen_length))
        self._gen_len_lbl.setStyleSheet(f"color: {accent}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        lrl.addWidget(self._gen_len_lbl)
        gl.addWidget(len_row)

        self._gen_slider = QSlider(Qt.Orientation.Horizontal)
        self._gen_slider.setRange(8, 64)
        self._gen_slider.setValue(self._gen_length)
        self._gen_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ background: {'#444' if dark else '#ccc'}; height: 4px; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {accent}; width: 12px; height: 12px; border-radius: 6px; margin: -4px 0; }}
            QSlider::sub-page:horizontal {{ background: {accent}; height: 4px; border-radius: 2px; }}
        """)
        self._gen_slider.valueChanged.connect(self._gen_slider_changed)
        gl.addWidget(self._gen_slider)

        # Opcje (checkboxy)
        for label, attr in [("Duże litery", "_gen_upper"), ("Cyfry", "_gen_digits"), ("Znaki specjalne", "_gen_special")]:
            cb = QCheckBox(label)
            cb.setChecked(getattr(self, attr))
            cb.setStyleSheet(f"""
                QCheckBox {{
                    color: {'#d0d0d0' if dark else '#444'};
                    font-size: 11px; background: transparent; spacing: 6px;
                }}
                QCheckBox::indicator {{
                    width: 14px; height: 14px;
                    border: 1px solid {'#666' if dark else '#aaa'};
                    border-radius: 3px;
                    background: {'#2a2a2a' if dark else '#fff'};
                }}
                QCheckBox::indicator:checked {{
                    background: {accent}; border-color: {accent};
                }}
            """)
            cb.stateChanged.connect(lambda state, a=attr: setattr(self, a, bool(state)))
            gl.addWidget(cb)

        # Hasło output
        self._gen_out = QLabel("—")
        self._gen_out.setWordWrap(True)
        self._gen_out.setStyleSheet(f"color: {'#90c090' if dark else '#2d6a4f'}; font-size: 11px; font-family: 'Courier New', monospace; background: transparent; border: none;")
        gl.addWidget(self._gen_out)

        # Przyciski
        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent; border: none;")
        brl = QHBoxLayout(btn_row)
        brl.setContentsMargins(0, 0, 0, 0)
        brl.setSpacing(4)
        gen_btn = QPushButton("Generuj")
        gen_btn.setFixedHeight(28)
        gen_btn.setStyleSheet(f"background: {accent}; color: white; border-radius: 6px; font-size: 11px; font-weight: bold; border: none; padding: 0 6px; min-height: 0;")
        gen_btn.clicked.connect(self._gen_generate)
        brl.addWidget(gen_btn)
        copy_btn = QPushButton("Kopiuj")
        copy_btn.setFixedHeight(28)
        copy_btn.setStyleSheet(f"background: {'#2a2a2a' if dark else '#e0e0e0'}; color: {'#f0f0f0' if dark else '#1a1a1a'}; border-radius: 6px; font-size: 11px; border: none; padding: 0 6px; min-height: 0;")
        copy_btn.clicked.connect(self._gen_copy)
        brl.addWidget(copy_btn)
        gl.addWidget(btn_row)

        vl.addWidget(gen)

    def _gen_slider_changed(self, val):
        self._gen_length = val
        if hasattr(self, "_gen_len_lbl"):
            self._gen_len_lbl.setText(str(val))

    def _gen_generate(self):
        import string
        chars = string.ascii_lowercase
        if self._gen_upper:   chars += string.ascii_uppercase
        if self._gen_digits:  chars += string.digits
        if self._gen_special: chars += "!@#$%^&*()-_=+[]{}|;:,.<>?"
        import random
        pwd = "".join(random.choices(chars, k=self._gen_length))
        self._gen_pwd = pwd
        self._gen_out.setText(pwd[:30] + ("…" if len(pwd) > 30 else ""))

    def _gen_copy(self):
        if self._gen_pwd:
            try:
                pyperclip.copy(self._gen_pwd)
                if self._toast:
                    self._toast.show("Skopiowano do schowka", "success")
            except Exception:
                pass

    # ── Category filter ───────────────────────────────────────────────

    def _filter_category(self, cat: str):
        self._active_category = cat
        accent = self._prefs.get_accent()
        dark   = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
        for c, b in self._cat_buttons.items():
            active = (c == cat)
            cat_color = CATEGORIES.get(c, {}).get("color") or self._get_cat_color_from_db(c)
            b.setStyleSheet(self._cat_btn_style(cat_color, active, dark, accent))

        if cat == "Wszystkie":
            self._breadcrumb_sep.setVisible(False)
            self._breadcrumb_lbl.setVisible(False)
        else:
            self._breadcrumb_lbl.setText(cat)
            self._breadcrumb_sep.setVisible(True)
            self._breadcrumb_lbl.setVisible(True)

        # Zmień label przycisku dodawania
        if hasattr(self, "_add_btn"):
            if cat == "Notatki":
                self._add_btn.setText("+ Notatka")
                self._add_btn.setStyleSheet(
                    "background: #5a67d8; color: white; border-radius: 8px; "
                    "font-size: 12px; font-weight: bold; padding: 0 12px; border: none;"
                )
            else:
                accent = self._prefs.get_accent()
                self._add_btn.setText("+ Dodaj")
                self._add_btn.setStyleSheet(
                    f"background: {accent}; color: white; border-radius: 8px; "
                    "font-size: 12px; font-weight: bold; padding: 0 12px; border: none;"
                )

        self._load_passwords()

    # ── Load passwords ────────────────────────────────────────────────

    def _load_passwords(self, query: str = "", animate: bool = True):
        # Usuń stare wiersze
        while self._list_vl.count():
            item = self._list_vl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if query:
            all_ent = self.db.get_passwords_by_category(self.user, self._active_category)
            entries = self._search_local(query, all_ent)
        else:
            entries = self.db.get_passwords_by_category(self.user, self._active_category)

        count    = len(entries)
        is_notes = (self._active_category == "Notatki")
        if is_notes:
            pl = "notatka" if count == 1 else "notatek"
        else:
            pl = "hasło" if count == 1 else "haseł"
        self._count_lbl.setText(f"{count} {pl}")

        if not entries:
            dark = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
            accent = self._prefs.get_accent()
            empty = QWidget()
            el = QVBoxLayout(empty)
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)

            if query:
                icon_lbl = QLabel("🔍")
                icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                icon_lbl.setStyleSheet("font-size: 40px; background: transparent; border: none;")
                el.addWidget(icon_lbl)
                el.addWidget(self._empty_lbl("Brak wyników", 15, dark))
                el.addWidget(self._empty_lbl(f'Nic nie pasuje do „{query}"', 12, dark, muted=True))
            else:
                is_notes_empty = (self._active_category == "Notatki")
                icon_lbl = QLabel("📝" if is_notes_empty else ("📂" if self._active_category != "Wszystkie" else "🔐"))
                icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                icon_lbl.setStyleSheet("font-size: 40px; background: transparent; border: none;")
                el.addWidget(icon_lbl)
                if is_notes_empty:
                    el.addWidget(self._empty_lbl("Brak notatek", 15, dark))
                    el.addWidget(self._empty_lbl("Dodaj pierwszą zaszyfrowaną notatkę.", 12, dark, muted=True))
                    add_e = QPushButton("+ Dodaj notatkę")
                    add_e.setFixedHeight(42)
                    add_e.setFixedWidth(200)
                    add_e.setStyleSheet(f"background: #5a67d8; color: white; border-radius: 10px; font-size: 13px; font-weight: bold; border: none;")
                    add_e.clicked.connect(self._add_note)
                    el.addWidget(add_e, alignment=Qt.AlignmentFlag.AlignCenter)
                else:
                    el.addWidget(self._empty_lbl("Brak haseł", 15, dark))
                    el.addWidget(self._empty_lbl("Nie masz jeszcze żadnych zapisanych haseł.", 12, dark, muted=True))
                    add_e = QPushButton("+ Dodaj pierwsze hasło")
                    add_e.setFixedHeight(42)
                    add_e.setFixedWidth(220)
                    add_e.setStyleSheet(f"background: {accent}; color: white; border-radius: 10px; font-size: 13px; font-weight: bold; border: none;")
                    add_e.clicked.connect(self._add_password)
                    el.addWidget(add_e, alignment=Qt.AlignmentFlag.AlignCenter)

            self._list_vl.addWidget(empty)
            self._list_vl.addStretch()
            return

        # Pobierz kolory kategorii
        cat_color_map = self._get_category_colors()

        # Oblicz siłę — z cache
        entry_data = []
        for entry in entries:
            cache_key = (entry.id, getattr(entry, "updated_at", None))
            if cache_key in self._strength_cache:
                score, s_color = self._strength_cache[cache_key]
            else:
                try:
                    pt = self.db.decrypt_password(entry, self.crypto)
                    sc = check_strength(pt)
                    s_color = sc["color"]
                    score   = sc["score"]
                except Exception:
                    s_color = "#718096"
                    score   = 2
                self._strength_cache[cache_key] = (score, s_color)
            fav = getattr(entry, "is_favorite", 0) or 0
            entry_data.append((entry, s_color, score, fav))

        # Sortuj: ulubione na górze
        entry_data.sort(key=lambda x: -x[3])

        dark = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
        for entry, s_color, score, fav in entry_data:
            cat_col = cat_color_map.get(entry.category or "Inne", "#718096")
            row = PasswordRowWidget(
                self._list_container,
                entry=entry,
                db=self.db,
                crypto=self.crypto,
                user=self.user,
                on_refresh=self._refresh,
                on_copy=self._on_copy,
                on_autotype=self._do_autotype,
                strength_color=s_color,
                strength_score=score,
                cat_color=cat_col,
                compact=self._compact_mode,
            )
            self._list_vl.addWidget(row)

        self._list_vl.addStretch()

    def _empty_lbl(self, text, size, dark, muted=False):
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col = "#888" if muted else ("#f0f0f0" if dark else "#1a1a1a")
        lbl.setStyleSheet(f"font-size: {size}px; color: {col}; {'font-weight: bold;' if not muted else ''} background: transparent; border: none;")
        return lbl

    def _get_category_colors(self) -> dict:
        if self._cat_colors_cache is None:
            self._cat_colors_cache = {}
        colors = {**{k: v["color"] or "#718096" for k, v in CATEGORIES.items()},
                  **self._cat_colors_cache}
        return colors

    def _search_local(self, query: str, entries: list) -> list:
        try:
            from rapidfuzz import fuzz
            q = query.lower()
            scored = []
            for e in entries:
                text = f"{e.title or ''} {e.username or ''} {e.url or ''}".lower()
                ratio = fuzz.partial_ratio(q, text)
                if ratio > 55 or q in text:
                    scored.append((e, ratio))
            scored.sort(key=lambda x: -x[1])
            return [e for e, _ in scored]
        except ImportError:
            q = query.lower()
            return [e for e in entries if q in (e.title or "").lower()
                    or q in (e.username or "").lower()]

    # ── Refresh / search ──────────────────────────────────────────────

    def _refresh(self, rebuild_sidebar: bool = False):
        self._cat_colors_cache = None
        self._strength_cache   = {}
        if rebuild_sidebar:
            self._cat_cache = None
            self._build_sidebar()
        else:
            self._build_sidebar()  # rebuild zawsze (lekki w Qt)
        query = self._search_entry.text().strip()
        self._load_passwords(query, animate=False)
        QTimer.singleShot(300, self._compute_security_score)

    def _on_search(self):
        self._load_passwords(self._search_entry.text().strip())

    # ── Add / edit password ───────────────────────────────────────────

    def _add_smart(self):
        """Dodaje hasło lub notatkę zależnie od aktywnej kategorii."""
        if self._active_category == "Notatki":
            self._add_note()
        else:
            self._add_password()

    def _add_note(self):
        dlg = NoteFormDialog(self, self.db, self.user)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result:
            self._refresh(rebuild_sidebar=True)

    def _add_password(self):
        dlg = PasswordFormDialog(self, self.db, self.crypto, self.user)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result:
            self._refresh(rebuild_sidebar=True)

    # ── Copy callback ─────────────────────────────────────────────────

    def _on_copy(self, title: str):
        if self._toast:
            self._toast.show(f"Skopiowano: {title}", "success")
        # Start clipboard timer
        secs = 30
        self._clipboard_secs = secs
        self._clipboard_entry_title = title
        self._clipboard_qt_timer.start()
        self._update_clipboard_label()

    def _tick_clipboard(self):
        self._clipboard_secs -= 1
        if self._clipboard_secs <= 0:
            self._clipboard_qt_timer.stop()
            try:
                pyperclip.copy("")
            except Exception:
                pass
            self._clipboard_lbl.setText("")
        else:
            self._update_clipboard_label()

    def _update_clipboard_label(self):
        accent = self._prefs.get_accent()
        self._clipboard_lbl.setStyleSheet(f"color: {accent}; font-size: 12px; background: transparent; border: none;")
        self._clipboard_lbl.setText(f"📋  {self._clipboard_entry_title}  ·  {self._clipboard_secs}s")

    # ── View modes ────────────────────────────────────────────────────

    def _toggle_compact(self):
        self._compact_mode = not self._compact_mode
        self._prefs.set("compact_mode", self._compact_mode)
        self._view_btn.setText("Kompaktowy" if self._compact_mode else "Normalny")
        self._load_passwords(self._search_entry.text().strip(), animate=False)

    # ── Auto-lock ─────────────────────────────────────────────────────

    def _check_lock(self):
        if self._locked:
            return
        timeout = self._prefs.get("auto_lock_seconds") or 0
        if timeout > 0 and (time.time() - self._last_activity) >= timeout:
            self._lock()

    def _reset_activity(self):
        self._last_activity = time.time()

    def mousePressEvent(self, event):
        self._reset_activity()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        self._reset_activity()
        super().keyPressEvent(event)

    def _lock(self):
        self._locked = True
        try:
            pyperclip.copy("")
        except Exception:
            pass
        self._clipboard_qt_timer.stop()
        self._clipboard_lbl.setText("")

        dlg = QDialog(self)
        dlg.setWindowTitle("Aplikacja zablokowana")
        dlg.setFixedSize(440, 300)
        dlg.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            # Bez WindowCloseButtonHint → brak przycisku X
            # Bez WindowStaysOnTopHint → nie wyskakuje nad inne aplikacje
        )
        dlg.reject = lambda: None  # blokuj Escape
        dlg.setStyleSheet("QDialog { background: #1e1e1e; color: #f0f0f0; } QLabel { background: transparent; border: none; color: #f0f0f0; }")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(30, 20, 30, 20)

        lock_icon = QLabel("🔒")
        lock_icon.setStyleSheet("font-size: 52px;")
        lock_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(lock_icon)

        vl.addWidget(self._empty_lbl("Aplikacja zablokowana", 18, True))
        vl.addWidget(self._empty_lbl("Wpisz hasło masterowe aby odblokować:", 12, True, muted=True))

        entry = QLineEdit()
        entry.setEchoMode(QLineEdit.EchoMode.Password)
        entry.setPlaceholderText("Hasło masterowe...")
        entry.setFixedHeight(42)
        entry.setStyleSheet("background: #2a2a2a; color: #f0f0f0; border: 1px solid #444; border-radius: 10px; padding: 0 12px; font-size: 13px;")
        vl.addWidget(entry)

        msg_lbl = QLabel("")
        msg_lbl.setStyleSheet("color: #e53e3e; font-size: 11px;")
        msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(msg_lbl)

        accent = self._prefs.get_accent()
        unlock_btn = QPushButton("Odblokuj")
        unlock_btn.setFixedHeight(42)
        unlock_btn.setStyleSheet(f"background: {accent}; color: white; border-radius: 10px; font-size: 13px; font-weight: bold; border: none;")
        vl.addWidget(unlock_btn)

        def _unlock():
            if verify_master_password(entry.text(), self.user.master_password_hash):
                self._locked = False
                self._last_activity = time.time()
                dlg.accept()
                self._lock_timer.start()
            else:
                msg_lbl.setText("Nieprawidłowe hasło!")
                entry.clear()
                shake(entry)

        unlock_btn.clicked.connect(_unlock)
        entry.returnPressed.connect(_unlock)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        QTimer.singleShot(200, entry.setFocus)
        dlg.exec()

    # ── Settings panel ────────────────────────────────────────────────

    def _precreate_settings(self):
        from gui_qt.settings_window import SettingsPanel
        self._settings_panel = SettingsPanel(
            self.centralWidget(),
            db=self.db,
            crypto=self.crypto,
            user=self.user,
            on_close=self._close_settings,
            on_logout=self._logout,
            on_theme_change=self._on_theme_change,
        )
        # Fall back to main-window dimensions if centralWidget hasn't been
        # laid out yet (returns 0 during the post-rebuild deferred call).
        w = self.centralWidget().width() or self.width()
        h = self.centralWidget().height() or self.height()
        self._settings_panel.setGeometry(w, 0, w, h)
        self._settings_panel.hide()

    def _open_settings(self):
        if self._settings_panel is None:
            self._precreate_settings()
        # Don't slide-in if already visible (e.g. deferred timer fires twice)
        if self._settings_panel.isVisible():
            return
        self._settings_panel.slide_in(self.centralWidget())

    def _close_settings(self):
        if self._settings_panel:
            self._settings_panel.slide_out()

    def _on_theme_change(self, theme_id: str):
        accent = self._prefs.get_accent()
        dark   = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
        app = get_app()
        if app:
            app.setStyleSheet(build_qss(accent, dark))
        # Defer rebuild — SettingsPanel jest dzieckiem centralWidget i wywołuje
        # tę metodę. Bezpośredni rebuild niszczyłby SettingsPanel w trakcie jego
        # własnego callbacku (use-after-free). QTimer.singleShot(0) czeka na
        # zakończenie bieżącego event loop frame.
        QTimer.singleShot(0, self._rebuild_and_reopen_settings)

    def _rebuild_and_reopen_settings(self):
        self._rebuild_ui()
        # Force layout computation so centralWidget has correct dimensions
        # before _precreate_settings reads width()/height().
        self.centralWidget().updateGeometry()
        QTimer.singleShot(300, self._open_settings)

    def _rebuild_ui(self):
        """Pełna przebudowa UI — po zmianie motywu lub koloru akcentu."""
        query   = self._search_entry.text().strip() if hasattr(self, '_search_entry') else ""
        cat     = self._active_category
        compact = self._compact_mode

        # Zatrzymaj animacje starego UI
        for attr in ('_top_sep', '_content_hex'):
            widget = getattr(self, attr, None)
            if widget and hasattr(widget, 'stop_animation'):
                try: widget.stop_animation()
                except Exception: pass

        # Zniszcz stary panel ustawień (zostanie odtworzony przy kolejnym otwarciu)
        self._settings_panel = None

        self._active_category = cat
        self._compact_mode    = compact

        self._build_ui()

        # Odtwórz toast i skróty po nowym centralWidget
        self._toast = ToastManager(self.centralWidget())
        self._setup_shortcuts()

        if hasattr(self, '_search_entry'):
            self._search_entry.setText(query)
        self._load_passwords(query, animate=False)
        QTimer.singleShot(100, self._position_content_hex)
        QTimer.singleShot(300, self._compute_security_score)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._position_content_hex)

    def _position_content_hex(self):
        scroll = getattr(self, '_list_scroll', None)
        hex_bg = getattr(self, '_content_hex', None)
        if scroll and hex_bg:
            vp = scroll.viewport()
            w, h = vp.width(), vp.height()
            if w > 0 and h > 0:
                hex_bg.setGeometry(0, 0, w, h)
                hex_bg.lower()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_content_hex()
        cw = self.centralWidget()
        if cw and self._settings_panel and not self._settings_panel.isHidden():
            self._settings_panel.setGeometry(0, 0, cw.width(), cw.height())

    # ── User menu ─────────────────────────────────────────────────────

    def _toggle_user_menu(self):
        dark = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
        accent = self._prefs.get_accent()
        if hasattr(self, "_user_menu_widget") and self._user_menu_widget:
            try:
                self._user_menu_widget.close()
                self._user_menu_widget = None
            except Exception:
                pass
            return

        menu = QFrame(self.centralWidget())
        menu.setWindowFlags(Qt.WindowType.Popup)
        menu.setFixedWidth(200)
        menu.setStyleSheet(f"background: {'#1e1e1e' if dark else '#fff'}; border: 1px solid {'#444' if dark else '#ccc'}; border-radius: 10px;")
        ml = QVBoxLayout(menu)
        ml.setContentsMargins(0, 6, 0, 6)
        ml.setSpacing(0)

        for text, callback in [
            (f"👤  {self.user.username}", None),
            ("⚙️  Ustawienia", self._open_settings),
            ("🔒  Zablokuj", self._lock),
            ("🔄  Synchronizacja", self._open_sync),
            ("🚪  Wyloguj", self._logout),
        ]:
            btn = QPushButton(text)
            btn.setFixedHeight(38)
            is_header = callback is None
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none; text-align: left;
                    padding: 0 16px; font-size: 13px;
                    color: {accent if is_header else ('#f0f0f0' if dark else '#1a1a1a')};
                    {'font-weight: bold;' if is_header else ''}
                }}
                QPushButton:hover {{ background: {'#2a2a2a' if dark and not is_header else 'transparent' if is_header else '#f0f0f0'}; }}
            """)
            if callback:
                btn.clicked.connect(lambda _, c=callback: (menu.close(), c()))
            ml.addWidget(btn)

        # Pozycja przy user_btn (globalna — menu jest top-level Popup)
        pos = self.user_btn.mapToGlobal(self.user_btn.rect().bottomLeft())
        menu.move(pos.x(), pos.y() + 4)
        menu.show()
        self._user_menu_widget = menu

    # ── Theme toggle ──────────────────────────────────────────────────

    def _toggle_theme(self):
        dark = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
        new_dark = not dark
        self._prefs.set("appearance_mode", "dark" if new_dark else "light")
        apply_theme(dark=new_dark)
        self._rebuild_ui()

    # ── Shortcuts ─────────────────────────────────────────────────────

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self._add_password)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(lambda: (self._search_entry.setFocus(), self._search_entry.selectAll()))
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self._lock)
        QShortcut(QKeySequence("Ctrl+W"), self).activated.connect(self._ctrl_w)
        QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(self._autotype_first)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self._duplicate_first)
        QShortcut(QKeySequence("?"),      self).activated.connect(self._show_shortcuts)

    def _ctrl_w(self):
        action = self._prefs.get("ctrl_w_action") or "minimize"
        if action == "close":
            self.close()
        else:
            if self._tray:
                self.hide()
            else:
                self.showMinimized()

    def _autotype_first(self):
        for i in range(self._list_vl.count()):
            item = self._list_vl.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), PasswordRowWidget):
                self._do_autotype(item.widget().entry)
                return
        if self._toast:
            self._toast.show("Brak widocznych haseł do Auto-type", "warning")

    def _duplicate_first(self):
        for i in range(self._list_vl.count()):
            item = self._list_vl.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), PasswordRowWidget):
                entry = item.widget().entry
                try:
                    plain = self.db.decrypt_password(entry, self.crypto)
                    self.db.add_password(
                        self.user, self.crypto,
                        title=f"Kopia — {entry.title}",
                        username=entry.username or "",
                        plaintext_password=plain,
                        url=entry.url or "", notes=entry.notes or "",
                        category=entry.category or "Inne",
                        expires_at=entry.expires_at,
                    )
                    self._refresh()
                    if self._toast:
                        self._toast.show(f"Zduplikowano: {entry.title}", "success")
                except Exception:
                    pass
                return

    def _show_shortcuts(self):
        dark = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
        dlg = QDialog(self)
        dlg.setWindowTitle("Skróty klawiszowe")
        dlg.setFixedSize(480, 360)
        dlg.setStyleSheet(f"QDialog {{ background: {'#1e1e1e' if dark else '#f8f8f8'}; }} QLabel {{ background: transparent; border: none; color: {'#f0f0f0' if dark else '#1a1a1a'}; }}")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 16, 20, 16)
        accent = self._prefs.get_accent()
        title = QLabel("Skróty klawiszowe")
        title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {accent};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(title)
        shortcuts = [
            ("Ctrl + N", "Dodaj nowe hasło"),
            ("Ctrl + F", "Szukaj haseł"),
            ("Ctrl + L", "Zablokuj aplikację"),
            ("Ctrl + W", "Minimalizuj / Zamknij"),
            ("Ctrl + T", "Auto-type pierwszego hasła"),
            ("Ctrl + D", "Duplikuj pierwsze hasło"),
            ("?",        "Pokaż/ukryj ten ekran"),
        ]
        for key, desc in shortcuts:
            row = QWidget()
            row.setStyleSheet(f"background: {'#252525' if dark else '#f0f0f0'}; border-radius: 6px; border: none;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)
            k = QLabel(key)
            k.setStyleSheet(f"color: {accent}; font-family: 'Courier New', monospace; font-size: 12px; font-weight: bold; min-width: 100px;")
            rl.addWidget(k)
            d = QLabel(desc)
            d.setStyleSheet(f"color: {'#f0f0f0' if dark else '#1a1a1a'}; font-size: 12px;")
            rl.addWidget(d)
            rl.addStretch()
            vl.addWidget(row)
        vl.addStretch()
        dlg.exec()

    # ── Auto-type ─────────────────────────────────────────────────────

    def _do_autotype(self, entry):
        try:
            password = self.db.decrypt_password(entry, self.crypto)
        except Exception:
            if self._toast:
                self._toast.show("Błąd deszyfrowania — Auto-type anulowany", "error")
            return
        username = entry.username or ""
        delay_s  = float(self._prefs.get("autotype_delay") or 2)
        sequence = self._prefs.get("autotype_sequence") or "{USERNAME}{TAB}{PASSWORD}{ENTER}"
        if self._toast:
            self._toast.show(f"Auto-type za {int(delay_s)}s — przełącz okno", "info",
                             duration=int(delay_s * 1000) + 800)

        def _type_worker():
            import time as _t
            _t.sleep(delay_s)
            try:
                from pynput.keyboard import Key, Controller
                kb = Controller()
                i = 0
                while i < len(sequence):
                    if sequence[i] == '{':
                        end = sequence.find('}', i)
                        if end == -1:
                            i += 1
                            continue
                        token = sequence[i+1:end].upper()
                        if token == 'USERNAME':    kb.type(username)
                        elif token == 'PASSWORD':  kb.type(password)
                        elif token == 'TAB':       _t.sleep(0.06); kb.press(Key.tab); kb.release(Key.tab)
                        elif token == 'ENTER':     _t.sleep(0.06); kb.press(Key.enter); kb.release(Key.enter)
                        elif token.startswith('DELAY='):
                            try: _t.sleep(int(token[6:]) / 1000)
                            except ValueError: pass
                        i = end + 1
                    else:
                        kb.type(sequence[i]); i += 1
            except Exception:
                pass

        threading.Thread(target=_type_worker, daemon=True).start()

    # ── Category management ───────────────────────────────────────────

    def _add_category(self):
        dlg = CategoryDialog(self, self.db, self.user,
                             on_created=lambda _: self._refresh(rebuild_sidebar=True))
        dlg.exec()

    # ── Trash / backup ────────────────────────────────────────────────

    def _open_trash(self):
        dlg = TrashDialog(self, self.db, self.crypto, self.user,
                          on_refresh=lambda: self._refresh(rebuild_sidebar=True))
        dlg.exec()

    def _export(self):
        ExportDialog(self, self.db, self.crypto, self.user).exec()

    def _import_aegis(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import .aegis", "", "AegisVault Backup (*.aegis)"
        )
        if path:
            try:
                from utils.import_manager import import_passwords_aegis
                count = import_passwords_aegis(self.db, self.crypto, self.user, path)
                show_success("Import", f"Zaimportowano {count} haseł.", parent=self)
                self._refresh(rebuild_sidebar=True)
            except Exception as e:
                show_error("Błąd importu", str(e), parent=self)

    def _import_external(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import zewnętrzny", "", "CSV / JSON (*.csv *.json)"
        )
        if not path:
            return
        try:
            from utils.import_manager import ImportManager
            mgr = ImportManager(self.db, self.crypto, self.user)
            count = mgr.import_file(path)
            show_success("Import", f"Zaimportowano {count} haseł.", parent=self)
            self._refresh(rebuild_sidebar=True)
        except Exception as e:
            show_error("Błąd importu", str(e), parent=self)

    # ── Security score ────────────────────────────────────────────────

    def _compute_security_score(self):
        def _worker():
            try:
                result = _sec_score.calculate(self.db, self.crypto, self.user)
                self._score_ready_sig.emit(result.get("score", 0))
            except Exception as e:
                logger.warning(f"Security score failed: {e}")
        threading.Thread(target=_worker, daemon=True).start()

    def _on_score_ready(self, score: int):
        if self._score_ring:
            self._score_ring.animate_to(score)

    # ── Sync status ───────────────────────────────────────────────────

    def _sync_ping(self):
        def _check():
            try:
                connected = SyncClient().is_connected()
            except Exception:
                connected = False
            self._sync_status_sig.emit(connected)
        threading.Thread(target=_check, daemon=True).start()
        QTimer.singleShot(30_000, self._sync_ping)

    def _on_sync_status(self, connected: bool):
        if self._sync_connected == connected:
            return
        self._sync_connected = connected
        color = "#4caf50" if connected else "#555555"
        self._sync_dot.setStyleSheet(f"color: {color}; font-size: 10px; background: transparent; border: none;")

    def _open_sync(self):
        try:
            from gui_qt.sync_window import SyncWindow
            from utils.sync_client import SyncClient
            dlg = SyncWindow(
                self, self.db, self.crypto, self.user,
                sync_client=SyncClient(),
                on_refresh=self._refresh,
            )
            dlg.exec()
        except Exception as e:
            logger.error(f"Sync window error: {e}")
            show_info("Synchronizacja", f"Błąd otwarcia okna synchronizacji:\n{e}", parent=self)

    # ── Update ────────────────────────────────────────────────────────

    def _bg_check_update(self):
        info = check_for_update()
        if info:
            self._update_found_sig.emit(info)
        else:
            QTimer.singleShot(4 * 60 * 60 * 1000,
                              lambda: threading.Thread(target=self._bg_check_update, daemon=True).start())

    def _on_update_found(self, info: dict):
        self._update_info = info
        if self._update_btn:
            self._update_btn.setVisible(True)
            self._update_btn.setToolTip(f"Nowa wersja: {info.get('version', '?')}")

    def _open_update_dialog(self):
        try:
            from gui_qt.update_dialog import UpdateDialog
            dlg = UpdateDialog(self, self._update_info)
            dlg.exec()
        except ImportError:
            if self._update_info:
                url = self._update_info.get("url", "")
                if url:
                    webbrowser.open(url)

    def _maybe_show_changelog(self):
        try:
            from version import APP_VERSION, APP_CHANGELOG
            prefs = PrefsManager()
            last = prefs.get("last_seen_version")
            prefs.set("last_seen_version", APP_VERSION)
            if last and last != APP_VERSION:
                from gui_qt.changelog_dialog import ChangelogDialog
                ChangelogDialog(self, APP_VERSION, APP_CHANGELOG,
                                accent=self._prefs.get_accent()).exec()
        except Exception:
            pass

    def _check_auto_backup(self):
        from utils.auto_backup import should_backup, do_backup
        if not should_backup(self._prefs):
            return
        def _worker():
            try:
                path = do_backup(self.db, self.crypto, self.user, self._prefs)
                if path and self._toast:
                    fname = os.path.basename(path)
                    QTimer.singleShot(0, lambda: self._toast.show(
                        f"Auto-backup zapisany: {fname}", "info", duration=4000
                    ))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    # ── Security analysis ─────────────────────────────────────────────

    def _open_analysis(self):
        try:
            from gui_qt.security_analysis_window import SecurityAnalysisWindow
            dlg = SecurityAnalysisWindow(self, self.db, self.crypto, self.user)
            dlg.exec()
        except ImportError:
            show_info("Analiza bezpieczeństwa", "Okno analizy nie jest jeszcze dostępne.", parent=self)

    # ── Logout ────────────────────────────────────────────────────────

    def _logout(self):
        self._cleanup()
        self.close()
        # LoginWindow uruchomi się przez main.py po powrocie
        QApplication.quit()
