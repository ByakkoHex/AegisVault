"""
settings_window.py — Panel ustawień (PyQt6)
============================================
In-app overlay — nie osobne okno. Wsuwa się z prawej strony
przez QPropertyAnimation(self, b"geometry") — zero shutterów.

Zakładki (QStackedWidget):
  0 — Wygląd    (dark/light, kolor akcentu, hex custom)
  1 — Bezpieczeństwo (WH, auto-lock, zmiana hasła, reset 2FA, auto-type)
  2 — System    (Ctrl+W, autostart, backup, usunięcie konta, logi)

Użycie z MainWindow:
    self._settings = SettingsPanel(self, db, crypto, user,
                                   on_close=self._on_settings_close,
                                   on_logout=self._logout,
                                   on_theme_change=self._apply_theme)
    self._settings.setGeometry(self.width(), 0, self.width(), self.height())
    self._settings.hide()
    # Otwórz:
    self._settings.slide_in(self)
    # Zamknij (wywołane przez panel samodzielnie przez on_close):
    self._settings.slide_out()
"""

import platform
import threading
from PIL import Image

from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QLineEdit,
    QScrollArea, QVBoxLayout, QHBoxLayout, QGridLayout,
    QStackedWidget, QSlider, QComboBox, QDialog,
    QSizePolicy, QButtonGroup,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QPixmap, QImage

from database.db_manager import DatabaseManager
from core.crypto import CryptoManager, hash_master_password, verify_master_password, generate_salt, KDF_ARGON2ID
from core.totp import TOTPManager
from utils.prefs_manager import PrefsManager, THEMES
import utils.windows_hello as wh
import utils.autostart as autostart
from utils.logger import get_logger, cleanup_old_logs

from gui_qt.gradient  import AnimatedGradientWidget
from gui_qt.dialogs   import show_error, show_info, show_success, ask_yes_no
from gui_qt.app       import apply_theme
from gui_qt.style     import build_qss

logger = get_logger(__name__)

_ON_WINDOWS = platform.system() == "Windows"


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qi = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qi)


# ══════════════════════════════════════════════════════════════════════
# SettingsPanel
# ══════════════════════════════════════════════════════════════════════

class SettingsPanel(QWidget):
    """
    Fullscreen settings overlay widget.
    Nie jest osobnym oknem — jest dzieckiem MainWindow, wysuwa się
    z prawej strony przez QPropertyAnimation.
    """

    # Sygnały thread-safe (Windows Hello działa w osobnym wątku)
    _wh_status_ready = pyqtSignal(str, bool)   # (availability_status, is_enabled)

    def __init__(
        self,
        parent: QWidget,
        db: DatabaseManager,
        crypto: CryptoManager,
        user,
        on_close,
        on_logout=None,
        on_theme_change=None,
    ):
        super().__init__(parent)
        self.db              = db
        self.crypto          = crypto
        self.user            = user
        self.on_close        = on_close
        self.on_logout       = on_logout
        self.on_theme_change = on_theme_change
        self._prefs          = PrefsManager()
        self._anim: QPropertyAnimation | None = None

        self._wh_status_ready.connect(self._wh_update_ui)

        self._build_ui()

        from gui_qt.hex_background import HexBackground
        self._hex_bg = HexBackground(self, hex_size=32, glow_max=2, glow_interval_ms=2000)
        self._hex_bg.setGeometry(0, 0, self.width(), self.height())
        self._hex_bg.lower()

    # ── Animacje slide ────────────────────────────────────────────────

    def paintEvent(self, event):
        """Gwarantuje pełne, nieprzezroczyste tło — QSS na child QWidget bywa zawodny."""
        from PyQt6.QtGui import QPainter, QColor
        dark = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
        bg = "#1a1a1a" if dark else "#f5f5f5"
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(bg))
        painter.end()

    def slide_in(self, main_window: QWidget) -> None:
        """Wsuwa panel z prawej krawędzi main_window."""
        mw = main_window.width()
        mh = main_window.height()
        # Fallback: centralWidget may not have laid out yet right after rebuild
        if mw == 0 or mh == 0:
            win = main_window.window()
            mw = win.width()
            mh = win.height()
        self.setGeometry(mw, 0, mw, mh)
        self.show()
        self.raise_()

        if hasattr(self, '_hex_bg') and self._hex_bg:
            self._hex_bg.setGeometry(0, 0, mw, mh)
            self._hex_bg.lower()

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(220)
        self._anim.setStartValue(QRect(mw, 0, mw, mh))
        self._anim.setEndValue(QRect(0, 0, mw, mh))
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def slide_out(self) -> None:
        """Wysuwa panel poza prawy ekran i chowa po zakończeniu."""
        w = self.width()
        h = self.height()
        cur = self.geometry()

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(200)
        self._anim.setStartValue(cur)
        self._anim.setEndValue(QRect(w, cur.y(), w, h))
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.finished.connect(self.hide)
        self._anim.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_hex_bg') and self._hex_bg:
            self._hex_bg.setGeometry(0, 0, self.width(), self.height())
            self._hex_bg.lower()

    # ── Budowa UI ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        accent = self._prefs.get_accent()
        dark   = (self._prefs.get("appearance_mode") or "dark").lower() != "light"

        bg      = "#1a1a1a" if dark else "#f5f5f5"
        hdr_bg  = "#1e1e1e" if dark else "#f0f0f0"
        sep_clr = "#2a2a2a" if dark else "#d0d0d0"

        self.setObjectName("SettingsPanel")
        # WA_StyledBackground wymagane żeby QSS background działał na QWidget
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#SettingsPanel {{ background: {bg}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Nagłówek ─────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(56)
        hdr.setStyleSheet(f"background: {hdr_bg}; border: none;")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(12, 0, 16, 0)

        back_btn = QPushButton("← Wstecz")
        back_btn.setFixedHeight(32)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {accent}; font-size: 13px; padding: 0 10px;
                border-radius: 6px;
            }}
            QPushButton:hover {{ background: {'#2a2a2a' if dark else '#e0e0e0'}; }}
        """)
        back_btn.clicked.connect(self._safe_close)
        hdr_layout.addWidget(back_btn)

        title_lbl = QLabel("Ustawienia")
        title_lbl.setStyleSheet(
            f"color: {'#f0f0f0' if dark else '#1a1a1a'}; font-size: 18px; font-weight: bold;"
        )
        hdr_layout.addWidget(title_lbl)
        hdr_layout.addStretch()

        self._user_lbl = QLabel(f"  {self.user.username}")
        self._user_lbl.setStyleSheet(f"color: {accent}; font-size: 12px;")
        hdr_layout.addWidget(self._user_lbl)

        root.addWidget(hdr)

        # Gradient separator 2px
        self._hdr_sep = AnimatedGradientWidget(
            accent=accent, base=bg,
            direction="h",
            anim_mode="slide",
            fps=20,
            period_ms=6000,
        )
        self._hdr_sep.setFixedHeight(2)
        self._hdr_sep.start_animation()
        root.addWidget(self._hdr_sep)

        # ── Pasek zakładek ────────────────────────────────────────────
        tab_bar = QFrame()
        tab_bar.setFixedHeight(46)
        tab_bar.setStyleSheet(
            f"background: {'#181818' if dark else '#e8e8e8'}; border: none;"
        )
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        self._tab_btns: dict[str, QPushButton] = {}
        self._tab_stack = QStackedWidget()
        self._tab_stack.setStyleSheet("background: transparent;")

        for idx, (label, tid) in enumerate([
            ("Wygląd",           "appearance"),
            ("Bezpieczeństwo",   "security"),
            ("System",           "system"),
        ]):
            btn = QPushButton(label)
            btn.setFixedHeight(46)
            btn.setCheckable(True)
            btn.setStyleSheet(self._tab_btn_style(accent, dark, False))
            btn.clicked.connect(lambda checked, t=tid: self._switch_tab(t))
            tab_layout.addWidget(btn)
            self._tab_btns[tid] = btn

        tab_layout.addStretch()
        root.addWidget(tab_bar)

        # Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {sep_clr};")
        root.addWidget(sep)

        # ── Zawartość zakładek ────────────────────────────────────────
        root.addWidget(self._tab_stack, stretch=1)

        # Buduj każdą zakładkę
        for tid, builder in [
            ("appearance", self._build_appearance),
            ("security",   self._build_security),
            ("system",     self._build_system),
        ]:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("background: transparent; border: none;")
            scroll.viewport().setStyleSheet("background: transparent;")

            content = QWidget()
            content.setStyleSheet("background: transparent;")
            vl = QVBoxLayout(content)
            vl.setContentsMargins(16, 12, 16, 32)
            vl.setSpacing(12)

            builder(vl, dark, accent)
            vl.addStretch()

            scroll.setWidget(content)
            self._tab_stack.addWidget(scroll)

        # ── Dolny pasek ───────────────────────────────────────────────
        bot_sep = QFrame()
        bot_sep.setFixedHeight(1)
        bot_sep.setStyleSheet(f"background: {sep_clr};")
        root.addWidget(bot_sep)

        close_btn = QPushButton("← Wstecz")
        close_btn.setFixedHeight(42)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {'#888' if dark else '#555'}; font-size: 13px;
            }}
            QPushButton:hover {{ background: {'#252525' if dark else '#e8e8e8'}; }}
        """)
        close_btn.clicked.connect(self._safe_close)
        root.addWidget(close_btn)

        self._switch_tab("appearance")

    # ── Tab helpers ───────────────────────────────────────────────────

    def _tab_btn_style(self, accent: str, dark: bool, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    background: {'#202020' if dark else '#e0e0e0'};
                    border: none; border-bottom: 2px solid {accent};
                    color: {accent}; font-size: 13px; padding: 0 16px;
                }}
            """
        return f"""
            QPushButton {{
                background: transparent; border: none;
                color: {'#888' if dark else '#666'}; font-size: 13px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {'#222' if dark else '#e8e8e8'}; }}
        """

    def _switch_tab(self, tab_id: str) -> None:
        accent = self._prefs.get_accent()
        dark   = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
        for tid, btn in self._tab_btns.items():
            active = (tid == tab_id)
            btn.setChecked(active)
            btn.setStyleSheet(self._tab_btn_style(accent, dark, active))
        idx_map = {"appearance": 0, "security": 1, "system": 2}
        self._tab_stack.setCurrentIndex(idx_map[tab_id])

    # ── Card / Row helpers ────────────────────────────────────────────

    @staticmethod
    def _card(parent_layout: QVBoxLayout, title: str,
              dark: bool) -> QVBoxLayout:
        """Karta sekcji z nagłówkiem. Zwraca layout karty."""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {'#252525' if dark else '#ffffff'};
                border-radius: 12px;
                border: 1px solid {'#333' if dark else '#ddd'};
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 10)
        cl.setSpacing(0)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {'#f0f0f0' if dark else '#1a1a1a'}; font-size: 13px; "
            f"font-weight: bold; padding: 14px 16px 6px 16px; background: transparent; border: none;"
        )
        cl.addWidget(title_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {'#333' if dark else '#ddd'}; border: none; margin: 0 16px;")
        cl.addWidget(sep)

        parent_layout.addWidget(card)
        return cl

    @staticmethod
    def _row(card_layout: QVBoxLayout, title: str, subtitle: str,
             dark: bool) -> QHBoxLayout:
        """Wiersz: tekst po lewej, widget po prawej. Zwraca right_layout."""
        row = QWidget()
        row.setStyleSheet("background: transparent; border: none;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(16, 4, 16, 4)

        left = QVBoxLayout()
        left.setSpacing(1)
        t = QLabel(title)
        t.setStyleSheet(f"color: {'#f0f0f0' if dark else '#1a1a1a'}; font-size: 13px;")
        left.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setWordWrap(True)
            s.setStyleSheet("color: #888; font-size: 11px;")
            left.addWidget(s)
        rl.addLayout(left, stretch=1)

        right = QHBoxLayout()
        right.setSpacing(6)
        rl.addLayout(right)

        card_layout.addWidget(row)
        return right

    @staticmethod
    def _action_btn(card_layout: QVBoxLayout, text: str, fn,
                    color: str = "#1f6aa5", hover: str = "#1a5a94",
                    text_color: str = "white") -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(38)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color}; color: {text_color};
                border-radius: 10px; font-size: 13px; font-weight: bold;
                margin: 4px 16px; padding: 0;
            }}
            QPushButton:hover {{ background: {hover}; }}
        """)
        btn.clicked.connect(fn)
        card_layout.addWidget(btn)
        return btn

    def _safe_close(self) -> None:
        try:
            self._hdr_sep.stop_animation()
        except Exception:
            pass
        try:
            self.on_close()
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════
    # ZAKŁADKA: WYGLĄD
    # ══════════════════════════════════════════════════════════════════

    def _build_appearance(self, vl: QVBoxLayout, dark: bool, accent: str) -> None:
        # ── Tryb ciemny/jasny ─────────────────────────────────────────
        card1 = self._card(vl, "Tryb wyświetlania", dark)
        right1 = self._row(card1, "Tryb",
                           "Przełącz między jasnym a ciemnym interfejsem.", dark)

        # Przełącznik słońce/księżyc
        toggle_frame = QFrame()
        toggle_frame.setFixedSize(80, 36)
        toggle_frame.setStyleSheet(
            f"background: {'#2a2a2a' if dark else '#e0e0e0'}; border-radius: 18px; border: none;"
        )
        tf_layout = QHBoxLayout(toggle_frame)
        tf_layout.setContentsMargins(2, 2, 2, 2)
        tf_layout.setSpacing(0)

        sun_btn  = QPushButton("☀")
        moon_btn = QPushButton("🌙")
        for b in (sun_btn, moon_btn):
            b.setFixedSize(36, 32)
            b.setStyleSheet(
                "QPushButton { background: transparent; border: none; font-size: 16px; "
                "font-family: 'Segoe UI Emoji','Segoe UI Symbol','Apple Color Emoji',sans-serif; "
                "border-radius: 16px; padding: 0; color: #888; }"
                "QPushButton:hover { background: rgba(128,128,128,0.2); }"
            )
        # Highlight active side
        _active_style = (
            f"QPushButton {{ background: {accent}; border: none; font-size: 16px; "
            f"font-family: 'Segoe UI Emoji','Segoe UI Symbol','Apple Color Emoji',sans-serif; "
            f"border-radius: 16px; padding: 0; color: white; }}"
        )
        if dark:
            moon_btn.setStyleSheet(_active_style)
        else:
            sun_btn.setStyleSheet(_active_style)

        def _set_theme(new_dark: bool):
            self._prefs.set("appearance_mode", "dark" if new_dark else "light")
            apply_theme(dark=new_dark)
            if new_dark:
                moon_btn.setStyleSheet(_active_style)
                sun_btn.setStyleSheet(
                    "QPushButton { background: transparent; border: none; font-size: 16px; "
                    "font-family: 'Segoe UI Emoji','Segoe UI Symbol','Apple Color Emoji',sans-serif; "
                    "border-radius: 16px; padding: 0; color: #888; }"
                    "QPushButton:hover { background: rgba(128,128,128,0.2); }"
                )
                toggle_frame.setStyleSheet(
                    "background: #2a2a2a; border-radius: 18px; border: none;"
                )
            else:
                sun_btn.setStyleSheet(_active_style)
                moon_btn.setStyleSheet(
                    "QPushButton { background: transparent; border: none; font-size: 16px; "
                    "font-family: 'Segoe UI Emoji','Segoe UI Symbol','Apple Color Emoji',sans-serif; "
                    "border-radius: 16px; padding: 0; color: #888; }"
                    "QPushButton:hover { background: rgba(128,128,128,0.2); }"
                )
                toggle_frame.setStyleSheet(
                    "background: #e0e0e0; border-radius: 18px; border: none;"
                )
            if self.on_theme_change:
                self.on_theme_change(self._prefs.get("color_theme") or "blue")

        sun_btn.clicked.connect(lambda: _set_theme(False))
        moon_btn.clicked.connect(lambda: _set_theme(True))

        tf_layout.addWidget(sun_btn)
        tf_layout.addWidget(moon_btn)
        right1.addWidget(toggle_frame)

        # ── Kolor akcentu ─────────────────────────────────────────────
        card2 = self._card(vl, "Kolor akcentu", dark)

        current = self._prefs.get("color_theme") or "blue"

        # Podgląd
        preview_row = QWidget()
        preview_row.setStyleSheet("background: transparent; border: none;")
        pr = QHBoxLayout(preview_row)
        pr.setContentsMargins(16, 0, 16, 6)
        lbl_act = QLabel("Aktywny:")
        lbl_act.setStyleSheet("color: #888; font-size: 12px; background: transparent; border: none;")
        pr.addWidget(lbl_act)
        self._theme_name_lbl = QLabel(THEMES.get(current, {}).get("label", ""))
        self._theme_name_lbl.setStyleSheet(
            f"color: {accent}; font-size: 12px; font-weight: bold; background: transparent; border: none;"
        )
        pr.addWidget(self._theme_name_lbl)
        pr.addStretch()
        card2.addWidget(preview_row)

        # Pasek akcentu
        self._accent_bar = QFrame()
        self._accent_bar.setFixedHeight(6)
        self._accent_bar.setStyleSheet(
            f"background: {THEMES.get(current, {}).get('accent', accent)}; "
            "border-radius: 3px; margin: 0 16px; border: none;"
        )
        card2.addWidget(self._accent_bar)

        # Siatka swatchy — 5 kolumn
        COLS = 5
        theme_list = list(THEMES.items())
        swatch_widget = QWidget()
        swatch_widget.setStyleSheet("background: transparent; border: none;")
        swatch_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sw_grid = QGridLayout(swatch_widget)
        sw_grid.setContentsMargins(16, 12, 16, 12)
        sw_grid.setSpacing(12)
        sw_grid.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._swatch_btns: dict[str, QPushButton] = {}
        for idx, (tid, tdata) in enumerate(theme_list):
            row_i, col_i = divmod(idx, COLS)
            is_sel = (tid == current)
            btn = QPushButton("✔" if is_sel else "")
            btn.setFixedSize(52, 52)
            btn.setStyleSheet(self._swatch_style(tdata["accent"], tdata["hover"], is_sel))
            btn.setToolTip(tdata["label"])
            btn.clicked.connect(lambda _, t=tid: self._select_color_theme(t))
            sw_grid.addWidget(btn, row_i, col_i)
            self._swatch_btns[tid] = btn

            # Hover: pokaż nazwę i zmień kolor
            def _enter(event, n=tdata["label"], a=tdata["accent"]):
                self._theme_name_lbl.setText(n)
                self._theme_name_lbl.setStyleSheet(
                    f"color: {a}; font-size: 12px; font-weight: bold; background: transparent; border: none;"
                )
                self._accent_bar.setStyleSheet(
                    f"background: {a}; border-radius: 3px; margin: 0 16px; border: none;"
                )
            def _leave(event):
                cur_t = self._prefs.get("color_theme") or "blue"
                cur_a = self._prefs.get_accent()
                self._theme_name_lbl.setText(
                    THEMES.get(cur_t, {}).get("label", "Własny")
                )
                self._theme_name_lbl.setStyleSheet(
                    f"color: {cur_a}; font-size: 12px; font-weight: bold; background: transparent; border: none;"
                )
                self._accent_bar.setStyleSheet(
                    f"background: {cur_a}; "
                    "border-radius: 3px; margin: 0 16px; border: none;"
                )
            btn.enterEvent = _enter
            btn.leaveEvent = _leave

        card2.addWidget(swatch_widget)

        # Własny kolor hex
        hex_row = QWidget()
        hex_row.setStyleSheet("background: transparent; border: none;")
        hrl = QHBoxLayout(hex_row)
        hrl.setContentsMargins(16, 0, 16, 12)

        hash_lbl = QLabel("#")
        hash_lbl.setStyleSheet("color: #888; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        hrl.addWidget(hash_lbl)

        self._hex_entry = QLineEdit()
        self._hex_entry.setPlaceholderText("4F8EF7")
        self._hex_entry.setMaxLength(6)
        self._hex_entry.setFixedSize(100, 32)
        self._hex_entry.setStyleSheet(f"""
            QLineEdit {{
                background: {'#2a2a2a' if dark else '#f0f0f0'};
                color: {'#f0f0f0' if dark else '#1a1a1a'};
                border: 1px solid {'#444' if dark else '#ccc'};
                border-radius: 6px; padding: 0 8px;
                font-family: 'Courier New', monospace; font-size: 12px;
            }}
        """)
        cur_accent = self._prefs.get_accent()
        self._hex_entry.setText(cur_accent.lstrip("#"))
        hrl.addWidget(self._hex_entry)

        self._hex_preview = QFrame()
        self._hex_preview.setFixedSize(40, 32)
        self._hex_preview.setStyleSheet(
            f"background: {cur_accent}; border-radius: 8px; border: none;"
        )
        hrl.addWidget(self._hex_preview)
        hrl.addStretch()
        card2.addWidget(hex_row)

        self._hex_debounce = QTimer(self)
        self._hex_debounce.setSingleShot(True)
        self._hex_debounce.setInterval(300)
        self._hex_debounce.timeout.connect(self._on_hex_debounced)
        self._hex_entry.textChanged.connect(
            lambda _: self._hex_debounce.start()
        )

    def _toggle_style(self, accent: str, checked: bool, dark: bool = True) -> str:
        off_bg = "#3a3a3a" if dark else "#d8d8d8"
        off_fg = "#aaaaaa" if dark else "#666666"
        if checked:
            return f"""
                QPushButton {{
                    background: {accent}; color: white;
                    border-radius: 8px; font-size: 12px; font-weight: bold;
                    padding: 0 8px; min-height: 0;
                }}
            """
        return f"""
            QPushButton {{
                background: {off_bg}; color: {off_fg};
                border-radius: 8px; font-size: 12px;
                padding: 0 8px; min-height: 0;
            }}
        """

    @staticmethod
    def _swatch_style(accent: str, hover: str, selected: bool) -> str:
        border = "border: 3px solid white;" if selected else "border: none;"
        return f"""
            QPushButton {{
                background: {accent}; color: white;
                border-radius: 14px; font-size: 17px; font-weight: bold;
                {border}
            }}
            QPushButton:hover {{ background: {hover}; }}
        """

    def _on_hex_debounced(self) -> None:
        val = self._hex_entry.text().strip().lstrip("#")
        if len(val) == 6:
            try:
                int(val, 16)
                color = f"#{val}"
                self._hex_preview.setStyleSheet(
                    f"background: {color}; border-radius: 8px; border: none;"
                )
                self._hex_entry.setStyleSheet(
                    self._hex_entry.styleSheet().replace("#e05252", "#444").replace("#f0a500", "#444")
                )
                # Szukaj pasującego swacha
                for tid, tdata in THEMES.items():
                    if tdata["accent"].lower() == color.lower():
                        self._select_color_theme(tid)
                        return
                # Custom
                self._prefs.set("accent_custom", color)
                self._prefs.set("color_theme", "custom")
                self._theme_name_lbl.setText("Własny")
                self._accent_bar.setStyleSheet(
                    f"background: {color}; border-radius: 3px; margin: 0 16px; border: none;"
                )
                for b in self._swatch_btns.values():
                    b.setText("")
                    b.setStyleSheet(b.styleSheet().replace("border: 2px solid white;", "border: none;"))
                if self.on_theme_change:
                    self.on_theme_change("custom")
            except ValueError:
                pass
        elif len(val) == 0:
            self._hex_preview.setStyleSheet(
                f"background: {self._prefs.get_accent()}; border-radius: 8px; border: none;"
            )

    def _select_color_theme(self, theme_id: str) -> None:
        self._prefs.set("color_theme", theme_id)
        tdata = self._prefs.get_theme_colors()
        new_accent = tdata.get("accent", "#4F8EF7")

        for tid, btn in self._swatch_btns.items():
            sel = (tid == theme_id)
            btn.setText("✔" if sel else "")
            btn.setStyleSheet(self._swatch_style(
                THEMES[tid]["accent"], THEMES[tid]["hover"], sel
            ))

        self._theme_name_lbl.setText(tdata.get("label", ""))
        self._accent_bar.setStyleSheet(
            f"background: {new_accent}; border-radius: 3px; margin: 0 16px; border: none;"
        )
        self._hex_entry.setText(new_accent.lstrip("#"))
        self._hex_preview.setStyleSheet(
            f"background: {new_accent}; border-radius: 8px; border: none;"
        )
        # Aktualizuj etykietę usera
        self._user_lbl.setStyleSheet(f"color: {new_accent}; font-size: 12px;")

        if self.on_theme_change:
            self.on_theme_change(theme_id)

    def _toggle_theme(self, checked: bool, btn: QPushButton, accent: str) -> None:
        btn.setText("Ciemny" if checked else "Jasny")
        btn.setStyleSheet(self._toggle_style(accent, checked))
        mode = "dark" if checked else "light"
        self._prefs.set("appearance_mode", mode)
        apply_theme(dark=(mode == "dark"))
        if self.on_theme_change:
            self.on_theme_change(self._prefs.get("color_theme") or "blue")

    # ══════════════════════════════════════════════════════════════════
    # ZAKŁADKA: BEZPIECZEŃSTWO
    # ══════════════════════════════════════════════════════════════════

    def _build_security(self, vl: QVBoxLayout, dark: bool, accent: str) -> None:
        # ── Windows Hello ─────────────────────────────────────────────
        card_wh = self._card(vl, "Windows Hello", dark)

        right_wh = self._row(
            card_wh, "Logowanie biometryczne",
            "Użyj odcisku palca, twarzy lub PIN-u zamiast hasła masterowego.", dark
        )
        self._wh_badge = QLabel("…")
        self._wh_badge.setStyleSheet("color: #888; font-size: 11px; background: transparent; border: none;")
        right_wh.addWidget(self._wh_badge)

        wh_row = QWidget()
        wh_row.setStyleSheet("background: transparent; border: none;")
        wrl = QHBoxLayout(wh_row)
        wrl.setContentsMargins(16, 0, 16, 14)

        self._wh_enable_btn = QPushButton("Włącz Windows Hello")
        self._wh_enable_btn.setFixedHeight(38)
        self._wh_enable_btn.setStyleSheet("""
            QPushButton { background: #2d6a4f; color: white; border-radius: 10px;
                          font-size: 12px; font-weight: bold; }
            QPushButton:hover { background: #40916c; }
            QPushButton:disabled { background: #1e1e1e; color: #555; }
        """)
        self._wh_enable_btn.clicked.connect(self._wh_enable)
        wrl.addWidget(self._wh_enable_btn)

        self._wh_disable_btn = QPushButton("Wyłącz")
        self._wh_disable_btn.setFixedHeight(38)
        self._wh_disable_btn.setFixedWidth(90)
        self._wh_disable_btn.setStyleSheet("""
            QPushButton { background: #4a1a1a; color: #ff8080; border-radius: 10px;
                          font-size: 12px; font-weight: bold; }
            QPushButton:hover { background: #5a2020; }
            QPushButton:disabled { background: #1e1e1e; color: #555; }
        """)
        self._wh_disable_btn.clicked.connect(self._wh_disable)
        wrl.addWidget(self._wh_disable_btn)

        card_wh.addWidget(wh_row)

        if not _ON_WINDOWS:
            self._wh_enable_btn.setEnabled(False)
            self._wh_enable_btn.setText("Niedostępne (tylko Windows)")
            self._wh_disable_btn.setEnabled(False)
            self._wh_badge.setText("Niedostępne")
        else:
            threading.Thread(target=self._wh_check_status_thread, daemon=True).start()

        # WH na ekranie blokady
        right_whl = self._row(
            card_wh, "Odblokuj przez Windows Hello",
            "Zamiast hasła masterowego — użyj biometrii na ekranie blokady.", dark
        )
        self._wh_lock_btn = QPushButton(
            "Włączone" if self._prefs.get("wh_lock_unlock") else "Wyłączone"
        )
        self._wh_lock_btn.setCheckable(True)
        self._wh_lock_btn.setChecked(bool(self._prefs.get("wh_lock_unlock")))
        self._wh_lock_btn.setFixedSize(110, 32)
        self._wh_lock_btn.setStyleSheet(
            self._toggle_style(accent, bool(self._prefs.get("wh_lock_unlock")), dark)
        )
        self._wh_lock_btn.toggled.connect(self._on_wh_lock_toggle)
        right_whl.addWidget(self._wh_lock_btn)

        # ── Auto-lock ─────────────────────────────────────────────────
        card_al = self._card(vl, "Automatyczne blokowanie", dark)
        self._row(
            card_al, "Zablokuj po bezczynności",
            "Aplikacja zablokuje się po wybranym czasie bez aktywności.", dark
        )

        _al_labels = ["1 min", "5 min", "15 min", "30 min", "1 godz", "Nigdy"]
        _al_values = [60, 300, 900, 1800, 3600, 0]
        self._al_map = dict(zip(_al_labels, _al_values))
        self._al_rev = {v: k for k, v in self._al_map.items()}
        cur_al = self._prefs.get("auto_lock_seconds") or 300

        al_row = QWidget()
        al_row.setStyleSheet("background: transparent; border: none;")
        alrl = QHBoxLayout(al_row)
        alrl.setContentsMargins(16, 0, 16, 14)
        alrl.setSpacing(6)
        for lbl in _al_labels:
            b = QPushButton(lbl)
            b.setFixedHeight(32)
            b.setCheckable(True)
            b.setChecked(self._al_rev.get(cur_al) == lbl)
            b.setStyleSheet(self._seg_style(accent, dark, self._al_rev.get(cur_al) == lbl))
            b.toggled.connect(lambda checked, l=lbl, btn=b: self._on_al_change(l, btn, accent, dark) if checked else None)
            alrl.addWidget(b)
        alrl.addStretch()
        self._al_btns = {lbl: alrl.itemAt(i).widget() for i, lbl in enumerate(_al_labels)}
        card_al.addWidget(al_row)

        # ── Zmiana hasła ──────────────────────────────────────────────
        card_pwd = self._card(vl, "Hasło masterowe", dark)
        self._row(card_pwd, "Zmiana hasła masterowego",
                  "Wymaga podania aktualnego hasła oraz kodu 2FA.", dark)
        self._action_btn(card_pwd, "Zmień hasło masterowe",
                         self._show_reset_password, "#1f6aa5", "#1a5a94")

        # ── Reset 2FA ─────────────────────────────────────────────────
        card_2fa = self._card(vl, "Uwierzytelnianie dwuetapowe", dark)
        self._row(card_2fa, "Wygeneruj nowy kod QR",
                  "Przydatne przy zmianie telefonu lub aplikacji 2FA.", dark)
        self._action_btn(card_2fa, "Wygeneruj nowy QR",
                         self._show_reset_2fa, "#2d6a4f", "#40916c")

        # ── Auto-type ─────────────────────────────────────────────────
        card_at = self._card(vl, "Auto-Type", dark)
        self._row(card_at, "Opóźnienie przed wpisaniem",
                  "Czas na przełączenie się na okno logowania po kliknięciu Auto-type.", dark)

        _at_labels = ["1s", "2s", "3s", "5s"]
        _at_values = [1, 2, 3, 5]
        self._at_map = dict(zip(_at_labels, _at_values))
        self._at_rev = {v: k for k, v in self._at_map.items()}
        cur_at = int(self._prefs.get("autotype_delay") or 2)

        at_row = QWidget()
        at_row.setStyleSheet("background: transparent; border: none;")
        atrl = QHBoxLayout(at_row)
        atrl.setContentsMargins(16, 0, 16, 6)
        atrl.setSpacing(6)
        for lbl in _at_labels:
            b = QPushButton(lbl)
            b.setFixedHeight(30)
            b.setCheckable(True)
            b.setChecked(self._at_rev.get(cur_at) == lbl)
            b.setStyleSheet(self._seg_style(accent, dark, self._at_rev.get(cur_at) == lbl))
            b.toggled.connect(lambda checked, l=lbl: self._on_at_change(l) if checked else None)
            atrl.addWidget(b)
        atrl.addStretch()
        card_at.addWidget(at_row)

        self._row(card_at, "Sekwencja wpisywania",
                  "Tokeny: {USERNAME} {TAB} {PASSWORD} {ENTER} {DELAY=ms}", dark)
        seq_w = QWidget()
        seq_w.setStyleSheet("background: transparent; border: none;")
        seql = QHBoxLayout(seq_w)
        seql.setContentsMargins(16, 0, 16, 14)
        cur_seq = self._prefs.get("autotype_sequence") or "{USERNAME}{TAB}{PASSWORD}{ENTER}"
        self._at_seq_entry = QLineEdit(cur_seq)
        self._at_seq_entry.setFixedHeight(36)
        self._at_seq_entry.setStyleSheet(f"""
            QLineEdit {{
                background: {'#2a2a2a' if dark else '#f0f0f0'};
                color: {'#f0f0f0' if dark else '#1a1a1a'};
                border: 1px solid {'#444' if dark else '#ccc'};
                border-radius: 6px; padding: 0 8px;
                font-family: 'Courier New', monospace; font-size: 12px;
            }}
        """)
        seql.addWidget(self._at_seq_entry)
        save_seq_btn = QPushButton("Zapisz")
        save_seq_btn.setFixedSize(80, 36)
        save_seq_btn.setStyleSheet(f"""
            QPushButton {{ background: {accent}; color: white;
                border-radius: 8px; font-size: 12px; font-weight: bold;
                padding: 0 8px; min-height: 0; }}
            QPushButton:hover {{ background: {self._prefs.get_accent_hover()}; }}
        """)
        save_seq_btn.clicked.connect(self._on_at_seq_save)
        seql.addWidget(save_seq_btn)
        card_at.addWidget(seq_w)

    @staticmethod
    def _seg_style(accent: str, dark: bool, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{ background: {accent}; color: white;
                    border-radius: 6px; font-size: 12px; font-weight: bold;
                    padding: 4px 10px; min-height: 0; }}
            """
        return f"""
            QPushButton {{ background: {'#2a2a2a' if dark else '#e8e8e8'};
                color: {'#aaa' if dark else '#555'};
                border-radius: 6px; font-size: 12px;
                padding: 4px 10px; min-height: 0; }}
            QPushButton:hover {{ background: {'#333' if dark else '#ddd'}; }}
        """

    # ══════════════════════════════════════════════════════════════════
    # ZAKŁADKA: SYSTEM
    # ══════════════════════════════════════════════════════════════════

    def _build_system(self, vl: QVBoxLayout, dark: bool, accent: str) -> None:
        # ── Ctrl+W ───────────────────────────────────────────────────
        card_w = self._card(vl, "Skrót Ctrl+W", dark)
        right_w = self._row(card_w, "Akcja Ctrl+W",
                            "Co ma robić Ctrl+W w głównym oknie aplikacji.", dark)
        cur_cw = self._prefs.get("ctrl_w_action") or "minimize"
        for lbl, val in [("Minimalizuj", "minimize"), ("Zamknij", "close")]:
            b = QPushButton(lbl)
            b.setFixedHeight(30)
            b.setCheckable(True)
            b.setChecked(cur_cw == val)
            b.setStyleSheet(self._seg_style(accent, dark, cur_cw == val))
            b.toggled.connect(lambda checked, v=val, b_=b: (
                self._prefs.set("ctrl_w_action", v), None
            ) if checked else None)
            right_w.addWidget(b)

        # ── Autostart ─────────────────────────────────────────────────
        card_as = self._card(vl, "Autostart", dark)
        right_as = self._row(
            card_as, "Uruchamiaj przy starcie systemu",
            "AegisVault uruchomi się automatycznie po zalogowaniu do systemu.", dark
        )
        as_enabled = autostart.is_enabled()
        as_btn = QPushButton("Włączone" if as_enabled else "Wyłączone")
        as_btn.setCheckable(True)
        as_btn.setChecked(as_enabled)
        as_btn.setFixedSize(110, 32)
        as_btn.setStyleSheet(self._toggle_style(accent, as_enabled, dark))
        as_btn.toggled.connect(lambda checked: self._on_autostart_toggle(checked, as_btn, accent))
        right_as.addWidget(as_btn)

        # ── Automatyczny backup ───────────────────────────────────────
        card_backup = self._card(vl, "Automatyczny backup", dark)
        self._row(card_backup, "Częstotliwość",
                  "Backup zaszyfrowany zapisywany w folderze danych aplikacji.", dark)

        _backup_labels = ["Wyłączony", "Codziennie", "Co 3 dni", "Tygodniowo", "Miesięcznie"]
        _backup_values = ["wyłączony", "codziennie", "co 3 dni", "tygodniowo", "miesięcznie"]
        _l2v = dict(zip(_backup_labels, _backup_values))
        _v2l = dict(zip(_backup_values, _backup_labels))
        cur_int = self._prefs.get("backup_interval") or "wyłączony"

        backup_combo = QComboBox()
        backup_combo.addItems(_backup_labels)
        backup_combo.setCurrentText(_v2l.get(cur_int, "Wyłączony"))
        backup_combo.setStyleSheet(f"""
            QComboBox {{
                background: {'#2a2a2a' if dark else '#f0f0f0'};
                color: {'#f0f0f0' if dark else '#1a1a1a'};
                border: 1px solid {'#444' if dark else '#ccc'};
                border-radius: 8px; padding: 4px 12px; font-size: 12px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background: {'#2a2a2a' if dark else '#fff'};
                color: {'#f0f0f0' if dark else '#1a1a1a'};
                selection-background-color: {accent};
            }}
        """)
        backup_combo.setFixedHeight(36)
        backup_combo.setFixedWidth(200)
        backup_combo.currentTextChanged.connect(
            lambda lbl: self._prefs.set("backup_interval", _l2v.get(lbl, "wyłączony"))
        )

        bw = QWidget()
        bw.setStyleSheet("background: transparent; border: none;")
        bwl = QHBoxLayout(bw)
        bwl.setContentsMargins(16, 0, 16, 8)
        bwl.addWidget(backup_combo)
        bwl.addStretch()
        card_backup.addWidget(bw)

        self._action_btn(card_backup, "Wykonaj backup teraz", self._do_backup_now)

        # ── Strefa niebezpieczna ──────────────────────────────────────
        card_del = self._card(vl, "Strefa niebezpieczna", dark)
        self._row(card_del, "Usuń konto",
                  "Trwale usuwa konto i wszystkie zapisane hasła.\nOperacji nie można cofnąć!", dark)
        self._action_btn(card_del, "Usuń konto", self._show_delete_account,
                         color="#4a1a1a", hover="#5a2020", text_color="#ff8080")

        # ── Logi ──────────────────────────────────────────────────────
        card_logs = self._card(vl, "Logi aplikacji", dark)

        logs_info = QLabel("Pliki logów przechowywane w AppData/AegisVault/logs/")
        logs_info.setStyleSheet("color: #888; font-size: 12px; padding: 0 16px; background: transparent; border: none;")
        card_logs.addWidget(logs_info)

        logs_row = QWidget()
        logs_row.setStyleSheet("background: transparent; border: none;")
        lrl = QHBoxLayout(logs_row)
        lrl.setContentsMargins(16, 4, 16, 4)
        lrl.addWidget(QLabel("Przechowuj logi przez:"))

        self._log_days_lbl = QLabel(f"{self._prefs.get('log_retention_days')} dni")
        self._log_days_lbl.setStyleSheet(
            f"color: {accent}; font-size: 13px; font-weight: bold; background: transparent; border: none;"
        )
        lrl.addStretch()
        lrl.addWidget(self._log_days_lbl)
        card_logs.addWidget(logs_row)

        log_slider = QSlider(Qt.Orientation.Horizontal)
        log_slider.setRange(1, 30)
        log_slider.setValue(self._prefs.get("log_retention_days") or 7)
        log_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ background: {'#333' if dark else '#ccc'}; height: 4px; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {accent}; width: 14px; height: 14px; border-radius: 7px; margin: -5px 0; }}
            QSlider::sub-page:horizontal {{ background: {accent}; height: 4px; border-radius: 2px; }}
        """)
        log_slider.valueChanged.connect(self._on_log_slider)

        sw = QWidget()
        sw.setStyleSheet("background: transparent; border: none;")
        swl = QHBoxLayout(sw)
        swl.setContentsMargins(16, 0, 16, 12)
        swl.addWidget(log_slider)
        card_logs.addWidget(sw)

    # ══════════════════════════════════════════════════════════════════
    # LOGIKA — SYSTEM
    # ══════════════════════════════════════════════════════════════════

    def _on_autostart_toggle(self, checked: bool, btn: QPushButton, accent: str) -> None:
        dark = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
        btn.setText("Włączone" if checked else "Wyłączone")
        btn.setStyleSheet(self._toggle_style(accent, checked, dark))
        if checked:
            if not autostart.enable():
                btn.setChecked(False)
                btn.setText("Wyłączone")
                btn.setStyleSheet(self._toggle_style(accent, False, dark))
                show_error("Błąd", "Nie udało się dodać wpisu autostartu.", parent=self)
        else:
            autostart.disable()

    def _do_backup_now(self) -> None:
        from utils.auto_backup import do_backup
        import os as _os
        path = do_backup(self.db, self.crypto, self.user, self._prefs)
        if path:
            show_success("Backup", f"Backup zapisany:\n{_os.path.basename(path)}", parent=self)
        else:
            show_error("Backup", "Nie udało się wykonać backupu.\nSprawdź logi aplikacji.", parent=self)

    def _on_al_change(self, label: str, btn: QPushButton, accent: str, dark: bool) -> None:
        seconds = self._al_map.get(label, 300)
        self._prefs.set("auto_lock_seconds", seconds)
        # Odznacz pozostałe
        for lbl, b in self._al_btns.items():
            active = (lbl == label)
            b.setStyleSheet(self._seg_style(accent, dark, active))
            if not active and b.isChecked():
                b.blockSignals(True)
                b.setChecked(False)
                b.blockSignals(False)

    def _on_at_change(self, label: str) -> None:
        self._prefs.set("autotype_delay", self._at_map.get(label, 2))

    def _on_at_seq_save(self) -> None:
        seq = self._at_seq_entry.text().strip()
        if not seq:
            seq = "{USERNAME}{TAB}{PASSWORD}{ENTER}"
            self._at_seq_entry.setText(seq)
        self._prefs.set("autotype_sequence", seq)

    def _on_log_slider(self, val: int) -> None:
        self._log_days_lbl.setText(f"{val} dni")
        self._prefs.set("log_retention_days", val)
        cleanup_old_logs(val)

    def _on_wh_lock_toggle(self, checked: bool) -> None:
        accent = self._prefs.get_accent()
        dark = (self._prefs.get("appearance_mode") or "dark").lower() != "light"
        self._wh_lock_btn.setText("Włączone" if checked else "Wyłączone")
        self._wh_lock_btn.setStyleSheet(self._toggle_style(accent, checked, dark))
        self._prefs.set("wh_lock_unlock", checked)

    # ══════════════════════════════════════════════════════════════════
    # LOGIKA — WINDOWS HELLO
    # ══════════════════════════════════════════════════════════════════

    def _wh_check_status_thread(self) -> None:
        status  = wh.check_availability()
        enabled = wh.has_credential(self.user.username)
        self._wh_status_ready.emit(status, enabled)

    def _wh_update_ui(self, status: str, enabled: bool) -> None:
        available = (status == "Available")
        if not available:
            msg = wh.STATUS_MESSAGES.get(status, "Niedostępne")
            self._wh_badge.setText("Niedostępne")
            self._wh_badge.setStyleSheet("color: #e05252; font-size: 11px; background: transparent; border: none;")
            self._wh_enable_btn.setEnabled(False)
            self._wh_enable_btn.setText(msg)
            self._wh_disable_btn.setEnabled(False)
        elif enabled:
            self._wh_badge.setText("Włączone")
            self._wh_badge.setStyleSheet("color: #4caf50; font-size: 11px; background: transparent; border: none;")
            self._wh_enable_btn.setEnabled(False)
            self._wh_disable_btn.setEnabled(True)
        else:
            self._wh_badge.setText("Wyłączone")
            self._wh_badge.setStyleSheet("color: #888; font-size: 11px; background: transparent; border: none;")
            self._wh_enable_btn.setEnabled(True)
            self._wh_disable_btn.setEnabled(False)

    def _wh_enable(self) -> None:
        dialog = self._make_dialog("Włącz Windows Hello", 400, 300)
        vl = QVBoxLayout(dialog)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(8)

        title = QLabel("Włącz Windows Hello")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(title)

        sep = AnimatedGradientWidget(
            accent=self._prefs.get_accent(), base="#1e1e1e", direction="h", anim_mode="slide"
        )
        sep.setFixedHeight(2)
        sep.start_animation()
        vl.addWidget(sep)

        info = QLabel("Potwierdź hasłem masterowym,\naby skojarzyć konto z Windows Hello.")
        info.setStyleSheet("color: #888; font-size: 12px;")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(info)

        pwd_lbl = QLabel("Hasło masterowe")
        vl.addWidget(pwd_lbl)
        entry_pwd = QLineEdit()
        entry_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        entry_pwd.setPlaceholderText("Wpisz hasło...")
        entry_pwd.setFixedHeight(38)
        vl.addWidget(entry_pwd)

        err_lbl = QLabel("")
        err_lbl.setStyleSheet("color: #e05252; font-size: 11px;")
        vl.addWidget(err_lbl)

        btn_row = QWidget()
        brl = QHBoxLayout(btn_row)
        brl.setContentsMargins(0, 0, 0, 0)

        cancel = QPushButton("Anuluj")
        cancel.setFixedHeight(36)
        cancel.setStyleSheet("background: transparent; border: 1px solid #555; color: #aaa; border-radius: 8px;")
        cancel.clicked.connect(dialog.reject)
        brl.addWidget(cancel)

        confirm_btn = QPushButton("Dalej →")
        confirm_btn.setFixedHeight(36)
        confirm_btn.setStyleSheet(
            "background: #2d6a4f; color: white; border-radius: 8px; font-weight: bold;"
        )
        brl.addWidget(confirm_btn)
        vl.addWidget(btn_row)

        QTimer.singleShot(250, entry_pwd.setFocus)

        def _confirm():
            if not verify_master_password(entry_pwd.text(), self.user.master_password_hash):
                err_lbl.setText("Nieprawidłowe hasło masterowe!")
                return
            confirm_btn.setEnabled(False)
            confirm_btn.setText("Oczekiwanie…")
            err_lbl.setText("")
            threading.Thread(
                target=self._wh_do_enable,
                args=(dialog, entry_pwd.text()),
                daemon=True,
            ).start()

        confirm_btn.clicked.connect(_confirm)
        entry_pwd.returnPressed.connect(_confirm)
        dialog.exec()

    def _wh_do_enable(self, dialog: QDialog, master_password: str) -> None:
        verified = wh.verify("Włącz Windows Hello dla AegisVault")
        if not verified:
            QTimer.singleShot(0, lambda: show_error(
                "Windows Hello", "Weryfikacja anulowana lub nieudana.\nSpróbuj ponownie.", parent=self
            ))
            return
        ok = wh.store_credential(self.user.username, master_password)
        if ok:
            wh.invalidate_cache()
            QTimer.singleShot(0, lambda: (
                dialog.accept(),
                show_success("Windows Hello",
                             "Windows Hello zostało włączone.\nMożesz teraz logować się bez hasła.",
                             parent=self),
                self._wh_update_ui("Available", True),
            ))
        else:
            QTimer.singleShot(0, lambda: show_error(
                "Błąd", "Nie można zapisać poświadczeń w Credential Manager.", parent=self
            ))

    def _wh_disable(self) -> None:
        if not ask_yes_no(
            "Wyłącz Windows Hello",
            "Czy na pewno chcesz wyłączyć logowanie Windows Hello?\n"
            "Będziesz musiał ponownie wpisywać hasło masterowe.",
            parent=self, yes_text="Wyłącz",
        ):
            return
        self._wh_disable_btn.setEnabled(False)
        self._wh_disable_btn.setText("Weryfikacja…")

        def _do() -> None:
            verified = wh.verify("Wyłącz Windows Hello — AegisVault")
            if not verified:
                QTimer.singleShot(0, lambda: (
                    self._wh_disable_btn.setEnabled(True),
                    self._wh_disable_btn.setText("Wyłącz"),
                    show_error("Windows Hello", "Weryfikacja nieudana lub anulowana.", parent=self),
                ))
                return
            wh.delete_credential(self.user.username)
            wh.invalidate_cache()
            QTimer.singleShot(0, lambda: (
                show_success("Windows Hello", "Windows Hello zostało wyłączone.", parent=self),
                self._wh_update_ui("Available", False),
            ))

        threading.Thread(target=_do, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════
    # LOGIKA — ZMIANA HASŁA
    # ══════════════════════════════════════════════════════════════════

    def _show_reset_password(self) -> None:
        dialog = self._make_dialog("Zmiana hasła masterowego", 420, 420)
        vl = QVBoxLayout(dialog)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(8)

        title = QLabel("Zmiana hasła masterowego")
        title.setStyleSheet("font-size: 17px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(title)

        sep = AnimatedGradientWidget(
            accent=self._prefs.get_accent(), base="#1e1e1e", direction="h", anim_mode="slide"
        )
        sep.setFixedHeight(2)
        sep.start_animation()
        vl.addWidget(sep)

        fields = {}
        for key, lbl, ph, secret in [
            ("old",  "Aktualne hasło masterowe", "Wpisz aktualne hasło...", True),
            ("new",  "Nowe hasło masterowe",      "Min. 8 znaków...",       True),
            ("new2", "Powtórz nowe hasło",         "Powtórz nowe hasło...", True),
            ("totp", "Kod 2FA",                   "000000",                 False),
        ]:
            vl.addWidget(QLabel(lbl))
            e = QLineEdit()
            e.setPlaceholderText(ph)
            e.setFixedHeight(38)
            if secret:
                e.setEchoMode(QLineEdit.EchoMode.Password)
            vl.addWidget(e)
            fields[key] = e

        fields["old"].setFocus()

        btn_row = QWidget()
        brl = QHBoxLayout(btn_row)
        brl.setContentsMargins(0, 4, 0, 0)
        cancel = QPushButton("Anuluj")
        cancel.setFixedHeight(38)
        cancel.setStyleSheet("background: transparent; border: 1px solid #555; color: #aaa; border-radius: 8px;")
        cancel.clicked.connect(dialog.reject)
        brl.addWidget(cancel)
        ok_btn = QPushButton("Zmień hasło")
        ok_btn.setFixedHeight(38)
        ok_btn.setStyleSheet(
            "background: #1f6aa5; color: white; border-radius: 8px; font-weight: bold;"
        )
        ok_btn.clicked.connect(lambda: self._on_reset_password(
            dialog, fields["old"].text(), fields["new"].text(),
            fields["new2"].text(), fields["totp"].text().strip()
        ))
        brl.addWidget(ok_btn)
        vl.addWidget(btn_row)

        dialog.exec()

    def _on_reset_password(self, dialog: QDialog, old_pwd: str, new_pwd: str,
                           new_pwd2: str, totp_code: str) -> None:
        if not all([old_pwd, new_pwd, new_pwd2, totp_code]):
            show_error("Błąd", "Wypełnij wszystkie pola!", parent=dialog)
            return
        if len(new_pwd) < 8:
            show_error("Błąd", "Nowe hasło musi mieć co najmniej 8 znaków!", parent=dialog)
            return
        if new_pwd != new_pwd2:
            show_error("Błąd", "Nowe hasła nie są identyczne!", parent=dialog)
            return
        if not verify_master_password(old_pwd, self.user.master_password_hash):
            show_error("Błąd", "Aktualne hasło jest nieprawidłowe!", parent=dialog)
            return
        if not TOTPManager(secret=self.user.totp_secret).verify(totp_code):
            show_error("Błąd 2FA", "Nieprawidłowy kod 2FA!", parent=dialog)
            return
        try:
            from database.models import Password, PasswordHistory
            new_salt   = generate_salt(32)
            new_crypto = CryptoManager(new_pwd, new_salt, kdf_version=KDF_ARGON2ID)

            # Re-szyfruj wszystkie hasła (aktywne + kosz)
            all_passwords = (self.db.session.query(Password)
                             .filter_by(user_id=self.user.id).all())
            for entry in all_passwords:
                try:
                    pt = self.crypto.decrypt(entry.encrypted_password)
                    entry.encrypted_password = new_crypto.encrypt(pt)
                except Exception:
                    pass  # uszkodzony wpis — pomiń

            # Re-szyfruj historię haseł
            history_entries = (
                self.db.session.query(PasswordHistory)
                .join(Password)
                .filter(Password.user_id == self.user.id)
                .all()
            )
            for h in history_entries:
                try:
                    pt = self.crypto.decrypt(h.encrypted_password)
                    h.encrypted_password = new_crypto.encrypt(pt)
                except Exception:
                    pass

            self.user.master_password_hash = hash_master_password(new_pwd, version=KDF_ARGON2ID)
            self.user.salt       = new_salt
            self.user.kdf_version = KDF_ARGON2ID
            self.db.session.commit()
            self.crypto = new_crypto
            show_success("Sukces", "Hasło masterowe zostało zmienione.", parent=dialog)
            dialog.accept()
        except Exception as e:
            self.db.session.rollback()
            show_error("Błąd", f"Wystąpił błąd:\n{e}", parent=dialog)

    # ══════════════════════════════════════════════════════════════════
    # LOGIKA — RESET 2FA
    # ══════════════════════════════════════════════════════════════════

    def _show_reset_2fa(self) -> None:
        dialog = self._make_dialog("Reset 2FA", 420, 540)
        vl = QVBoxLayout(dialog)
        vl.setContentsMargins(0, 0, 0, 0)

        stack = QStackedWidget()
        vl.addWidget(stack)

        # ── Krok 1: weryfikacja hasła ──────────────────────────────────
        step1 = QWidget()
        s1l = QVBoxLayout(step1)
        s1l.setContentsMargins(20, 20, 20, 20)
        s1l.setSpacing(8)

        t1 = QLabel("Reset 2FA — Krok 1/2")
        t1.setStyleSheet("font-size: 17px; font-weight: bold;")
        t1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s1l.addWidget(t1)

        sep1 = AnimatedGradientWidget(
            accent=self._prefs.get_accent(), base="#1e1e1e", direction="h", anim_mode="slide"
        )
        sep1.setFixedHeight(2)
        sep1.start_animation()
        s1l.addWidget(sep1)

        info1 = QLabel("Potwierdź tożsamość hasłem masterowym,\naby wygenerować nowy kod QR.")
        info1.setStyleSheet("color: #888; font-size: 12px;")
        info1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s1l.addWidget(info1)

        s1l.addWidget(QLabel("Hasło masterowe"))
        entry_pwd = QLineEdit()
        entry_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        entry_pwd.setPlaceholderText("Wpisz hasło...")
        entry_pwd.setFixedHeight(38)
        s1l.addWidget(entry_pwd)

        err1 = QLabel("")
        err1.setStyleSheet("color: #e05252; font-size: 11px;")
        s1l.addWidget(err1)
        s1l.addStretch()

        r1 = QWidget()
        r1l = QHBoxLayout(r1)
        r1l.setContentsMargins(0, 0, 0, 0)
        c1 = QPushButton("Anuluj")
        c1.setFixedHeight(38)
        c1.setStyleSheet("background: transparent; border: 1px solid #555; color: #aaa; border-radius: 8px;")
        c1.clicked.connect(dialog.reject)
        r1l.addWidget(c1)
        n1 = QPushButton("Dalej →")
        n1.setFixedHeight(38)
        n1.setStyleSheet("background: #2d6a4f; color: white; border-radius: 8px; font-weight: bold;")
        r1l.addWidget(n1)
        s1l.addWidget(r1)

        stack.addWidget(step1)

        # ── Krok 2: QR + weryfikacja ───────────────────────────────────
        step2 = QWidget()
        s2l = QVBoxLayout(step2)
        s2l.setContentsMargins(20, 20, 20, 20)
        s2l.setSpacing(8)

        t2 = QLabel("Reset 2FA — Krok 2/2")
        t2.setStyleSheet("font-size: 17px; font-weight: bold;")
        t2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s2l.addWidget(t2)

        sep2 = AnimatedGradientWidget(
            accent=self._prefs.get_accent(), base="#1e1e1e", direction="h", anim_mode="slide"
        )
        sep2.setFixedHeight(2)
        sep2.start_animation()
        s2l.addWidget(sep2)

        info2 = QLabel("Zeskanuj nowy kod QR w aplikacji\nuwierzytelniającej i wpisz kod.")
        info2.setStyleSheet("color: #888; font-size: 12px;")
        info2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s2l.addWidget(info2)

        qr_lbl = QLabel()
        qr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s2l.addWidget(qr_lbl)

        s2l.addWidget(QLabel("Po zeskanowaniu wpisz kod:"))
        entry_code = QLineEdit()
        entry_code.setPlaceholderText("000000")
        entry_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        entry_code.setFixedHeight(46)
        entry_code.setStyleSheet("font-size: 22px; letter-spacing: 4px;")
        s2l.addWidget(entry_code)

        err2 = QLabel("")
        err2.setStyleSheet("color: #e05252; font-size: 11px;")
        s2l.addWidget(err2)
        s2l.addStretch()

        r2 = QWidget()
        r2l = QHBoxLayout(r2)
        r2l.setContentsMargins(0, 0, 0, 0)
        b2 = QPushButton("← Wróć")
        b2.setFixedHeight(38)
        b2.setStyleSheet("background: transparent; border: 1px solid #555; color: #aaa; border-radius: 8px;")
        b2.clicked.connect(lambda: stack.setCurrentIndex(0))
        r2l.addWidget(b2)
        sv = QPushButton("Zapisz nowy QR")
        sv.setFixedHeight(38)
        sv.setStyleSheet("background: #2d6a4f; color: white; border-radius: 8px; font-weight: bold;")
        r2l.addWidget(sv)
        s2l.addWidget(r2)

        stack.addWidget(step2)

        # ── Akcje ──────────────────────────────────────────────────────
        _new_totp_holder: list = []

        def go_step2():
            if not verify_master_password(entry_pwd.text(), self.user.master_password_hash):
                err1.setText("Nieprawidłowe hasło masterowe!")
                return
            new_totp = TOTPManager()
            _new_totp_holder.clear()
            _new_totp_holder.append(new_totp)
            qr_img = new_totp.get_qr_image(self.user.username).resize((180, 180), Image.NEAREST)
            pix = _pil_to_pixmap(qr_img)
            qr_lbl.setPixmap(pix)
            stack.setCurrentIndex(1)
            QTimer.singleShot(200, entry_code.setFocus)

        def save_qr():
            if not _new_totp_holder:
                return
            new_totp = _new_totp_holder[0]
            if not new_totp.verify(entry_code.text().strip()):
                err2.setText("Nieprawidłowy kod!")
                entry_code.clear()
                return
            self.user.totp_secret = new_totp.secret
            self.db.session.commit()
            show_success("2FA zaktualizowane",
                         "Nowy kod QR zapisany.\nOd teraz używaj nowego kodu.", parent=dialog)
            dialog.accept()

        n1.clicked.connect(go_step2)
        entry_pwd.returnPressed.connect(go_step2)
        sv.clicked.connect(save_qr)
        entry_code.returnPressed.connect(save_qr)

        dialog.exec()

    # ══════════════════════════════════════════════════════════════════
    # LOGIKA — USUNIĘCIE KONTA
    # ══════════════════════════════════════════════════════════════════

    def _show_delete_account(self) -> None:
        dialog = self._make_dialog("Usuń konto", 420, 340)
        vl = QVBoxLayout(dialog)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(8)

        title = QLabel("Usuń konto")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #e05252;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(title)

        sep = AnimatedGradientWidget(
            accent="#e05252", base="#1e1e1e", direction="h", anim_mode="slide"
        )
        sep.setFixedHeight(2)
        sep.start_animation()
        vl.addWidget(sep)

        warn = QLabel("Ta operacja jest nieodwracalna!\n"
                      "Wszystkie zapisane hasła zostaną trwale usunięte.")
        warn.setStyleSheet("color: #888; font-size: 12px;")
        warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(warn)

        vl.addWidget(QLabel("Hasło masterowe"))
        entry_pwd = QLineEdit()
        entry_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        entry_pwd.setPlaceholderText("Wpisz hasło...")
        entry_pwd.setFixedHeight(38)
        vl.addWidget(entry_pwd)

        vl.addWidget(QLabel("Kod 2FA"))
        entry_totp = QLineEdit()
        entry_totp.setPlaceholderText("000000")
        entry_totp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        entry_totp.setFixedHeight(42)
        entry_totp.setStyleSheet("font-size: 18px; letter-spacing: 4px;")
        vl.addWidget(entry_totp)

        vl.addStretch()

        btn_row = QWidget()
        brl = QHBoxLayout(btn_row)
        brl.setContentsMargins(0, 0, 0, 0)
        cancel = QPushButton("Anuluj")
        cancel.setFixedHeight(38)
        cancel.setStyleSheet("background: transparent; border: 1px solid #555; color: #aaa; border-radius: 8px;")
        cancel.clicked.connect(dialog.reject)
        brl.addWidget(cancel)
        del_btn = QPushButton("Usuń konto")
        del_btn.setFixedHeight(38)
        del_btn.setStyleSheet(
            "background: #e05252; color: white; border-radius: 8px; font-weight: bold;"
        )
        del_btn.clicked.connect(lambda: self._on_delete_account(
            dialog, entry_pwd.text(), entry_totp.text().strip()
        ))
        brl.addWidget(del_btn)
        vl.addWidget(btn_row)

        dialog.exec()

    def _on_delete_account(self, dialog: QDialog, pwd: str, totp: str) -> None:
        if not verify_master_password(pwd, self.user.master_password_hash):
            show_error("Błąd", "Nieprawidłowe hasło masterowe!", parent=dialog)
            return
        if not TOTPManager(secret=self.user.totp_secret).verify(totp):
            show_error("Błąd 2FA", "Nieprawidłowy kod 2FA!", parent=dialog)
            return
        try:
            self.db.delete_user(self.user)
            dialog.accept()
            if self.on_logout:
                self.on_logout()
        except Exception as e:
            show_error("Błąd", f"Nie udało się usunąć konta:\n{e}", parent=dialog)

    # ── Dialog helper ─────────────────────────────────────────────────

    def _make_dialog(self, title: str, w: int, h: int) -> QDialog:
        from PyQt6.QtWidgets import QDialog
        d = QDialog(self)
        d.setWindowTitle(title)
        d.setFixedSize(w, h)
        d.setStyleSheet("""
            QDialog {
                background: #1e1e1e; color: #f0f0f0;
            }
            QLabel { color: #f0f0f0; font-size: 13px; background: transparent; border: none; }
            QLineEdit {
                background: #2a2a2a; color: #f0f0f0;
                border: 1px solid #444; border-radius: 8px; padding: 4px 10px;
                font-size: 13px;
            }
            QLineEdit:focus { border-color: #4F8EF7; }
        """)
        return d
