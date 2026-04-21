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
  PasswordFormPanel   — slide-in panel dodawania / edycji hasła (gui_qt/panels.py)
  NoteFormPanel       — slide-in panel dodawania / edycji notatki
  CategoryPanel       — slide-in panel nowej kategorii
  TrashPanel          — slide-in panel kosza
  ExportPanel         — slide-in panel eksportu
  MainWindow          — okno główne
"""

import os
import platform
import threading
import time
import webbrowser
import pyperclip
from utils.clipboard import copy_sensitive
from datetime import datetime, timezone
from PIL import Image

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QLineEdit, QScrollArea, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTextEdit, QComboBox, QSlider, QCheckBox, QDialog,
    QSizePolicy, QStackedWidget, QProgressBar, QFileDialog,
    QButtonGroup, QApplication, QListWidget,
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
from gui_qt.panels         import (
    PasswordFormPanel, NoteFormPanel, CategoryPanel, TrashPanel, ExportPanel,
)
from utils.i18n            import t

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
# PasswordRowWidget — wiersz hasła
# ══════════════════════════════════════════════════════════════════════

class PasswordRowWidget(QFrame):
    def __init__(self, parent, entry, db, crypto, user,
                 on_refresh, on_copy, on_autotype=None,
                 on_select=None,
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
        self.on_select      = on_select
        self._checkbox: QCheckBox | None = None
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

        # Checkbox do bulk selection (ukryty domyślnie)
        self._checkbox = QCheckBox()
        self._checkbox.setVisible(False)
        self._checkbox.setStyleSheet(
            "QCheckBox { margin: 0 4px 0 2px; background: transparent; border: none; }"
            "QCheckBox::indicator { width: 16px; height: 16px; border-radius: 3px; }"
        )
        if self.on_select:
            self._checkbox.stateChanged.connect(
                lambda state: self.on_select(self.entry.id, bool(state))
            )
        rl.addWidget(self._checkbox)

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
            title_lbl = QLabel(entry.title or "—")
            title_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {_text_col}; background: transparent; border: none;")
            trl.addWidget(title_lbl)
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
            title_lbl = QLabel(entry.title or "—")
            title_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {_text_col}; background: transparent; border: none;")
            trl.addWidget(title_lbl)
            # Expiry badge
            exp = getattr(entry, "expiry_status", None)
            if exp in ("expired", "soon"):
                _exp = entry.expires_at
                if _exp and _exp.tzinfo is None:
                    _exp = _exp.replace(tzinfo=timezone.utc)
                days = max(0, (_exp - datetime.now(timezone.utc)).days) if _exp else 0
                exp_lbl = QLabel(t("pw.expired") if exp == "expired" else t("pw.expires_in", n=days))
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
        fav_btn.setToolTip(t("pw.fav_add") if not fav_active else t("pw.fav_remove"))
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
                f"  font-family: 'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji','Segoe UI',sans-serif;"
                f"  padding: 0 {'6px' if compact else '10px'}; min-height: 0; min-width: 0;"
                f"}}"
            )
            if tooltip:
                b.setToolTip(tooltip)
            b.clicked.connect(callback)
            brl.addWidget(b)
            return b

        # ── Kopiuj hasło ─────────────────────────────────────────────
        _action_btn("📋", t("pw.copy"), accent, "#ffffff", self._copy, "Kopiuj hasło (Ctrl+C)")

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
                f" font-size: 15px; font-family: 'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',sans-serif;"
                f" padding: 0; min-height: 0; min-width: 0; }}"
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
            # Live OTP timer — parent=self zapewnia auto-stop przy deleteLater()
            self._otp_timer = QTimer(self)
            self._otp_timer.timeout.connect(self._refresh_otp_btn)
            self._otp_timer.start(1000)
            self.destroyed.connect(self._otp_timer.stop)
            self._refresh_otp_btn()

        # ── Edytuj ───────────────────────────────────────────────────
        _bg_edit = "#2a2a2a" if self._dark else "#e8e8e8"
        _fg_edit = "#cccccc" if self._dark else "#444444"
        _action_btn("✎", t("pw.edit"), _bg_edit, _fg_edit, self._edit, "Edytuj wpis")

        # ── Kosz ─────────────────────────────────────────────────────
        _action_btn("🗑", t("pw.trash"), "#3a1a1a" if self._dark else "#fde8e8",
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
            copy_sensitive(code)
            self.db.log_event(self.user, "otp_copied",
                              entry_id=self.entry.id, details=self.entry.title)
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

        # Checkbox do bulk selection (ukryty domyślnie)
        self._checkbox = QCheckBox()
        self._checkbox.setVisible(False)
        self._checkbox.setStyleSheet(
            "QCheckBox { margin: 0 4px 0 2px; background: transparent; border: none; }"
            "QCheckBox::indicator { width: 16px; height: 16px; border-radius: 3px; }"
        )
        if self.on_select:
            self._checkbox.stateChanged.connect(
                lambda state: self.on_select(self.entry.id, bool(state))
            )
        rl.addWidget(self._checkbox)

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

    def set_bulk_mode(self, active: bool):
        if self._checkbox:
            self._checkbox.setVisible(active)

    def set_checked(self, checked: bool):
        if self._checkbox:
            self._checkbox.blockSignals(True)
            self._checkbox.setChecked(checked)
            self._checkbox.blockSignals(False)

    def is_checked(self) -> bool:
        return bool(self._checkbox and self._checkbox.isChecked())

    def _edit_note(self):
        win = self.window()
        parent = win.centralWidget() if hasattr(win, "centralWidget") else win
        user = win.user if hasattr(win, "user") else self.user
        NoteFormPanel(parent, self.db, user, self.entry, on_saved=self.on_refresh).open()

    def _copy(self):
        try:
            plaintext = self.db.decrypt_password(self.entry, self.crypto)
            copy_sensitive(plaintext)
            self.db.mark_used(self.entry)
            self.db.log_event(self.user, "password_copied",
                              entry_id=self.entry.id, details=self.entry.title)
            if self.on_copy:
                self.on_copy(self.entry.title)
        except Exception:
            pass

    def _copy_username(self):
        if self.entry.username:
            try:
                copy_sensitive(self.entry.username)
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
        win = self.window()
        parent = win.centralWidget() if hasattr(win, "centralWidget") else win
        PasswordFormPanel(parent, self.db, self.crypto, self.user, self.entry, on_saved=self.on_refresh).open()

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
    _no_update_sig     = pyqtSignal()
    _sync_status_sig   = pyqtSignal(bool)
    _score_ready_sig   = pyqtSignal(int)
    _backup_done_sig   = pyqtSignal(str)   # filename

    # Emitowany przy wylogowaniu w trybie embedded (zamiast zamykania okna)
    logout_requested   = pyqtSignal()

    def __init__(self, db: DatabaseManager, crypto: CryptoManager, user,
                 embedded: bool = False):
        super().__init__()
        self.db       = db
        self.crypto   = crypto
        self.user     = user
        self._prefs   = PrefsManager()
        self._embedded = embedded

        self._active_category    = "Wszystkie"
        self._compact_mode       = self._prefs.get("compact_mode") or False
        self._last_activity      = time.time()
        self._locked             = False
        self._clipboard_secs     = 0
        self._score_ring: AnimatedScoreRing | None = None
        self._settings_panel     = None
        self._tray               = None
        self._toast: ToastManager | None = None
        self._update_btn: QPushButton | None = None
        self._update_info        = None
        self.logged_out          = False
        self._sync_connected     = None
        self._bulk_mode          = False
        self._selected_ids: set[int] = set()
        self._row_widgets: list      = []
        self._sort_by            = self._prefs.get("sort_by") or "name"
        self._sort_asc           = self._prefs.get("sort_asc") if self._prefs.get("sort_asc") is not None else True
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

        # Generator state (hasło losowe)
        self._gen_length  = 16
        self._gen_upper   = True
        self._gen_digits  = True
        self._gen_special = True
        self._gen_pwd     = ""
        # Generator state (diceware)
        self._dice_count  = 5
        self._dice_sep    = "-"
        self._dice_cap    = False
        self._dice_phrase = ""

        # Connect signals
        self._update_found_sig.connect(self._on_update_found)
        self._no_update_sig.connect(self._on_no_update)
        self._sync_status_sig.connect(self._on_sync_status)
        self._score_ready_sig.connect(self._on_score_ready)
        self._backup_done_sig.connect(
            lambda fname: self._toast and self._toast.show(
                f"Auto-backup zapisany: {fname}", "info", duration=4000
            )
        )

        if not self._embedded:
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

        # Screen capture protection
        if self._prefs.get("screen_capture_protection"):
            QTimer.singleShot(200, lambda: self.apply_screen_capture_protection(True))

        # Background tasks
        threading.Thread(target=lambda: (
            self.db.purge_old_trash(self.user),
            self.db.purge_old_audit(self.user),
        ), daemon=True).start()
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

    def apply_screen_capture_protection(self, enable: bool) -> None:
        """Włącza/wyłącza WDA_EXCLUDEFROMCAPTURE (Windows 10 2004+)."""
        import sys
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            WDA_NONE               = 0x00000000
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            ctypes.windll.user32.SetWindowDisplayAffinity(
                hwnd, WDA_EXCLUDEFROMCAPTURE if enable else WDA_NONE
            )
        except Exception as e:
            logger.warning(f"SetWindowDisplayAffinity failed: {e}")

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
        self._search_entry.setPlaceholderText(t("main.search_placeholder"))
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

        # Update badge (ukryty dopóki nie ma aktualizacji)
        self._update_btn = QPushButton(t("main.new_version"))
        self._update_btn.setFixedHeight(32)
        self._update_btn.setStyleSheet("""
            QPushButton {
                background: #92400e;
                color: #fde68a;
                border: 1px solid #d97706;
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
                padding: 0 12px;
            }
            QPushButton:hover {
                background: #b45309;
                border-color: #f59e0b;
                color: #fff;
            }
        """)
        self._update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn.clicked.connect(self._open_update_dialog)
        self._update_btn.setVisible(False)
        tl.addWidget(self._update_btn)

        # Theme toggle
        self._theme_btn = QPushButton("🌙" if dark else "☀")
        self._theme_btn.setFixedSize(36, 36)
        self._theme_btn.setStyleSheet(
            f"background: {_blend(accent, bg, 0.22)}; border: 1px solid {accent}; "
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
            QPushButton:hover {{ background: {_blend(accent, bg, 0.15)}; }}
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

        self._count_lbl = QLabel(t("main.n_passwords", n=0))
        self._count_lbl.setStyleSheet(f"color: {'#888' if dark else '#666'}; font-size: 12px; background: transparent; border: none;")
        toll.addWidget(self._count_lbl)
        toll.addStretch()

        # Sort combobox
        _sort_opts = [
            ("name_asc",      t("main.sort_name_asc")),
            ("name_desc",     t("main.sort_name_desc")),
            ("used_desc",     t("main.sort_used_desc")),
            ("strength_desc", t("main.sort_strength_desc")),
            ("strength_asc",  t("main.sort_strength_asc")),
            ("created_desc",  t("main.sort_created_desc")),
            ("created_asc",   t("main.sort_created_asc")),
        ]
        self._sort_combo = QComboBox()
        self._sort_combo.setFixedHeight(28)
        self._sort_combo.setStyleSheet(
            f"QComboBox {{ background: {'#2a2a2a' if dark else '#e8e8e8'}; color: {'#f0f0f0' if dark else '#1a1a1a'}; "
            f"border-radius: 6px; font-size: 11px; border: none; padding: 0 8px; }}"
            f"QComboBox::drop-down {{ border: none; width: 18px; }}"
            f"QComboBox QAbstractItemView {{ background: {'#2a2a2a' if dark else '#fff'}; "
            f"selection-background-color: {accent}; border: none; }}"
        )
        _cur_key = (self._sort_by + ("_asc" if self._sort_asc else "_desc"))
        for key, label in _sort_opts:
            self._sort_combo.addItem(label, key)
        _idx = next((i for i, (k, _) in enumerate(_sort_opts) if k == _cur_key), 0)
        self._sort_combo.setCurrentIndex(_idx)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        toll.addWidget(self._sort_combo)
        toll.addSpacing(8)

        # Clipboard label
        self._clipboard_lbl = QLabel("")
        self._clipboard_lbl.setStyleSheet(f"color: {accent}; font-size: 12px; background: transparent; border: none;")
        toll.addWidget(self._clipboard_lbl)
        toll.addSpacing(12)

        # Widok
        self._view_btn = QPushButton(t("main.view_compact") if self._compact_mode else t("main.view_normal"))
        self._view_btn.setFixedHeight(32)
        self._view_btn.setStyleSheet(f"background: {'#2a2a2a' if dark else '#e8e8e8'}; color: {'#f0f0f0' if dark else '#1a1a1a'}; border-radius: 8px; font-size: 12px; padding: 0 12px; border: none;")
        self._view_btn.clicked.connect(self._toggle_compact)
        toll.addWidget(self._view_btn)

        # Dodaj hasło / notatkę (zależnie od aktywnej kategorii)
        self._add_btn = QPushButton(t("main.btn_add"))
        self._add_btn.setFixedHeight(32)
        self._add_btn.setStyleSheet(f"background: {accent}; color: white; border-radius: 8px; font-size: 12px; font-weight: bold; padding: 0 12px; border: none;")
        self._add_btn.clicked.connect(self._add_smart)
        toll.addWidget(self._add_btn)

        _btn_bg = "#2a2a2a" if dark else "#e8e8e8"
        _btn_fg = "#f0f0f0" if dark else "#1a1a1a"
        self._bulk_btn = QPushButton(t("main.btn_select"))
        self._bulk_btn.setFixedHeight(32)
        self._bulk_btn.setStyleSheet(
            f"background: {_btn_bg}; color: {_btn_fg}; border-radius: 8px; "
            f"font-size: 12px; padding: 0 12px; border: none;"
        )
        self._bulk_btn.clicked.connect(self._toggle_bulk_mode)
        toll.addWidget(self._bulk_btn)

        cl.addWidget(toolbar)

        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background: {'#2a2a2a' if dark else '#d0d0d0'}; border: none;")
        cl.addWidget(sep2)

        # Pasek bulk akcji (ukryty dopóki bulk_mode=False)
        _bulk_bg  = "#1a2a1a" if dark else "#e8f5e9"
        _bulk_fg  = "#7ec87e" if dark else "#2d6a4f"
        self._bulk_bar = QFrame()
        self._bulk_bar.setFixedHeight(44)
        self._bulk_bar.setStyleSheet(f"background: {_bulk_bg}; border: none;")
        self._bulk_bar.setVisible(False)
        bbl = QHBoxLayout(self._bulk_bar)
        bbl.setContentsMargins(12, 4, 12, 4)
        bbl.setSpacing(8)

        self._bulk_count_lbl = QLabel(t("main.bulk_selected", n=0))
        self._bulk_count_lbl.setStyleSheet(
            f"color: {_bulk_fg}; font-size: 12px; font-weight: bold; background: transparent; border: none;"
        )
        bbl.addWidget(self._bulk_count_lbl)
        bbl.addStretch()

        for txt, cb, sty in [
            (t("main.bulk_select_all"), self._bulk_select_all,
             f"background: transparent; color: {'#7ab8f5' if dark else '#1a5080'}; "
             f"border: 1px solid {'#444' if dark else '#ccc'}; border-radius: 6px; "
             f"font-size: 11px; padding: 0 8px; min-height: 0;"),
            (t("main.bulk_delete"), self._bulk_trash,
             f"background: {'#3a1a1a' if dark else '#fde8e8'}; color: {'#ff7070' if dark else '#c0392b'}; "
             f"border: none; border-radius: 6px; font-size: 11px; font-weight: 500; padding: 0 10px; min-height: 0;"),
            (t("main.bulk_move"), self._bulk_move,
             f"background: {'#1a2a3a' if dark else '#dbeafe'}; color: {'#7ab8f5' if dark else '#1a4a80'}; "
             f"border: none; border-radius: 6px; font-size: 11px; font-weight: 500; padding: 0 10px; min-height: 0;"),
            (t("main.bulk_cancel"), self._toggle_bulk_mode,
             f"background: transparent; color: {'#aaa' if dark else '#666'}; "
             f"border: 1px solid {'#444' if dark else '#ccc'}; border-radius: 6px; "
             f"font-size: 11px; padding: 0 8px; min-height: 0;"),
        ]:
            b = QPushButton(txt)
            b.setFixedHeight(28)
            b.setStyleSheet(sty)
            b.clicked.connect(cb)
            bbl.addWidget(b)

        cl.addWidget(self._bulk_bar)

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
        self._cat_section_label(vl, t("sidebar.section_categories"), dark)
        if self._cat_cache is None:
            self._cat_cache = self.db.get_all_categories(self.user)
        cat_icons = self.db.get_category_icons(self.user)
        default_set = set(DEFAULT_CATEGORIES)

        _cat_i18n = {
            "Wszystkie": "cat.all", "Praca": "cat.work", "Bankowość": "cat.banking",
            "Rozrywka": "cat.entertainment", "Inne": "cat.other",
            "Wygasające": "cat.expiring", "Notatki": "cat.notes",
        }
        self._cat_buttons: dict[str, QPushButton] = {}
        for cat in ["Wszystkie"] + self._cat_cache:
            icon     = CATEGORIES.get(cat, {}).get("icon") or cat_icons.get(cat, "🏷")
            n        = counts.get(cat, 0)
            disp     = t(_cat_i18n[cat]) if cat in _cat_i18n else cat
            label    = f"{icon} {disp}  ({n})" if n > 0 else f"{icon} {disp}"
            deletable = cat not in default_set and cat != "Wszystkie"
            self._add_cat_btn(vl, cat, label, deletable, dark, accent)

        # Dodaj kategorię
        new_cat_btn = self._sidebar_btn(t("sidebar.new_category"), "#888", dark)
        new_cat_btn.clicked.connect(self._add_category)
        vl.addWidget(new_cat_btn)
        self._sidebar_sep(vl, dark)

        # SPECJALNE
        self._cat_section_label(vl, t("sidebar.section_special"), dark)

        notes_count = len(self.db.get_all_notes(self.user))
        notes_base  = t("sidebar.notes")
        notes_txt   = notes_base + (f"  ({notes_count})" if notes_count else "")
        notes_btn   = self._sidebar_btn(notes_txt, "#5a67d8" if notes_count else "#888", dark)
        notes_btn.clicked.connect(lambda: self._filter_category("Notatki"))
        vl.addWidget(notes_btn)

        exp_count = len(self.db.get_expiring_passwords(self.user))
        exp_base  = t("sidebar.expiring")
        exp_txt   = exp_base + (f"  ({exp_count})" if exp_count else "")
        exp_btn   = self._sidebar_btn(exp_txt, "#f0a500" if exp_count else "#888", dark)
        exp_btn.clicked.connect(lambda: self._filter_category("Wygasające"))
        vl.addWidget(exp_btn)

        trash_count = len(self.db.get_trashed_passwords(self.user))
        trash_base  = t("sidebar.trash")
        trash_txt   = trash_base + (f"  ({trash_count})" if trash_count else "")
        trash_btn   = self._sidebar_btn(trash_txt, "#e05252" if trash_count else "#888", dark)
        trash_btn.clicked.connect(self._open_trash)
        vl.addWidget(trash_btn)
        self._sidebar_sep(vl, dark)

        # BACKUP
        self._cat_section_label(vl, t("sidebar.section_backup"), dark)
        for txt, cmd in [
            (t("sidebar.export"),          self._export),
            (t("sidebar.import_aegis"),    self._import_aegis),
            (t("sidebar.import_external"), self._import_external),
        ]:
            b = self._sidebar_btn(txt, "#888", dark)
            b.clicked.connect(cmd)
            vl.addWidget(b)
        self._sidebar_sep(vl, dark)

        # GENERATOR
        self._cat_section_label(vl, t("sidebar.section_generator"), dark)
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
                font-family: 'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji','Segoe UI',sans-serif;
            }}
            QPushButton:hover {{ background: {'#2a2a2a' if dark else '#e0e0e0'}; }}
        """)
        return btn

    _EMOJI_FONT_CSS = "font-family: 'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji','Segoe UI',sans-serif;"

    @staticmethod
    def _cat_btn_style(cat_color, active, dark, accent):
        _ef = MainWindow._EMOJI_FONT_CSS
        if active:
            return f"""
                QPushButton {{
                    background: {_blend(cat_color or accent, '#161616' if dark else '#f0f0f0', 0.25)};
                    border-left: 3px solid {cat_color or accent};
                    border-right: none; border-top: none; border-bottom: none;
                    text-align: left; color: {'#f0f0f0' if dark else '#1a1a1a'};
                    font-size: 12px; padding: 0 10px; border-radius: 0; {_ef}
                }}
            """
        return f"""
            QPushButton {{
                background: transparent; border: none; text-align: left;
                color: {'#d0d0d0' if dark else '#333'}; font-size: 12px;
                padding: 0 10px; border-radius: 8px; {_ef}
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

        # ── Przełącznik tabów ─────────────────────────────────────────
        tab_row = QWidget()
        tab_row.setStyleSheet("background: transparent; border: none;")
        trl = QHBoxLayout(tab_row)
        trl.setContentsMargins(0, 0, 0, 4)
        trl.setSpacing(2)
        _tab_active   = f"background: {accent}; color: white; border-radius: 5px; font-size: 10px; font-weight: bold; border: none; padding: 2px 6px; min-height: 0;"
        _tab_inactive = f"background: {'#333' if dark else '#d0d0d0'}; color: {'#aaa' if dark else '#666'}; border-radius: 5px; font-size: 10px; border: none; padding: 2px 6px; min-height: 0;"
        self._tab_pwd  = QPushButton(t("gen.random"))
        self._tab_dice = QPushButton(t("gen.passphrase"))
        for b in (self._tab_pwd, self._tab_dice):
            b.setFixedHeight(22)
            trl.addWidget(b)
        trl.addStretch()
        gl.addWidget(tab_row)

        # ── Stack — dwa panele ────────────────────────────────────────
        self._gen_stack = QStackedWidget()
        self._gen_stack.setStyleSheet("background: transparent; border: none;")

        # Panel 1: hasło losowe
        pwd_panel = QWidget()
        pwd_panel.setStyleSheet("background: transparent; border: none;")
        pl = QVBoxLayout(pwd_panel)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(4)

        len_row = QWidget()
        len_row.setStyleSheet("background: transparent; border: none;")
        lrl = QHBoxLayout(len_row)
        lrl.setContentsMargins(0, 0, 0, 0)
        len_lbl = QLabel(t("gen.length"))
        len_lbl.setStyleSheet(f"color: {'#f0f0f0' if dark else '#1a1a1a'}; font-size: 11px; background: transparent; border: none;")
        lrl.addWidget(len_lbl)
        lrl.addStretch()
        self._gen_len_lbl = QLabel(str(self._gen_length))
        self._gen_len_lbl.setStyleSheet(f"color: {accent}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        lrl.addWidget(self._gen_len_lbl)
        pl.addWidget(len_row)

        self._gen_slider = QSlider(Qt.Orientation.Horizontal)
        self._gen_slider.setRange(8, 64)
        self._gen_slider.setValue(self._gen_length)
        _slider_sty = f"""
            QSlider::groove:horizontal {{ background: {'#444' if dark else '#ccc'}; height: 4px; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {accent}; width: 12px; height: 12px; border-radius: 6px; margin: -4px 0; }}
            QSlider::sub-page:horizontal {{ background: {accent}; height: 4px; border-radius: 2px; }}
        """
        self._gen_slider.setStyleSheet(_slider_sty)
        self._gen_slider.valueChanged.connect(self._gen_slider_changed)
        pl.addWidget(self._gen_slider)

        _check_svg = os.path.join(_ASSETS_DIR, "check.svg").replace("\\", "/")
        _cb_sty = f"""
            QCheckBox {{ color: {'#d0d0d0' if dark else '#444'}; font-size: 11px; background: transparent; spacing: 6px; }}
            QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {'#666' if dark else '#aaa'}; border-radius: 3px; background: {'#2a2a2a' if dark else '#fff'}; }}
            QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url("{_check_svg}"); }}
        """
        for label, attr in [(t("gen.uppercase"), "_gen_upper"), (t("gen.digits"), "_gen_digits"), (t("gen.special"), "_gen_special")]:
            cb = QCheckBox(label)
            cb.setChecked(getattr(self, attr))
            cb.setStyleSheet(_cb_sty)
            cb.stateChanged.connect(lambda state, a=attr: setattr(self, a, bool(state)))
            pl.addWidget(cb)

        self._gen_out = QLabel("—")
        self._gen_out.setWordWrap(True)
        self._gen_out.setStyleSheet(f"color: {'#90c090' if dark else '#2d6a4f'}; font-size: 11px; font-family: 'Courier New', monospace; background: transparent; border: none;")
        pl.addWidget(self._gen_out)

        brl1 = QHBoxLayout()
        brl1.setContentsMargins(0, 0, 0, 0)
        brl1.setSpacing(4)
        gen_btn = QPushButton(t("gen.generate"))
        gen_btn.setFixedHeight(28)
        gen_btn.setStyleSheet(f"background: {accent}; color: white; border-radius: 6px; font-size: 11px; font-weight: bold; border: none; padding: 0 6px; min-height: 0;")
        gen_btn.clicked.connect(self._gen_generate)
        brl1.addWidget(gen_btn)
        copy_btn = QPushButton(t("gen.copy"))
        copy_btn.setFixedHeight(28)
        copy_btn.setStyleSheet(f"background: {'#2a2a2a' if dark else '#e0e0e0'}; color: {'#f0f0f0' if dark else '#1a1a1a'}; border-radius: 6px; font-size: 11px; border: none; padding: 0 6px; min-height: 0;")
        copy_btn.clicked.connect(self._gen_copy)
        brl1.addWidget(copy_btn)
        pl.addLayout(brl1)
        self._gen_stack.addWidget(pwd_panel)

        # Panel 2: Diceware / passphrase
        dice_panel = QWidget()
        dice_panel.setStyleSheet("background: transparent; border: none;")
        dl = QVBoxLayout(dice_panel)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(4)

        cnt_row = QWidget()
        cnt_row.setStyleSheet("background: transparent; border: none;")
        crl = QHBoxLayout(cnt_row)
        crl.setContentsMargins(0, 0, 0, 0)
        cnt_lbl = QLabel(t("gen.word_count"))
        cnt_lbl.setStyleSheet(f"color: {'#f0f0f0' if dark else '#1a1a1a'}; font-size: 11px; background: transparent; border: none;")
        crl.addWidget(cnt_lbl)
        crl.addStretch()
        self._dice_cnt_lbl = QLabel(str(self._dice_count))
        self._dice_cnt_lbl.setStyleSheet(f"color: {accent}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        crl.addWidget(self._dice_cnt_lbl)
        dl.addWidget(cnt_row)

        self._dice_slider = QSlider(Qt.Orientation.Horizontal)
        self._dice_slider.setRange(3, 8)
        self._dice_slider.setValue(self._dice_count)
        self._dice_slider.setStyleSheet(_slider_sty)
        self._dice_slider.valueChanged.connect(self._dice_slider_changed)
        dl.addWidget(self._dice_slider)

        # Separator
        sep_row = QWidget()
        sep_row.setStyleSheet("background: transparent; border: none;")
        sepl = QHBoxLayout(sep_row)
        sepl.setContentsMargins(0, 0, 0, 0)
        sepl.setSpacing(4)
        sepl.addWidget(QLabel("X") if False else
                       (lambda lbl: (lbl.setStyleSheet(f"color: {'#d0d0d0' if dark else '#444'}; font-size: 11px; background: transparent; border: none;"), lbl)[1])(QLabel(t("gen.separator"))))
        self._dice_sep_combo = QComboBox()
        self._dice_sep_combo.addItems([t("gen.sep_dash"), t("gen.sep_space"), t("gen.sep_dot"), t("gen.sep_underscore")])
        self._dice_sep_combo.setFixedHeight(22)
        self._dice_sep_combo.setStyleSheet(
            f"QComboBox {{ background: {'#333' if dark else '#d8d8d8'}; color: {'#f0f0f0' if dark else '#1a1a1a'}; border-radius: 4px; font-size: 10px; border: none; padding: 0 4px; }}"
            f"QComboBox::drop-down {{ border: none; }}"
        )
        self._dice_sep_combo.currentIndexChanged.connect(self._dice_sep_changed)
        sepl.addWidget(self._dice_sep_combo)
        dl.addWidget(sep_row)

        cap_cb = QCheckBox(t("gen.capitalize"))
        cap_cb.setChecked(self._dice_cap)
        cap_cb.setStyleSheet(_cb_sty)
        cap_cb.stateChanged.connect(lambda s: setattr(self, "_dice_cap", bool(s)))
        dl.addWidget(cap_cb)

        # Entropia + output
        self._dice_entropy_lbl = QLabel("")
        self._dice_entropy_lbl.setStyleSheet(f"color: {'#888' if dark else '#666'}; font-size: 10px; background: transparent; border: none;")
        dl.addWidget(self._dice_entropy_lbl)

        self._dice_out = QLabel("—")
        self._dice_out.setWordWrap(True)
        self._dice_out.setStyleSheet(f"color: {'#90c090' if dark else '#2d6a4f'}; font-size: 10px; font-family: 'Courier New', monospace; background: transparent; border: none;")
        dl.addWidget(self._dice_out)

        brl2 = QHBoxLayout()
        brl2.setContentsMargins(0, 0, 0, 0)
        brl2.setSpacing(4)
        dice_gen_btn = QPushButton(t("gen.generate"))
        dice_gen_btn.setFixedHeight(28)
        dice_gen_btn.setStyleSheet(f"background: {accent}; color: white; border-radius: 6px; font-size: 11px; font-weight: bold; border: none; padding: 0 6px; min-height: 0;")
        dice_gen_btn.clicked.connect(self._dice_generate)
        brl2.addWidget(dice_gen_btn)
        dice_copy_btn = QPushButton(t("gen.copy"))
        dice_copy_btn.setFixedHeight(28)
        dice_copy_btn.setStyleSheet(f"background: {'#2a2a2a' if dark else '#e0e0e0'}; color: {'#f0f0f0' if dark else '#1a1a1a'}; border-radius: 6px; font-size: 11px; border: none; padding: 0 6px; min-height: 0;")
        dice_copy_btn.clicked.connect(self._dice_copy)
        brl2.addWidget(dice_copy_btn)
        dl.addLayout(brl2)
        self._gen_stack.addWidget(dice_panel)

        gl.addWidget(self._gen_stack)
        vl.addWidget(gen)

        # Podpięcie tabów
        def _switch_tab(idx):
            self._gen_stack.setCurrentIndex(idx)
            self._tab_pwd.setStyleSheet(_tab_active if idx == 0 else _tab_inactive)
            self._tab_dice.setStyleSheet(_tab_active if idx == 1 else _tab_inactive)

        self._tab_pwd.clicked.connect(lambda: _switch_tab(0))
        self._tab_dice.clicked.connect(lambda: _switch_tab(1))
        _switch_tab(0)  # domyślnie zakładka "Losowe"
        self._dice_update_entropy()

    def _gen_slider_changed(self, val):
        self._gen_length = val
        if hasattr(self, "_gen_len_lbl"):
            self._gen_len_lbl.setText(str(val))

    def _dice_slider_changed(self, val):
        self._dice_count = val
        if hasattr(self, "_dice_cnt_lbl"):
            self._dice_cnt_lbl.setText(str(val))
        self._dice_update_entropy()

    def _dice_sep_changed(self, idx):
        self._dice_sep = ["-", " ", ".", "_"][idx]

    def _dice_update_entropy(self):
        if not hasattr(self, "_dice_entropy_lbl"):
            return
        from utils.wordlist import entropy_bits
        bits = entropy_bits(self._dice_count)
        strength = "słabe" if bits < 45 else "dobre" if bits < 60 else "silne" if bits < 80 else "bardzo silne"
        self._dice_entropy_lbl.setText(f"Entropia: {bits:.0f} bitów ({strength})")

    def _dice_generate(self):
        import secrets
        from utils.wordlist import WORDS
        words = [secrets.choice(WORDS) for _ in range(self._dice_count)]
        if self._dice_cap:
            words = [w.capitalize() for w in words]
        self._dice_phrase = self._dice_sep.join(words)
        self._dice_out.setText(self._dice_phrase)

    def _dice_copy(self):
        if self._dice_phrase:
            try:
                copy_sensitive(self._dice_phrase)
                if self._toast:
                    self._toast.show("Skopiowano do schowka", "success")
            except Exception:
                pass

    def _gen_generate(self):
        import string
        chars = string.ascii_lowercase
        if self._gen_upper:   chars += string.ascii_uppercase
        if self._gen_digits:  chars += string.digits
        if self._gen_special: chars += "!@#$%^&*()-_=+[]{}|;:,.<>?"
        import secrets as _sec
        pwd = "".join(_sec.choice(chars) for _ in range(self._gen_length))
        self._gen_pwd = pwd
        self._gen_out.setText(pwd[:30] + ("…" if len(pwd) > 30 else ""))

    def _gen_copy(self):
        if self._gen_pwd:
            try:
                copy_sensitive(self._gen_pwd)
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
        self._row_widgets = []
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

        # Sortuj: ulubione zawsze na górze, potem według wybranego kryterium
        def _sort_key(item):
            entry, s_color, score, fav = item
            if self._sort_by == "name":
                sec = (entry.title or "").lower()
            elif self._sort_by == "used":
                sec = getattr(entry, "last_used_at", None) or datetime.min
            elif self._sort_by == "strength":
                sec = score
            elif self._sort_by == "created":
                sec = getattr(entry, "created_at", None) or datetime.min
            else:
                sec = (entry.title or "").lower()
            return (-fav, sec if self._sort_asc else _Reverse(sec))

        class _Reverse:
            """Odwraca porządek sortowania dla dowolnego typu."""
            def __init__(self, val): self.val = val
            def __lt__(self, o): return self.val > o.val
            def __eq__(self, o): return self.val == o.val

        entry_data.sort(key=_sort_key)

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
                on_select=self._on_entry_select,
                strength_color=s_color,
                strength_score=score,
                cat_color=cat_col,
                compact=self._compact_mode,
            )
            if self._bulk_mode:
                row.set_bulk_mode(True)
                if entry.id in self._selected_ids:
                    row.set_checked(True)
            self._row_widgets.append(row)
            self._list_vl.addWidget(row)

        self._list_vl.addStretch()

    # ── Bulk operacje ──────────────────────────────────────────────────

    def _on_sort_changed(self, idx: int):
        key = self._sort_combo.itemData(idx)
        if key.endswith("_asc"):
            self._sort_by  = key[:-4]
            self._sort_asc = True
        else:
            self._sort_by  = key[:-5]
            self._sort_asc = False
        self._prefs.set("sort_by", self._sort_by)
        self._prefs.set("sort_asc", self._sort_asc)
        self._load_passwords()

    def _toggle_bulk_mode(self):
        self._bulk_mode = not self._bulk_mode
        if not self._bulk_mode:
            self._selected_ids.clear()
        self._bulk_bar.setVisible(self._bulk_mode)
        self._bulk_btn.setText("✕ Anuluj zaznaczanie" if self._bulk_mode else "☑ Zaznacz")
        for row in self._row_widgets:
            row.set_bulk_mode(self._bulk_mode)
            if not self._bulk_mode:
                row.set_checked(False)
        self._update_bulk_bar()

    def _on_entry_select(self, entry_id: int, checked: bool):
        if checked:
            self._selected_ids.add(entry_id)
        else:
            self._selected_ids.discard(entry_id)
        self._update_bulk_bar()

    def _update_bulk_bar(self):
        n = len(self._selected_ids)
        self._bulk_count_lbl.setText(f"{n} zaznaczonych" if n != 1 else "1 zaznaczony")

    def _bulk_select_all(self):
        for row in self._row_widgets:
            row.set_checked(True)
            self._selected_ids.add(row.entry.id)
        self._update_bulk_bar()

    def _bulk_trash(self):
        if not self._selected_ids:
            return
        n = len(self._selected_ids)
        if not ask_yes_no("Kosz", f"Przenieść {n} {'wpis' if n == 1 else 'wpisy' if n < 5 else 'wpisów'} do kosza?", parent=self):
            return
        moved = 0
        for eid in list(self._selected_ids):
            entry = self.db.get_password_by_id(eid, self.user)
            if entry:
                try:
                    self.db.trash_password(entry)
                    moved += 1
                except Exception:
                    pass
        self._selected_ids.clear()
        self._bulk_mode = False
        self._bulk_bar.setVisible(False)
        self._bulk_btn.setText("☑ Zaznacz")
        self._refresh()
        if self._toast:
            self._toast.show(f"Przeniesiono {moved} wpisów do kosza", "info")

    def _bulk_move(self):
        if not self._selected_ids:
            return
        cats = [c for c in self.db.get_all_categories(self.user)
                if c not in ("Wszystkie", "Notatki", "Ulubione")]

        dlg = QDialog(self)
        dlg.setWindowTitle("Przenieś do kategorii")
        dlg.setFixedSize(280, 360)
        dark = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
        dlg.setStyleSheet(f"background: {'#1e1e1e' if dark else '#ffffff'}; color: {'#f0f0f0' if dark else '#1a1a1a'};")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(8)

        lbl = QLabel(f"Wybierz kategorię dla {len(self._selected_ids)} wpisów:")
        lbl.setStyleSheet("font-size: 13px; font-weight: bold; background: transparent; border: none;")
        vl.addWidget(lbl)

        list_w = QListWidget()
        list_w.setStyleSheet(
            f"background: {'#2a2a2a' if dark else '#f5f5f5'}; border-radius: 8px; border: none; font-size: 13px;"
            f" QListWidget::item:selected {{ background: {'#1f6aa5' if dark else '#bee3f8'}; }}"
        )
        for cat in cats:
            list_w.addItem(cat)
        if list_w.count() > 0:
            list_w.setCurrentRow(0)
        vl.addWidget(list_w, stretch=1)

        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent; border: none;")
        brl = QHBoxLayout(btn_row)
        brl.setContentsMargins(0, 4, 0, 0)
        brl.setSpacing(8)
        cancel = QPushButton("Anuluj")
        cancel.setFixedHeight(34)
        cancel.setStyleSheet("background: transparent; border: 1px solid #555; border-radius: 6px; color: #aaa; font-size: 12px;")
        cancel.clicked.connect(dlg.reject)
        ok_btn = QPushButton("Przenieś")
        ok_btn.setFixedHeight(34)
        ok_btn.setStyleSheet("background: #1f6aa5; color: white; border-radius: 6px; font-size: 12px; font-weight: bold; border: none;")
        ok_btn.clicked.connect(dlg.accept)
        list_w.itemDoubleClicked.connect(lambda: dlg.accept())
        brl.addWidget(cancel)
        brl.addWidget(ok_btn)
        vl.addWidget(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        sel = list_w.currentItem()
        if not sel:
            return
        cat = sel.text()

        moved = 0
        for eid in list(self._selected_ids):
            entry = self.db.get_password_by_id(eid, self.user)
            if entry:
                entry.category = cat
                moved += 1
        self.db.session.commit()

        self._selected_ids.clear()
        self._bulk_mode = False
        self._bulk_bar.setVisible(False)
        self._bulk_btn.setText("☑ Zaznacz")
        self._refresh()
        if self._toast:
            self._toast.show(f"Przeniesiono {moved} wpisów do kategorii «{cat}»", "success")

    def keyPressEvent(self, event):
        if (self._bulk_mode
                and event.modifiers() == Qt.KeyboardModifier.ControlModifier
                and event.key() == Qt.Key.Key_A):
            self._bulk_select_all()
        else:
            super().keyPressEvent(event)

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
        NoteFormPanel(self.centralWidget(), self.db, self.user,
                      on_saved=lambda: self._refresh(rebuild_sidebar=True)).open()

    def _add_password(self):
        PasswordFormPanel(self.centralWidget(), self.db, self.crypto, self.user,
                          on_saved=lambda: self._refresh(rebuild_sidebar=True)).open()

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

        if self.db.has_pin(self.user):
            self._lock_pin_dialog()
        else:
            self._lock_master_dialog()

    def _lock_pin_dialog(self):
        """Ekran PIN-u (quick unlock). Po 3 błędach → fallback na masterhasło."""
        accent = self._prefs.get_accent()
        dlg = QDialog(self)
        dlg.setWindowTitle("Odblokuj aplikację")
        dlg.setFixedSize(380, 340)
        dlg.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint
        )
        dlg.reject = lambda: None
        dlg.setStyleSheet("QDialog { background: #1e1e1e; color: #f0f0f0; } QLabel { background: transparent; border: none; color: #f0f0f0; }")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(30, 20, 30, 20)
        vl.setSpacing(10)

        icon = QLabel("🔒")
        icon.setStyleSheet("font-size: 48px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(icon)

        vl.addWidget(self._empty_lbl("Podaj PIN aby odblokować", 15, True))

        pin_entry = QLineEdit()
        pin_entry.setEchoMode(QLineEdit.EchoMode.Password)
        pin_entry.setPlaceholderText("••••••")
        pin_entry.setMaxLength(6)
        pin_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pin_entry.setFixedHeight(52)
        pin_entry.setStyleSheet(
            "background: #2a2a2a; color: #f0f0f0; border: 1px solid #444;"
            "border-radius: 10px; padding: 0 12px; font-size: 22px; letter-spacing: 8px;"
        )
        vl.addWidget(pin_entry)

        msg_lbl = QLabel("")
        msg_lbl.setStyleSheet("color: #e53e3e; font-size: 11px;")
        msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(msg_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        fallback_btn = QPushButton("Użyj hasła masterowego")
        fallback_btn.setFixedHeight(36)
        fallback_btn.setStyleSheet(
            "background: #2a2a2a; color: #aaa; border: 1px solid #444;"
            "border-radius: 8px; font-size: 11px;"
        )
        unlock_btn = QPushButton("Odblokuj")
        unlock_btn.setFixedHeight(36)
        unlock_btn.setStyleSheet(
            f"background: {accent}; color: white; border: none;"
            "border-radius: 8px; font-size: 13px; font-weight: bold;"
        )
        unlock_btn.setDefault(True)
        btn_row.addWidget(fallback_btn)
        btn_row.addWidget(unlock_btn)
        vl.addLayout(btn_row)

        attempts = [0]

        def _try_pin():
            pin = pin_entry.text().strip()
            if self.db.verify_pin(self.user, pin):
                self._locked = False
                self._last_activity = time.time()
                dlg.accept()
                self._lock_timer.start()
            else:
                attempts[0] += 1
                pin_entry.clear()
                shake(pin_entry)
                if attempts[0] >= 3:
                    dlg.accept()
                    self._lock_master_dialog()
                else:
                    msg_lbl.setText(f"Nieprawidłowy PIN. Pozostało prób: {3 - attempts[0]}")

        unlock_btn.clicked.connect(_try_pin)
        pin_entry.returnPressed.connect(_try_pin)
        fallback_btn.clicked.connect(lambda: (dlg.accept(), self._lock_master_dialog()))

        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        QTimer.singleShot(200, pin_entry.setFocus)
        dlg.exec()

    def _lock_master_dialog(self):
        """Ekran masterhasła przy blokadzie."""
        accent = self._prefs.get_accent()
        dlg = QDialog(self)
        dlg.setWindowTitle("Aplikacja zablokowana")
        dlg.setFixedSize(440, 300)
        dlg.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint
        )
        dlg.reject = lambda: None
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
            on_language_change=self._on_language_change,
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
        if self._settings_panel.isVisible():
            return
        self._pause_bg_animations()
        self._settings_panel.slide_in(self.centralWidget())

    def _close_settings(self):
        if self._settings_panel:
            self._settings_panel.slide_out(on_hidden=self._resume_bg_animations)

    def _pause_bg_animations(self):
        self._bg_pause_count = getattr(self, "_bg_pause_count", 0) + 1
        if self._bg_pause_count > 1:
            return  # już zapauzowane
        for attr in ("_top_sep", "_content_hex"):
            w = getattr(self, attr, None)
            if w and hasattr(w, "stop_animation"):
                try:
                    w.stop_animation()
                except Exception:
                    pass
        if self._score_ring:
            self._score_ring.stop_pulse()

    def _resume_bg_animations(self):
        self._bg_pause_count = max(0, getattr(self, "_bg_pause_count", 0) - 1)
        if self._bg_pause_count > 0:
            return  # ktoś inny jeszcze pauzuje
        for attr in ("_top_sep", "_content_hex"):
            w = getattr(self, attr, None)
            if w and hasattr(w, "start_animation"):
                try:
                    w.start_animation()
                except Exception:
                    pass
        if self._score_ring:
            self._score_ring.start_pulse()

    def _on_language_change(self, lang: str):
        QTimer.singleShot(0, self._rebuild_and_reopen_settings)

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
        # Stary popup menu mógł zostać zniszczony razem ze starym centralWidget —
        # zerujemy referencję żeby uniknąć RuntimeError przy następnym kliknięciu.
        self._user_menu_widget = None

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
        try:
            widget = getattr(self, "_user_menu_widget", None)
            if widget is not None:
                widget.close()
                self._user_menu_widget = None
                return
        except Exception:
            self._user_menu_widget = None

        menu = QFrame(self.centralWidget())
        menu.setWindowFlags(Qt.WindowType.Popup)
        menu.setFixedWidth(200)
        menu.setStyleSheet(f"background: {'#1e1e1e' if dark else '#fff'}; border: 1px solid {'#444' if dark else '#ccc'}; border-radius: 10px;")
        ml = QVBoxLayout(menu)
        ml.setContentsMargins(0, 6, 0, 6)
        ml.setSpacing(0)

        for text, callback in [
            (f"👤  {self.user.username}", None),
            (t("main.menu_settings"), self._open_settings),
            (t("main.menu_lock"),     self._lock),
            (t("main.menu_sync"),     self._open_sync),
            (t("main.menu_logout"),   self._logout),
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
        # Preferuj zaznaczony wpis, fallback na pierwszy widoczny
        entry = None
        for i in range(self._list_vl.count()):
            item = self._list_vl.itemAt(i)
            w = item.widget() if item else None
            if not isinstance(w, PasswordRowWidget):
                continue
            if entry is None:
                entry = w.entry   # fallback: pierwszy widoczny
            if w.entry.id in self._selected_ids:
                entry = w.entry   # priorytet: zaznaczony
                break
        if entry is None:
            self._toast.show("Brak widocznych haseł do zduplikowania", "warning")
            return
        try:
            new_entry = self.db.duplicate_password(entry, self.crypto)
            self.db.log_event(self.user, "password_created",
                              entry_id=new_entry.id, details=f"duplikat: {entry.title}")
            self._refresh()
            self._toast.show(f"Zduplikowano: {entry.title}", "success")
        except Exception as e:
            self._toast.show(f"Błąd duplikowania: {e}", "error")

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
        CategoryPanel(self.centralWidget(), self.db, self.user,
                      on_created=lambda _: self._refresh(rebuild_sidebar=True)).open()

    # ── Trash / backup ────────────────────────────────────────────────

    def _open_trash(self):
        TrashPanel(self.centralWidget(), self.db, self.crypto, self.user,
                   on_refresh=lambda: self._refresh(rebuild_sidebar=True)).open()

    def _export(self):
        ExportPanel(self.centralWidget(), self.db, self.crypto, self.user).open()

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
            self, "Import zewnętrzny", "",
            "Wszystkie obsługiwane (*.csv *.json *.kdbx);;"
            "KeePass KDBX (*.kdbx);;"
            "CSV / JSON (*.csv *.json)"
        )
        if not path:
            return
        try:
            from utils.import_manager import ImportManager
            mgr = ImportManager(self.db, self.crypto, self.user)
            if path.lower().endswith(".kdbx"):
                count = self._import_keepass(mgr, path)
            else:
                count = mgr.import_file(path)
            if count is None:
                return   # anulowano dialog KeePass
            show_success("Import", f"Zaimportowano {count} haseł.", parent=self)
            self._refresh(rebuild_sidebar=True)
        except Exception as e:
            show_error("Błąd importu", str(e), parent=self)

    def _import_keepass(self, mgr, path: str):
        """Pokazuje dialog hasła KeePass i uruchamia import. Zwraca None gdy anulowano."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                      QLabel, QLineEdit, QPushButton)
        dlg = QDialog(self)
        dlg.setWindowTitle("Hasło do bazy KeePass")
        dlg.setFixedWidth(380)
        dlg.setStyleSheet("background:#1e1e1e; color:#e0e0e0;")

        vl = QVBoxLayout(dlg)
        vl.setSpacing(12)
        vl.setContentsMargins(24, 24, 24, 24)

        icon_lbl = QLabel("🔐 Podaj hasło do bazy KeePass")
        icon_lbl.setStyleSheet("font-size:14px; font-weight:600;")
        vl.addWidget(icon_lbl)

        file_lbl = QLabel(path.split("/")[-1].split("\\")[-1])
        file_lbl.setStyleSheet("font-size:11px; color:#888;")
        vl.addWidget(file_lbl)

        pwd_edit = QLineEdit()
        pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pwd_edit.setPlaceholderText("Hasło do pliku .kdbx...")
        pwd_edit.setFixedHeight(40)
        pwd_edit.setStyleSheet(
            "background:#2a2a2a; border:1px solid #444; border-radius:6px;"
            "padding:0 10px; font-size:13px; color:#e0e0e0;"
        )
        vl.addWidget(pwd_edit)

        hint = QLabel("Pozostaw puste jeśli baza nie ma hasła.")
        hint.setStyleSheet("font-size:10px; color:#666;")
        vl.addWidget(hint)

        hl = QHBoxLayout()
        hl.setSpacing(8)
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setStyleSheet(
            "background:#333; border:1px solid #555; border-radius:6px;"
            "color:#ccc; font-size:13px;"
        )
        ok_btn = QPushButton("Importuj")
        ok_btn.setFixedHeight(36)
        ok_btn.setStyleSheet(
            "background:#4F8EF7; border:none; border-radius:6px;"
            "color:white; font-size:13px; font-weight:600;"
        )
        ok_btn.setDefault(True)
        hl.addWidget(cancel_btn)
        hl.addWidget(ok_btn)
        vl.addLayout(hl)

        cancel_btn.clicked.connect(dlg.reject)
        ok_btn.clicked.connect(dlg.accept)
        pwd_edit.returnPressed.connect(dlg.accept)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        return mgr.import_keepass(path, pwd_edit.text())

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
        try:
            info = check_for_update()
        except Exception as e:
            logger.error(f"check_for_update failed: {e}")
            info = None
        if info:
            self._update_found_sig.emit(info)
        else:
            self._no_update_sig.emit()

    def _on_no_update(self):
        QTimer.singleShot(4 * 60 * 60 * 1000,
                          lambda: threading.Thread(target=self._bg_check_update, daemon=True).start())

    def _on_update_found(self, info: dict):
        self._update_info = info
        if self._update_btn:
            version = info.get("version", "")
            self._update_btn.setText(f"↑  {version}" if version else "↑  Nowa wersja")
            self._update_btn.setToolTip(f"Kliknij aby zaktualizować do {version}")
            self._update_btn.setVisible(True)

    def _open_update_dialog(self):
        if not self._update_info:
            return
        try:
            from gui_qt.update_dialog import UpdateDropdown
            UpdateDropdown(self, self._update_info, self._update_btn)
        except Exception as e:
            logger.error(f"UpdateDropdown error: {e}")
            url = self._update_info.get("download_url", "")
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
                if path:
                    self._backup_done_sig.emit(os.path.basename(path))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    # ── Security analysis ─────────────────────────────────────────────

    def _open_analysis(self):
        try:
            from gui_qt.security_analysis_window import SecurityAnalysisWindow
            dlg = SecurityAnalysisWindow(self, self.db, self.crypto, self.user)
            dlg.exec()
        except Exception as e:
            show_info("Analiza bezpieczeństwa", f"Błąd: {e}", parent=self)

    # ── Logout ────────────────────────────────────────────────────────

    def _logout(self):
        self.logged_out = True
        self._cleanup()
        if self._embedded:
            self.logout_requested.emit()
        else:
            self.close()
            QApplication.quit()
