"""
panels.py — Slide-in panele zastępujące QDialog.exec()
=======================================================
Wszystkie panele dziedziczą po SlidePanelBase z slide_panel.py.
Zamiast zwracać przez exec() → Accepted, wywołują callback on_saved/on_created.

Dostępne panele:
  PasswordFormPanel  — dodaj / edytuj hasło
  NoteFormPanel      — dodaj / edytuj notatkę
  CategoryPanel      — nowa kategoria
  TrashPanel         — kosz
  ExportPanel        — eksport haseł
"""

import os
import threading

import pyotp

from datetime import datetime, timezone

from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QLineEdit, QTextEdit,
    QComboBox, QScrollArea, QVBoxLayout, QHBoxLayout, QProgressBar,
    QGridLayout, QFileDialog, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from database.db_manager import DatabaseManager
from core.crypto import CryptoManager, generate_password
from utils.password_strength import check_strength
from utils.prefs_manager import PrefsManager
from utils.i18n import t
from utils.clipboard import copy_sensitive

from gui_qt.slide_panel import SlidePanelBase
from gui_qt.gradient import AnimatedGradientWidget
from gui_qt.dialogs import show_error, show_success, ask_yes_no

_ASSETS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "assets"))
_ARROW_SVG = os.path.join(_ASSETS, "arrow_down.svg").replace("\\", "/")
_CHECK_SVG = os.path.join(_ASSETS, "check.svg").replace("\\", "/")


def _emoji_font(size: int = 14) -> QFont:
    import sys
    if sys.platform == "win32":
        return QFont("Segoe UI Emoji", size)
    elif sys.platform == "darwin":
        return QFont("Apple Color Emoji", size)
    else:
        return QFont("Noto Color Emoji", size)


def _blend_hex(accent: str, base: str, alpha: float) -> str:
    def _p(c):
        c = c.lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    ar, ag, ab = _p(accent)
    br, bg_, bb = _p(base)
    return (f"#{int(br + (ar - br) * alpha):02x}"
            f"{int(bg_ + (ag - bg_) * alpha):02x}"
            f"{int(bb + (ab - bb) * alpha):02x}")

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


def _colors(prefs: PrefsManager):
    accent = prefs.get_accent()
    dark   = (prefs.get("appearance_mode") or "dark").lower() != "light"
    return dict(
        accent   = accent,
        dark     = dark,
        bg       = "#161616" if dark else "#f2f2f2",
        bg_panel = "#1a1a1a" if dark else "#f5f5f5",
        bg_input = "#2e2e2e" if dark else "#ffffff",
        bg_card  = "#242424" if dark else "#f8f8f8",
        bdr      = "#525252" if dark else "#c0c0c0",
        text     = "#f0f0f0" if dark else "#1a1a1a",
        muted    = "#aaaaaa" if dark else "#555555",
        bar_bg   = "#3a3a3a" if dark else "#e0e0e0",
    )


def _header(parent_layout, title: str, c: dict):
    lbl = QLabel(title)
    lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {c['text']}; background: transparent; border: none;")
    parent_layout.addWidget(lbl)
    sep = AnimatedGradientWidget(accent=c["accent"], base=c["bg"], direction="h", anim_mode="slide")
    sep.setFixedHeight(2)
    sep.start_animation()
    parent_layout.addWidget(sep)


def _close_btn(parent_layout, c: dict, on_click):
    btn = QPushButton("✕")
    btn.setFixedSize(32, 32)
    btn.setStyleSheet(
        f"background: transparent; border: none; color: {c['muted']}; "
        "font-size: 16px; font-weight: bold;"
    )
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(on_click)
    return btn


def _section_label(text: str, c: dict) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color: {c['muted']}; font-size: 11px; font-weight: 600; "
        "background: transparent; border: none;"
    )
    return lbl


def _input_style(c: dict) -> str:
    return (
        f"background: {c['bg_input']}; color: {c['text']}; "
        f"border: 1.5px solid {c['bdr']}; border-radius: 8px; "
        "padding: 8px 12px; font-size: 13px;"
    )


def _btn_cancel(c: dict) -> QPushButton:
    btn = QPushButton(t("form.cancel"))
    btn.setFixedHeight(42)
    btn.setStyleSheet(
        f"background: transparent; border: 1.5px solid {c['bdr']}; "
        f"color: {c['muted']}; border-radius: 10px; font-size: 13px;"
    )
    return btn


def _btn_save(c: dict, label: str | None = None) -> QPushButton:
    btn = QPushButton(label or t("form.save"))
    btn.setFixedHeight(42)
    btn.setStyleSheet(
        f"background: {c['accent']}; color: white; border-radius: 10px; "
        "font-size: 13px; font-weight: bold;"
    )
    return btn


# ══════════════════════════════════════════════════════════════════════
# PasswordFormPanel
# ══════════════════════════════════════════════════════════════════════

class PasswordFormPanel(SlidePanelBase):
    """Slide-in panel do dodawania / edytowania hasła."""

    PANEL_WIDTH = 660
    _hibp_result = pyqtSignal(str, str)  # msg, color

    def __init__(self, parent, db: DatabaseManager, crypto: CryptoManager, user, entry=None, on_saved=None):
        self._db       = db
        self._crypto   = crypto
        self._user     = user
        self._entry    = entry
        self._on_saved = on_saved
        super().__init__(parent)
        QTimer.singleShot(200, self._title_e.setFocus)

    def _build_ui(self):
        c = _colors(self._prefs)

        self.setStyleSheet(f"""
            QLabel  {{ color: {c['text']}; font-size: 13px; background: transparent; border: none; }}
            QLineEdit, QTextEdit {{
                background: {c['bg_input']}; color: {c['text']};
                border: 1.5px solid {c['bdr']}; border-radius: 8px;
                padding: 8px 12px; font-size: 13px;
            }}
            QLineEdit:hover, QTextEdit:hover {{ border-color: {'#888' if c['dark'] else '#909090'}; }}
            QLineEdit:focus, QTextEdit:focus {{ border-color: {c['accent']}; border-width: 2px; }}
            QComboBox {{
                background: {c['bg_input']}; color: {c['text']};
                border: 1.5px solid {c['bdr']}; border-radius: 8px;
                padding: 8px 12px; font-size: 13px;
            }}
            QComboBox:focus {{ border-color: {c['accent']}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: {c['bg_input']}; color: {c['text']};
                selection-background-color: {c['accent']};
                border: 1px solid {c['bdr']}; border-radius: 6px;
            }}
            QScrollBar:vertical {{ background: transparent; width: 6px; }}
            QScrollBar::handle:vertical {{
                background: {'#444' if c['dark'] else '#ccc'}; border-radius: 3px; min-height: 20px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 0)
        root.setSpacing(10)

        # Header row
        hdr_row = QWidget()
        hdr_row.setStyleSheet("background: transparent;")
        hrl = QHBoxLayout(hdr_row)
        hrl.setContentsMargins(0, 0, 0, 0)
        title_str = t("form.header_edit") if self._entry else t("form.header_add")
        hdr_lbl = QLabel(title_str)
        hdr_lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {c['text']}; background: transparent; border: none;")
        hrl.addWidget(hdr_lbl, stretch=1)
        x_btn = _close_btn(hrl, c, self.close)
        hrl.addWidget(x_btn)
        root.addWidget(hdr_row)

        sep = AnimatedGradientWidget(accent=c["accent"], base=c["bg"], direction="h", anim_mode="slide")
        sep.setFixedHeight(2)
        sep.start_animation()
        root.addWidget(sep)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(0)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.viewport().setStyleSheet("background: transparent;")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        fl = QVBoxLayout(inner)
        fl.setSpacing(6)
        fl.setContentsMargins(0, 0, 4, 0)

        # Pola podstawowe
        self._title_e    = self._make_field(fl, c, t("form.field_service"), t("form.placeholder_service"))
        self._username_e = self._make_field(fl, c, t("form.field_login"),   t("form.placeholder_login"))

        # Hasło
        fl.addWidget(_section_label(t("form.field_password"), c))
        pwd_row = QWidget(); pwd_row.setStyleSheet("background: transparent;")
        prl = QHBoxLayout(pwd_row); prl.setContentsMargins(0, 0, 0, 0); prl.setSpacing(6)
        self._pwd_e = QLineEdit()
        self._pwd_e.setEchoMode(QLineEdit.EchoMode.Password)
        self._pwd_e.setPlaceholderText(t("form.placeholder_pass"))
        self._pwd_e.setFixedHeight(40)
        self._pwd_e.setStyleSheet(_input_style(c))
        prl.addWidget(self._pwd_e)
        eye_btn = QPushButton("👁")
        eye_btn.setFixedSize(40, 40)
        eye_btn.setStyleSheet(
            f"background: transparent; border: 1.5px solid {c['bdr']}; "
            "border-radius: 8px; font-size: 15px; min-height: 0; padding: 0;"
        )
        eye_btn.clicked.connect(self._toggle_pwd)
        prl.addWidget(eye_btn)
        fl.addWidget(pwd_row)

        # Generuj + HIBP
        act_row = QWidget(); act_row.setStyleSheet("background: transparent;")
        arl = QHBoxLayout(act_row); arl.setContentsMargins(0, 2, 0, 2); arl.setSpacing(8)
        gen_btn = QPushButton(t("form.generate"))
        gen_btn.setFixedHeight(38)
        gen_btn.setStyleSheet(
            f"background: {'#1a3a5c' if c['dark'] else '#ddeeff'}; "
            f"color: {'#7ab8f5' if c['dark'] else '#1a5080'}; "
            "border-radius: 8px; font-size: 13px; font-weight: bold; padding: 0 14px; min-height: 0;"
        )
        gen_btn.clicked.connect(self._generate)
        arl.addWidget(gen_btn)
        hibp_btn = QPushButton(t("form.check_leak"))
        hibp_btn.setFixedHeight(38)
        hibp_btn.setStyleSheet(
            f"background: {'#2a1a00' if c['dark'] else '#fff3e0'}; "
            f"color: {'#ffb74d' if c['dark'] else '#8a5000'}; "
            "border-radius: 8px; font-size: 13px; font-weight: bold; padding: 0 14px; min-height: 0;"
        )
        hibp_btn.clicked.connect(self._check_hibp)
        arl.addWidget(hibp_btn)
        arl.addStretch()
        fl.addWidget(act_row)

        self._hibp_lbl = QLabel("")
        self._hibp_lbl.setStyleSheet("font-size: 11px; background: transparent; border: none;")
        fl.addWidget(self._hibp_lbl)

        # Pasek siły
        self._str_bar = QProgressBar()
        self._str_bar.setRange(0, 100); self._str_bar.setValue(0)
        self._str_bar.setFixedHeight(6); self._str_bar.setTextVisible(False)
        self._str_bar.setStyleSheet(
            f"QProgressBar {{ background: {c['bar_bg']}; border-radius: 3px; border: none; }}"
            "QProgressBar::chunk { background: #718096; }"
        )
        fl.addWidget(self._str_bar)
        self._str_lbl = QLabel("")
        self._str_lbl.setStyleSheet(f"font-size: 11px; color: {'#888' if c['dark'] else '#666'}; background: transparent; border: none;")
        fl.addWidget(self._str_lbl)
        self._pwd_e.textChanged.connect(self._update_strength)

        self._url_e = self._make_field(fl, c, t("form.field_url"), "https://...")

        # Kategoria
        fl.addWidget(_section_label(t("form.field_category"), c))
        self._cat_combo = QComboBox()
        all_cats = self._db.get_all_categories(self._user)
        self._cat_combo.addItems(all_cats)
        self._cat_combo.setFixedHeight(34)
        self._cat_combo.setStyleSheet(
            f"QComboBox {{ background: {c['bg_input']}; color: {c['text']}; "
            f"border: 1.5px solid {c['bdr']}; border-radius: 8px; padding: 4px 12px; font-size: 13px; }}"
            f"QComboBox::drop-down {{ border: none; width: 28px; }}"
            f"QComboBox::down-arrow {{ image: url({_ARROW_SVG}); width: 10px; height: 6px; }}"
            f"QComboBox QAbstractItemView {{ background: {c['bg_input']}; color: {c['text']}; "
            f"selection-background-color: {c['accent']}; border: 1px solid {c['bdr']}; border-radius: 6px; }}"
        )
        fl.addWidget(self._cat_combo)

        self._expires_e = self._make_field(fl, c, t("form.field_expires"), "2026-12-31")

        # Notatki
        fl.addWidget(_section_label(t("form.field_notes"), c))
        self._notes_e = QTextEdit()
        self._notes_e.setFixedHeight(80)
        self._notes_e.setStyleSheet(
            f"background: {c['bg_input']}; color: {c['text']}; "
            f"border: 1.5px solid {c['bdr']}; border-radius: 8px; padding: 6px 10px; font-size: 13px;"
        )
        fl.addWidget(self._notes_e)

        # OTP
        fl.addWidget(_section_label(t("form.field_otp"), c))
        otp_row = QWidget(); otp_row.setStyleSheet("background: transparent;")
        otprl = QHBoxLayout(otp_row); otprl.setContentsMargins(0, 0, 0, 0); otprl.setSpacing(6)
        self._otp_e = QLineEdit()
        self._otp_e.setPlaceholderText("Sekret Base32 lub otpauth://... URI")
        self._otp_e.setFixedHeight(40)
        self._otp_e.setStyleSheet(_input_style(c))
        otprl.addWidget(self._otp_e)
        self._otp_preview_lbl = QLabel("")
        self._otp_preview_lbl.setFixedWidth(68)
        self._otp_preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._otp_preview_lbl.setStyleSheet(
            f"background: {'#1a2a1a' if c['dark'] else '#d4f0d4'}; "
            f"color: {'#7ec87e' if c['dark'] else '#2a6e2a'}; "
            "border-radius: 8px; font-size: 14px; font-weight: bold; border: none;"
        )
        otprl.addWidget(self._otp_preview_lbl)
        fl.addWidget(otp_row)
        self._otp_e.textChanged.connect(self._update_otp_preview)

        # Własne pola
        fl.addWidget(_section_label(t("form.field_custom"), c))
        self._fields_container = QWidget()
        self._fields_container.setStyleSheet("background: transparent;")
        self._fields_vl = QVBoxLayout(self._fields_container)
        self._fields_vl.setContentsMargins(0, 0, 0, 0)
        self._fields_vl.setSpacing(4)
        fl.addWidget(self._fields_container)
        self._custom_field_rows: list[tuple] = []

        add_field_btn = QPushButton(t("form.add_field"))
        add_field_btn.setFixedHeight(32)
        add_field_btn.setStyleSheet(
            f"background: transparent; border: 1.5px dashed {c['bdr']}; color: {c['muted']}; "
            "border-radius: 8px; font-size: 12px;"
        )
        add_field_btn.clicked.connect(self._add_custom_field_row)
        fl.addWidget(add_field_btn)
        fl.addStretch()

        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        # Przyciski — stała wysokość gwarantuje widoczność niezależnie od layoutu
        btn_row = QWidget(); btn_row.setStyleSheet("background: transparent;")
        btn_row.setFixedHeight(78)
        brl = QHBoxLayout(btn_row); brl.setContentsMargins(0, 16, 0, 20); brl.setSpacing(8)
        cancel = _btn_cancel(c)
        cancel.clicked.connect(self.close)
        brl.addWidget(cancel)
        save_btn = _btn_save(c)
        save_btn.clicked.connect(self._save)
        brl.addWidget(save_btn)
        root.addWidget(btn_row)

        # Wypełnij przy edycji
        if self._entry:
            e = self._entry
            self._title_e.setText(e.title or "")
            self._username_e.setText(e.username or "")
            self._url_e.setText(e.url or "")
            self._notes_e.setPlainText(e.notes or "")
            self._pwd_e.setText(self._db.decrypt_password(e, self._crypto))
            idx = self._cat_combo.findText(e.category or "Inne")
            if idx >= 0:
                self._cat_combo.setCurrentIndex(idx)
            if e.expires_at:
                self._expires_e.setText(e.expires_at.strftime("%Y-%m-%d"))
            if e.otp_secret:
                self._otp_e.setText(e.otp_secret)
            for name, value in self._db.get_custom_fields(e, self._crypto):
                self._add_custom_field_row(name, value)

        # Store colors for later
        self._c = c
        self._hibp_result.connect(self._on_hibp_result)

    # ── Helpers ───────────────────────────────────────────────────────

    def _make_field(self, layout, c, label, placeholder):
        layout.addWidget(_section_label(label, c))
        e = QLineEdit()
        e.setPlaceholderText(placeholder)
        e.setFixedHeight(40)
        e.setStyleSheet(_input_style(c))
        layout.addWidget(e)
        return e

    def _toggle_pwd(self):
        mode = QLineEdit.EchoMode.Normal if self._pwd_e.echoMode() == QLineEdit.EchoMode.Password else QLineEdit.EchoMode.Password
        self._pwd_e.setEchoMode(mode)

    def _update_otp_preview(self, text):
        from utils.import_manager import _parse_otp_secret
        secret = _parse_otp_secret(text.strip())
        if not secret:
            self._otp_preview_lbl.setText(""); return
        try:
            self._otp_preview_lbl.setText(pyotp.TOTP(secret).now())
        except Exception:
            self._otp_preview_lbl.setText("")

    def _add_custom_field_row(self, name: str = "", value: str = ""):
        c = self._c
        row_w = QWidget(); row_w.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row_w); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(6)
        _fs = _input_style(c).replace("padding: 8px 12px;", "padding: 6px 10px;").replace("font-size: 13px;", "font-size: 12px;")
        name_e  = QLineEdit(name);  name_e.setPlaceholderText(t("form.field_name_ph")); name_e.setFixedHeight(36); name_e.setStyleSheet(_fs)
        value_e = QLineEdit(value); value_e.setPlaceholderText(t("form.field_value_ph")); value_e.setFixedHeight(36); value_e.setStyleSheet(_fs)
        del_btn = QPushButton("✕"); del_btn.setFixedSize(30, 30)
        del_btn.setStyleSheet("background: transparent; color: #e05252; border: none; font-size: 14px; font-weight: bold;")
        rl.addWidget(name_e, 2); rl.addWidget(value_e, 3); rl.addWidget(del_btn)
        entry = (name_e, value_e, row_w)
        self._custom_field_rows.append(entry)
        self._fields_vl.addWidget(row_w)
        def _remove():
            if entry in self._custom_field_rows:
                self._custom_field_rows.remove(entry)
            row_w.setParent(None); row_w.deleteLater()
        del_btn.clicked.connect(_remove)

    def _update_strength(self):
        pwd = self._pwd_e.text()
        if not pwd:
            self._str_bar.setValue(0); self._str_lbl.setText(""); return
        sc = check_strength(pwd)
        color = sc.get("color", "#718096")
        self._str_bar.setStyleSheet(
            f"QProgressBar {{ background: {self._c['bar_bg']}; border-radius: 3px; border: none; }}"
            f"QProgressBar::chunk {{ background: {color}; }}"
        )
        self._str_bar.setValue(sc.get("percent", 0))
        self._str_lbl.setText(sc.get("label", ""))
        self._str_lbl.setStyleSheet(f"font-size: 11px; color: {color}; background: transparent; border: none;")

    def _generate(self):
        pwd = generate_password(length=20)
        self._pwd_e.setText(pwd)
        self._pwd_e.setEchoMode(QLineEdit.EchoMode.Normal)
        try:
            copy_sensitive(pwd)
        except Exception:
            pass
        show_success("Generator", f"Wygenerowano i skopiowano!\n\n{pwd}", parent=self)

    def _check_hibp(self):
        pwd = self._pwd_e.text()
        if not pwd:
            self._hibp_lbl.setText("Najpierw wpisz hasło."); return
        self._hibp_lbl.setText("Sprawdzanie...")
        def _run():
            try:
                from utils.hibp import check_password
                breached, count = check_password(pwd)
                if count == -1:    msg, color = "Brak połączenia z HIBP.", "#f0a500"
                elif breached:     msg, color = f"Hasło wyciekło {count:,} razy!", "#e05252"
                else:              msg, color = "Nie znaleziono w wyciekach.", "#4caf50"
            except Exception as e:
                msg, color = f"Błąd: {e}", "#e05252"
            try:
                self._hibp_result.emit(msg, color)
            except RuntimeError:
                pass
        threading.Thread(target=_run, daemon=True).start()

    def _on_hibp_result(self, msg: str, color: str):
        self._hibp_lbl.setText(msg)
        self._hibp_lbl.setStyleSheet(
            f"font-size: 11px; color: {color}; background: transparent; border: none;"
        )

    def _save(self):
        title    = self._title_e.text().strip()
        username = self._username_e.text().strip()
        password = self._pwd_e.text()
        url      = self._url_e.text().strip()
        notes    = self._notes_e.toPlainText().strip()
        category = self._cat_combo.currentText()

        if not title:
            show_error("Błąd", "Nazwa serwisu jest wymagana!", parent=self); return
        if not password:
            show_error("Błąd", "Hasło jest wymagane!", parent=self); return

        expires = None
        raw_exp = self._expires_e.text().strip()
        if raw_exp:
            for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                try:
                    expires = datetime.strptime(raw_exp, fmt); break
                except ValueError:
                    continue
            if expires is None:
                show_error("Błąd daty", f"Nierozpoznany format: '{raw_exp}'\n(użyj RRRR-MM-DD)", parent=self); return

        from utils.import_manager import _parse_otp_secret
        otp_raw    = self._otp_e.text().strip()
        otp_secret = _parse_otp_secret(otp_raw) if otp_raw else None

        if self._entry:
            self._db.update_password(
                self._entry, self._crypto,
                title=title, username=username, plaintext_password=password,
                url=url, notes=notes, category=category, expires_at=expires, otp_secret=otp_secret,
            )
            target_entry = self._entry
        else:
            target_entry = self._db.add_password(
                self._user, self._crypto,
                title=title, username=username, plaintext_password=password,
                url=url, notes=notes, category=category, expires_at=expires, otp_secret=otp_secret,
            )

        fields = [(n.text().strip(), v.text()) for n, v, _ in self._custom_field_rows if n.text().strip()]
        if target_entry:
            self._db.set_custom_fields(target_entry, self._crypto, fields)

        self.close()
        if self._on_saved:
            self._on_saved()


# ══════════════════════════════════════════════════════════════════════
# NoteFormPanel
# ══════════════════════════════════════════════════════════════════════

class NoteFormPanel(SlidePanelBase):
    """Slide-in panel do dodawania / edytowania notatki."""

    PANEL_WIDTH = 600

    def __init__(self, parent, db: DatabaseManager, user, entry=None, on_saved=None):
        self._db       = db
        self._user     = user
        self._entry    = entry
        self._on_saved = on_saved
        super().__init__(parent)
        QTimer.singleShot(200, self._title_e.setFocus)

    def _build_ui(self):
        c = _colors(self._prefs)

        self.setStyleSheet(f"""
            QLabel {{ color: {c['text']}; font-size: 13px; background: transparent; border: none; }}
            QLineEdit, QTextEdit {{
                background: {c['bg_input']}; color: {c['text']};
                border: 1.5px solid {c['bdr']}; border-radius: 8px;
                padding: 8px 12px; font-size: 13px;
            }}
            QLineEdit:focus, QTextEdit:focus {{ border-color: {c['accent']}; border-width: 2px; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 0)
        root.setSpacing(10)

        # Header
        hdr_row = QWidget(); hdr_row.setStyleSheet("background: transparent;")
        hrl = QHBoxLayout(hdr_row); hrl.setContentsMargins(0, 0, 0, 0)
        title_str = t("form.note_title_edit") if self._entry else t("form.note_title_add")
        hdr_lbl = QLabel(title_str)
        hdr_lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {c['text']}; background: transparent; border: none;")
        hrl.addWidget(hdr_lbl, stretch=1)
        x_btn = _close_btn(hrl, c, self.close)
        hrl.addWidget(x_btn)
        root.addWidget(hdr_row)

        sep = AnimatedGradientWidget(accent=c["accent"], base=c["bg"], direction="h", anim_mode="slide")
        sep.setFixedHeight(2); sep.start_animation()
        root.addWidget(sep)

        # Tytuł
        root.addWidget(_section_label(t("form.note_field_title"), c))
        self._title_e = QLineEdit()
        self._title_e.setPlaceholderText(t("form.note_placeholder_title"))
        self._title_e.setFixedHeight(40)
        self._title_e.setStyleSheet(_input_style(c))
        root.addWidget(self._title_e)

        # Treść
        root.addWidget(_section_label(t("form.note_field_content"), c))
        self._content_e = QTextEdit()
        self._content_e.setPlaceholderText(t("form.note_placeholder_content"))
        self._content_e.setStyleSheet(
            f"background: {c['bg_input']}; color: {c['text']}; "
            f"border: 1.5px solid {c['bdr']}; border-radius: 8px; padding: 8px 10px; font-size: 13px;"
        )
        root.addWidget(self._content_e, stretch=1)

        # Przyciski — stała wysokość
        btn_row = QWidget(); btn_row.setStyleSheet("background: transparent;")
        btn_row.setFixedHeight(78)
        brl = QHBoxLayout(btn_row); brl.setContentsMargins(0, 16, 0, 20); brl.setSpacing(8)
        cancel = _btn_cancel(c); cancel.clicked.connect(self.close)
        brl.addWidget(cancel)
        save_btn = _btn_save(c); save_btn.clicked.connect(self._save)
        brl.addWidget(save_btn)
        root.addWidget(btn_row)

        if self._entry:
            self._title_e.setText(self._entry.title or "")
            self._content_e.setPlainText(self._entry.notes or "")

    def _save(self):
        title   = self._title_e.text().strip()
        content = self._content_e.toPlainText().strip()
        if not title:
            show_error("Błąd", "Tytuł notatki jest wymagany!", parent=self); return
        if self._entry:
            self._db.update_note(self._entry, title, content)
        else:
            self._db.add_note(self._user, title, content)
        self.close()
        if self._on_saved:
            self._on_saved()


# ══════════════════════════════════════════════════════════════════════
# CategoryPanel
# ══════════════════════════════════════════════════════════════════════

class CategoryPanel(SlidePanelBase):
    """Slide-in panel do tworzenia nowej kategorii."""

    PANEL_WIDTH = 600

    def __init__(self, parent, db: DatabaseManager, user, on_created=None):
        self._db         = db
        self._user       = user
        self._on_created = on_created
        self._icon  = _EMOJI_PICKER[0]
        self._color = _CAT_PRESET_COLORS[5]
        super().__init__(parent)
        QTimer.singleShot(200, self._name_e.setFocus)

    def _build_ui(self):
        c = _colors(self._prefs)

        self.setStyleSheet(f"""
            QLabel {{ color: {c['text']}; font-size: 13px; background: transparent; border: none; }}
            QLineEdit {{
                background: {c['bg_input']}; color: {c['text']};
                border: 1.5px solid {c['bdr']}; border-radius: 8px;
                padding: 6px 10px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {c['accent']}; border-width: 2px; }}
            QScrollBar:vertical {{ background: transparent; width: 6px; }}
            QScrollBar::handle:vertical {{
                background: {'#444' if c['dark'] else '#ccc'}; border-radius: 3px; min-height: 20px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 0)
        root.setSpacing(10)

        # Header
        hdr_row = QWidget(); hdr_row.setStyleSheet("background: transparent;")
        hrl = QHBoxLayout(hdr_row); hrl.setContentsMargins(0, 0, 0, 0)
        hdr_lbl = QLabel("Nowa kategoria")
        hdr_lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {c['text']}; background: transparent; border: none;")
        hrl.addWidget(hdr_lbl, stretch=1)
        x_btn = _close_btn(hrl, c, self.close)
        hrl.addWidget(x_btn)
        root.addWidget(hdr_row)

        sep = AnimatedGradientWidget(accent=c["accent"], base=c["bg"], direction="h", anim_mode="slide")
        sep.setFixedHeight(2); sep.start_animation()
        root.addWidget(sep)

        # Scroll area — zawartość (podgląd + nazwa + emoji + kolor)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(0)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.viewport().setStyleSheet("background: transparent;")
        inner = QWidget(); inner.setStyleSheet("background: transparent;")
        fl = QVBoxLayout(inner); fl.setSpacing(10); fl.setContentsMargins(0, 0, 4, 4)

        # Podgląd
        self._preview = QLabel(f"{self._icon}  Nowa kategoria")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setFixedHeight(44)
        self._preview.setStyleSheet(
            f"background: {self._color}; color: white; border-radius: 10px; "
            "font-size: 14px; font-weight: bold;"
        )
        fl.addWidget(self._preview)

        # Nazwa
        fl.addWidget(_section_label("Nazwa", c))
        self._name_e = QLineEdit()
        self._name_e.setPlaceholderText("np. Praca, Gaming...")
        self._name_e.setFixedHeight(40)
        self._name_e.textChanged.connect(self._update_preview)
        fl.addWidget(self._name_e)

        # Emoji picker ─────────────────────────────────────────────────
        # WAŻNE: nie używamy font w QSS — setFont() jest nadpisywane przez
        # QSS font-family/font-size, co powoduje niespójne renderowanie emoji.
        # Wyłącznie setFont() zapewnia poprawne kolory emoji (Segoe UI Emoji).
        fl.addWidget(_section_label("Ikona", c))
        emoji_card = QWidget()
        emoji_card.setStyleSheet(
            f"background: {c['bg_card']}; border-radius: 10px; border: none;"
        )
        ef = _emoji_font(20)
        _SEL_QSS   = f"background: {c['accent']}25; border: 2px solid {c['accent']}; border-radius: 8px;"
        _UNSEL_QSS = "background: transparent; border: 2px solid transparent; border-radius: 8px;"
        eg = QGridLayout(emoji_card)
        eg.setContentsMargins(8, 8, 8, 8)
        eg.setSpacing(4)
        self._emoji_btns: list[QPushButton] = []
        for idx, em in enumerate(_EMOJI_PICKER):
            row_i, col_i = divmod(idx, 8)
            b = QPushButton(em)
            b.setFixedSize(54, 48)
            b.setFont(ef)
            b.setStyleSheet(_UNSEL_QSS)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, e=em, i=idx: self._pick_emoji(e, i))
            eg.addWidget(b, row_i, col_i)
            self._emoji_btns.append(b)
        # 4 wiersze × 48px + 3 × 4px + 2 × 8px marginesów
        emoji_card.setFixedHeight(4 * 48 + 3 * 4 + 16)
        # Zaznacz domyślnie pierwszy emoji
        self._emoji_btns[0].setStyleSheet(_SEL_QSS)
        self._SEL_QSS   = _SEL_QSS
        self._UNSEL_QSS = _UNSEL_QSS
        fl.addWidget(emoji_card)

        # Kolor ─────────────────────────────────────────────────────────
        # Kółko 44×44; zaznaczenie = biały border 3px wewnątrz (Qt border jest
        # zawsze wewnętrzny), co daje efekt "kolorowe kółko + biały pierścień".
        fl.addWidget(_section_label("Kolor", c))
        color_card = QWidget()
        color_card.setStyleSheet(
            f"background: {c['bg_card']}; border-radius: 10px; border: none;"
        )
        cg = QGridLayout(color_card)
        cg.setContentsMargins(10, 10, 10, 10)
        cg.setSpacing(10)
        self._color_btns: list[QPushButton] = []
        cols_per_row = 5
        for i, clr in enumerate(_CAT_PRESET_COLORS):
            row_i, col_i = divmod(i, cols_per_row)
            b = QPushButton()
            b.setFixedSize(44, 44)
            b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            sel = (i == 5)
            b.setStyleSheet(
                f"background: {clr}; border-radius: 22px; "
                + ("border: 3px solid white;" if sel else "border: 3px solid transparent;")
            )
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, color=clr, idx=i: self._pick_color(color, idx))
            cg.addWidget(b, row_i, col_i, Qt.AlignmentFlag.AlignCenter)
            self._color_btns.append(b)
        # 2 wiersze × 44px + 1 × 10px + 2 × 10px marginesów
        color_card.setFixedHeight(2 * 44 + 10 + 20)
        fl.addWidget(color_card)

        fl.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        # Przyciski — stała wysokość
        btn_row = QWidget(); btn_row.setStyleSheet("background: transparent;")
        btn_row.setFixedHeight(78)
        brl = QHBoxLayout(btn_row); brl.setContentsMargins(0, 16, 0, 20); brl.setSpacing(8)
        cancel = _btn_cancel(c); cancel.clicked.connect(self.close)
        brl.addWidget(cancel)
        ok_btn = _btn_save(c, "Utwórz"); ok_btn.clicked.connect(self._create)
        brl.addWidget(ok_btn)
        root.addWidget(btn_row)

        self._c = c

    def _update_preview(self):
        name = self._name_e.text() or "Nowa kategoria"
        self._preview.setText(f"{self._icon}  {name}")
        self._preview.setStyleSheet(
            f"background: {self._color}; color: white; border-radius: 10px; font-size: 13px; font-weight: bold;"
        )

    def _pick_emoji(self, em, idx):
        self._icon = em
        self._update_preview()
        ef = _emoji_font(20)
        for i, b in enumerate(self._emoji_btns):
            b.setFont(ef)
            b.setStyleSheet(self._SEL_QSS if i == idx else self._UNSEL_QSS)

    def _pick_color(self, col, idx):
        self._color = col
        self._update_preview()
        for i, b in enumerate(self._color_btns):
            clr = _CAT_PRESET_COLORS[i]
            brd = "border: 3px solid white;" if i == idx else "border: 3px solid transparent;"
            b.setStyleSheet(f"background: {clr}; border-radius: 22px; {brd}")

    def _create(self):
        name = self._name_e.text().strip()
        if not name:
            show_error("Błąd", "Podaj nazwę kategorii!", parent=self); return
        try:
            self._db.add_custom_category(self._user, name, self._icon, self._color)
            self.close()
            if self._on_created:
                self._on_created(name)
        except Exception as e:
            show_error("Błąd", str(e), parent=self)


# ══════════════════════════════════════════════════════════════════════
# TrashPanel
# ══════════════════════════════════════════════════════════════════════

class TrashPanel(SlidePanelBase):
    """Slide-in panel kosza."""

    PANEL_WIDTH = 700

    def __init__(self, parent, db: DatabaseManager, crypto: CryptoManager, user, on_refresh=None):
        self._db         = db
        self._crypto     = crypto
        self._user       = user
        self._on_refresh = on_refresh
        super().__init__(parent)

    def _build_ui(self):
        c = _colors(self._prefs)
        accent = c["accent"]
        dark   = c["dark"]
        bg     = "#1a1a1a" if dark else "#f5f5f5"

        self.setStyleSheet(
            f"QLabel {{ color: {'#f0f0f0' if dark else '#1a1a1a'}; background: transparent; border: none; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QFrame(); hdr.setFixedHeight(60)
        hdr.setStyleSheet(f"background: {_blend_hex(accent, '#1e1e1e' if dark else '#e8e8e8', 0.18)}; border: none;")
        hrl = QHBoxLayout(hdr); hrl.setContentsMargins(20, 0, 16, 0)
        title_lbl = QLabel("Kosz")
        title_lbl.setStyleSheet(f"font-size: 19px; font-weight: bold; color: {'#f0f0f0' if dark else '#1a1a1a'};")
        hrl.addWidget(title_lbl)
        hrl.addStretch()
        x_btn = _close_btn(hrl, c, self.close)
        hrl.addWidget(x_btn)
        root.addWidget(hdr)

        sep = AnimatedGradientWidget(accent=accent, base=bg, direction="h", anim_mode="slide")
        sep.setFixedHeight(2); sep.start_animation()
        root.addWidget(sep)

        # Pasek akcji — info + przycisk wyczyść
        action_bar = QWidget(); action_bar.setStyleSheet("background: transparent;")
        abl = QHBoxLayout(action_bar); abl.setContentsMargins(20, 6, 16, 6); abl.setSpacing(10)
        info = QLabel("Hasła w koszu są trwale usuwane po 30 dniach.")
        info.setStyleSheet(f"color: {'#888' if dark else '#666'}; font-size: 11px;")
        abl.addWidget(info, stretch=1)
        purge_btn = QPushButton("Wyczyść kosz"); purge_btn.setFixedHeight(30)
        purge_btn.setStyleSheet("background: #4a1a1a; color: #ff8080; border-radius: 8px; font-size: 12px; padding: 0 10px;")
        purge_btn.clicked.connect(self._purge_all)
        abl.addWidget(purge_btn)
        root.addWidget(action_bar)

        # Lista
        self._scroll = QScrollArea(); self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(f"background: {bg}; border: none;")
        self._list_widget = QWidget(); self._list_widget.setStyleSheet(f"background: {bg};")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(20, 8, 20, 8); self._list_layout.setSpacing(6)
        self._scroll.setWidget(self._list_widget)
        root.addWidget(self._scroll)

        self._load()

    def _load(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        c = _colors(self._prefs)
        dark = c["dark"]
        entries = self._db.get_trashed_passwords(self._user)

        if not entries:
            empty = QLabel("Kosz jest pusty.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {'#888' if dark else '#666'}; font-size: 13px; padding: 40px;")
            self._list_layout.addWidget(empty)
            self._list_layout.addStretch()
            return

        accent = c["accent"]
        row_bg = "#2a2a2a" if dark else "#e8e8e8"
        for entry in entries:
            row = QFrame()
            row.setStyleSheet(f"background: {row_bg}; border-radius: 10px; border: none;")
            rl = QHBoxLayout(row); rl.setContentsMargins(12, 8, 8, 8)

            info_w = QWidget(); info_w.setStyleSheet("background: transparent; border: none;")
            il = QVBoxLayout(info_w); il.setSpacing(2); il.setContentsMargins(0, 0, 0, 0)
            name_lbl = QLabel(entry.title or "—")
            name_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {'#f0f0f0' if dark else '#1a1a1a'};")
            il.addWidget(name_lbl)
            days_txt = ""
            if entry.deleted_at:
                from database.db_manager import TRASH_DAYS
                _del = entry.deleted_at
                if _del.tzinfo is None:
                    _del = _del.replace(tzinfo=timezone.utc)
                removed = (datetime.now(timezone.utc) - _del).days
                left = TRASH_DAYS - removed
                days_txt = f"Usunięto: {entry.deleted_at.strftime('%d.%m.%Y')}  •  Pozostało {left} dni"
            d = QLabel(days_txt); d.setStyleSheet(f"font-size: 10px; color: {'#888' if dark else '#666'};")
            il.addWidget(d)
            rl.addWidget(info_w, stretch=1)

            restore_btn = QPushButton("Przywróć"); restore_btn.setFixedHeight(30)
            restore_btn.setStyleSheet(f"background: {accent}; color: white; border-radius: 6px; font-size: 11px; font-weight: bold;")
            restore_btn.clicked.connect(lambda _, e=entry: self._restore(e))
            rl.addWidget(restore_btn)

            del_btn = QPushButton("Usuń"); del_btn.setFixedHeight(30)
            del_btn.setStyleSheet("background: #4a1a1a; color: #ff8080; border-radius: 6px; font-size: 11px;")
            del_btn.clicked.connect(lambda _, e=entry: self._delete_perm(e))
            rl.addWidget(del_btn)

            self._list_layout.addWidget(row)
        self._list_layout.addStretch()

    def _restore(self, entry):
        self._db.restore_password(entry)
        if self._on_refresh:
            self._on_refresh()
        self._load()

    def _delete_perm(self, entry):
        if ask_yes_no("Usuń permanentnie", f"Trwale usunąć '{entry.title}'?",
                      parent=self, yes_text="Usuń", destructive=True):
            self._db.delete_password(entry)
            self._load()

    def _purge_all(self):
        entries = self._db.get_trashed_passwords(self._user)
        if not entries:
            return
        if ask_yes_no("Wyczyść kosz", f"Trwale usunąć wszystkie {len(entries)} haseł?",
                      parent=self, yes_text="Wyczyść", destructive=True):
            for e in entries:
                self._db.delete_password(e)
            self._load()


# ══════════════════════════════════════════════════════════════════════
# ExportPanel
# ══════════════════════════════════════════════════════════════════════

class ExportPanel(SlidePanelBase):
    """Slide-in panel eksportu haseł."""

    PANEL_WIDTH = 620
    _export_done_sig = pyqtSignal(int, str)   # count, path
    _export_err_sig  = pyqtSignal(str)        # error message

    _FORMATS = [
        ("aegis",     "🔒 AegisVault (.aegis)",    "Zaszyfrowany backup — tylko dla AegisVault.",           "aegisvault_backup.aegis",  "AegisVault Backup (*.aegis)"),
        ("csv",       "📄 Generic CSV (.csv)",      "Kompatybilny z większością menedżerów haseł.",          "export_aegisvault.csv",    "CSV (*.csv)"),
        ("bitwarden", "🔵 Bitwarden JSON (.json)",  "Import bezpośrednio do Bitwarden.",                     "bitwarden_export.json",    "JSON (*.json)"),
        ("1password", "🔑 1Password CSV (.csv)",    "Import do 1Password przez File → Import.",              "1password_export.csv",     "CSV (*.csv)"),
        ("keepass",   "🟢 KeePass XML (.xml)",      "Import do KeePass 2 / KeePassXC.",                      "keepass_export.xml",       "XML (*.xml)"),
    ]

    def __init__(self, parent, db: DatabaseManager, crypto: CryptoManager, user):
        self._db     = db
        self._crypto = crypto
        self._user   = user
        super().__init__(parent)

    def _build_ui(self):
        c = _colors(self._prefs)
        dark = c["dark"]

        bg_sel   = "#1a2a3a" if dark else "#ddeeff"
        bdr_norm = "#3a3a3a" if dark else "#dddddd"

        self.setStyleSheet(f"""
            QLabel {{ background: transparent; border: none; color: {c['text']}; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 0)
        root.setSpacing(10)

        # Header
        hdr_row = QWidget(); hdr_row.setStyleSheet("background: transparent;")
        hrl = QHBoxLayout(hdr_row); hrl.setContentsMargins(0, 0, 0, 0)
        hdr_lbl = QLabel("Eksport haseł")
        hdr_lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {c['text']}; background: transparent; border: none;")
        hrl.addWidget(hdr_lbl, stretch=1)
        x_btn = _close_btn(hrl, c, self.close)
        hrl.addWidget(x_btn)
        root.addWidget(hdr_row)

        sep = AnimatedGradientWidget(accent=c["accent"], base=c["bg"], direction="h", anim_mode="slide")
        sep.setFixedHeight(2); sep.start_animation()
        root.addWidget(sep)

        hint = QLabel("Wybierz format eksportu:")
        hint.setStyleSheet(f"font-size: 12px; color: {c['muted']};")
        root.addWidget(hint)

        # Karty formatów
        self._selected = "aegis"
        self._cards: dict[str, QFrame] = {}
        self._bg_sel  = bg_sel
        self._bdr_sel = c["accent"]
        self._bg_card = c["bg_card"]
        self._bdr_norm = bdr_norm

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(0)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.viewport().setStyleSheet("background: transparent;")
        inner = QWidget(); inner.setStyleSheet("background: transparent;")
        fl = QVBoxLayout(inner); fl.setSpacing(6); fl.setContentsMargins(0, 0, 0, 0)

        for fmt_id, fmt_name, fmt_desc, _, _ in self._FORMATS:
            card = QFrame(); card.setFixedHeight(62)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            self._cards[fmt_id] = card
            cl = QHBoxLayout(card); cl.setContentsMargins(12, 8, 12, 8); cl.setSpacing(10)
            text_w = QWidget(); text_w.setStyleSheet("background: transparent; border: none;")
            tl = QVBoxLayout(text_w); tl.setContentsMargins(0, 0, 0, 0); tl.setSpacing(2)
            name_lbl = QLabel(fmt_name)
            name_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {c['text']};")
            desc_lbl = QLabel(fmt_desc)
            desc_lbl.setStyleSheet(f"font-size: 11px; color: {c['muted']};")
            tl.addWidget(name_lbl); tl.addWidget(desc_lbl)
            cl.addWidget(text_w, stretch=1)
            fl.addWidget(card)
            card.mousePressEvent = lambda _, fid=fmt_id: self._select(fid)

        fl.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        # Ostrzeżenie — collapsed gdy niewidoczne (nie rezerwuje miejsca)
        self._warn_lbl = QLabel(
            "⚠️  Ten format zawiera hasła w postaci niezaszyfrowanej.\n"
            "Przechowuj plik w bezpiecznym miejscu i usuń po użyciu."
        )
        self._warn_lbl.setWordWrap(True)
        self._warn_lbl.setFixedHeight(52)
        self._warn_lbl.setStyleSheet(
            f"color: #f0a500; font-size: 11px; font-weight: bold; "
            f"background: {'#2a1e00' if dark else '#fff8e1'}; border-radius: 8px; padding: 8px 10px;"
        )
        self._warn_lbl.setVisible(False)
        self._warn_lbl.setMaximumHeight(0)
        root.addWidget(self._warn_lbl)

        # Przyciski — stała wysokość
        btn_row = QWidget(); btn_row.setStyleSheet("background: transparent;")
        btn_row.setFixedHeight(78)
        brl = QHBoxLayout(btn_row); brl.setContentsMargins(0, 16, 0, 20); brl.setSpacing(8)
        cancel = QPushButton("Anuluj"); cancel.setFixedHeight(42)
        cancel.setStyleSheet(
            f"background: transparent; border: 1.5px solid {c['bdr']}; "
            f"color: {c['muted']}; border-radius: 10px; font-size: 13px;"
        )
        cancel.clicked.connect(self.close)
        brl.addWidget(cancel)
        self._export_btn = QPushButton("Eksportuj →"); self._export_btn.setFixedHeight(42)
        self._export_btn.setStyleSheet(
            f"background: {c['accent']}; color: white; border-radius: 10px; "
            "font-size: 13px; font-weight: bold;"
        )
        self._export_btn.clicked.connect(self._do_export)
        brl.addWidget(self._export_btn)
        root.addWidget(btn_row)

        self._c = c
        self._select("aegis")
        self._export_done_sig.connect(self._done)
        self._export_err_sig.connect(self._error)

    def _select(self, fmt_id: str):
        self._selected = fmt_id
        for fid, card in self._cards.items():
            sel = (fid == fmt_id)
            card.setStyleSheet(
                f"QFrame {{ background: {self._bg_sel if sel else self._bg_card}; "
                f"border: {'2px' if sel else '1px'} solid {self._bdr_sel if sel else self._bdr_norm}; "
                f"border-radius: 10px; }}"
            )
        show_warn = fmt_id != "aegis"
        self._warn_lbl.setVisible(show_warn)
        self._warn_lbl.setMaximumHeight(52 if show_warn else 0)

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
                    count = self._db.export_passwords(self._user, self._crypto, path)
                else:
                    entries = collect_entries(self._db, self._crypto, self._user)
                    if self._selected == "csv":          count = export_csv(entries, path)
                    elif self._selected == "bitwarden":  count = export_bitwarden_json(entries, path)
                    elif self._selected == "1password":  count = export_1password_csv(entries, path)
                    elif self._selected == "keepass":    count = export_keepass_xml(entries, path)
                self._export_done_sig.emit(count, path)
            except Exception as e:
                self._export_err_sig.emit(str(e))

        threading.Thread(target=_run, daemon=True).start()

    def _done(self, count: int, path: str):
        self._export_btn.setEnabled(True)
        self._export_btn.setText("Eksportuj →")
        self._db.log_event(self._user, "export",
                           details=f"{self._selected} • {count} wpisów • {os.path.basename(path)}")
        show_success("Eksport zakończony", f"Wyeksportowano {count} haseł.\n\n{os.path.basename(path)}", parent=self)
        self.close()

    def _error(self, msg: str):
        self._export_btn.setEnabled(True)
        self._export_btn.setText("Eksportuj →")
        show_error("Błąd eksportu", msg, parent=self)
