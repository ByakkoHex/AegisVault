"""
dialogs.py — Stylizowane dialogi dla AegisVault (PyQt6)
=======================================================
Zamiennik gui/dialogs.py — to samo publiczne API:
    show_error, show_info, show_success, show_warning, ask_yes_no

Używa QDialog z animacją fade-in i kolorowym paskiem po lewej stronie.
W pełni stylowany przez QSS z gui_qt/style.py.
"""

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QSizePolicy,
    QGraphicsOpacityEffect,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QParallelAnimationGroup,
)
from PyQt6.QtGui import QColor, QFont, QKeyEvent

from utils.prefs_manager import PrefsManager


_ICONS = {
    "error":    "✖",
    "info":     "ℹ",
    "warning":  "⚠",
    "question": "?",
    "success":  "✔",
}

_ICON_COLORS = {
    "error":    "#e05252",
    "info":     "#4F8EF7",
    "warning":  "#f0a500",
    "question": "#4F8EF7",
    "success":  "#4caf50",
}


def _accent() -> str:
    return PrefsManager().get_accent()


class _BaseDialog(QDialog):
    """Bazowe okno dialogowe z animacją fade-in i kolorowym paskiem."""

    def __init__(self, parent: QWidget | None, title: str, message: str,
                 kind: str = "info"):
        super().__init__(parent)
        self.result_value: bool = False

        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedWidth(420)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        # Bez ramki systemowej — własny styl
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._build_ui(title, message, kind)
        self._center_on_parent(parent)

        # Fade-in
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)
        self._anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim.setDuration(120)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        QTimer.singleShot(20, self._anim.start)

    def _build_ui(self, title: str, message: str, kind: str):
        icon_char  = _ICONS.get(kind, "ℹ")
        icon_color = _ICON_COLORS.get(kind, _accent())

        prefs = PrefsManager()
        dark  = (prefs.get("appearance_mode") or "dark").lower() != "light"
        bg    = "#1e1e1e" if dark else "#ffffff"
        text  = "#f0f0f0" if dark else "#1a1a1a"
        muted = "#888888" if dark else "#666666"

        # Outer container z border-radius i cieniem
        outer = QFrame(self)
        outer.setObjectName("dialogOuter")
        outer.setStyleSheet(f"""
            #dialogOuter {{
                background-color: {bg};
                border-radius: 12px;
                border: 1px solid {"#2e2e2e" if dark else "#d0d0d0"};
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(outer)

        row_layout = QHBoxLayout(outer)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        # Kolorowy pasek po lewej
        bar = QFrame(outer)
        bar.setFixedWidth(4)
        bar.setStyleSheet(f"background-color: {icon_color}; border-radius: 4px 0 0 4px;")
        row_layout.addWidget(bar)

        # Treść
        content = QWidget(outer)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(8)
        row_layout.addWidget(content, stretch=1)

        # Nagłówek: ikona + tytuł
        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel(icon_char)
        icon_lbl.setStyleSheet(f"color: {icon_color}; font-size: 22px; font-weight: bold;")
        icon_lbl.setFixedWidth(32)
        header.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {text}; font-size: 14px; font-weight: 600;")
        header.addWidget(title_lbl, stretch=1)
        content_layout.addLayout(header)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {icon_color}; background-color: {icon_color}; max-height: 2px; border: none;")
        content_layout.addWidget(sep)

        # Treść wiadomości
        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(f"color: {text}; font-size: 13px;")
        content_layout.addWidget(msg_lbl)

        # Przyciski
        btn_layout = self._build_buttons(icon_color, dark)
        content_layout.addLayout(btn_layout)

    def _build_buttons(self, accent_color: str, dark: bool) -> QHBoxLayout:
        """Nadpisz w podklasach."""
        return QHBoxLayout()

    def _center_on_parent(self, parent: QWidget | None):
        self.adjustSize()
        if parent:
            pr = parent.frameGeometry()
            x  = pr.x() + (pr.width()  - self.width())  // 2
            y  = pr.y() + (pr.height() - self.height()) // 2
            self.move(x, y)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.result_value = False
            self.reject()
        else:
            super().keyPressEvent(event)

    def exec_and_get(self) -> bool:
        self.exec()
        return self.result_value


class _InfoDialog(_BaseDialog):

    def _build_buttons(self, accent_color: str, dark: bool) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addStretch()

        btn = QPushButton("OK")
        btn.setFixedWidth(90)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent_color};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 18px;
                font-weight: 500;
            }}
            QPushButton:hover {{ background-color: {_darken(accent_color, 0.15)}; }}
        """)
        btn.clicked.connect(self._ok)
        btn.setDefault(True)
        layout.addWidget(btn)
        return layout

    def _ok(self):
        self.result_value = True
        self.accept()


class _YesNoDialog(_BaseDialog):

    def __init__(self, parent, title, message, kind="question",
                 yes_text="Tak", no_text="Nie", destructive=False):
        self._yes_text    = yes_text
        self._no_text     = no_text
        self._destructive = destructive
        super().__init__(parent, title, message, kind)
        # Enter = Tak
        self._default_btn.setDefault(True)

    def _build_buttons(self, accent_color: str, dark: bool) -> QHBoxLayout:
        btn_bg   = "#2a2a2a" if dark else "#e8e8e8"
        btn_text = "#f0f0f0" if dark else "#1a1a1a"

        yes_color       = "#e05252" if self._destructive else accent_color
        yes_color_hover = "#c43e3e" if self._destructive else _darken(accent_color, 0.15)

        layout = QHBoxLayout()
        layout.addStretch()

        no_btn = QPushButton(self._no_text)
        no_btn.setFixedWidth(80)
        no_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_bg};
                color: {btn_text};
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{ background-color: {"#3a3a3a" if dark else "#d8d8d8"}; }}
        """)
        no_btn.clicked.connect(self._no)
        layout.addWidget(no_btn)

        yes_btn = QPushButton(self._yes_text)
        yes_btn.setFixedWidth(80)
        yes_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {yes_color};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 500;
            }}
            QPushButton:hover {{ background-color: {yes_color_hover}; }}
        """)
        yes_btn.clicked.connect(self._yes)
        layout.addWidget(yes_btn)

        self._default_btn = yes_btn
        return layout

    def _yes(self):
        self.result_value = True
        self.accept()

    def _no(self):
        self.result_value = False
        self.reject()


# ──────────────────────────────────────────────────────────────
# Publiczne API — identyczne jak gui/dialogs.py
# ──────────────────────────────────────────────────────────────

def show_error(title: str, message: str, parent=None) -> None:
    _InfoDialog(parent, title, message, kind="error").exec_and_get()


def show_info(title: str, message: str, parent=None) -> None:
    _InfoDialog(parent, title, message, kind="info").exec_and_get()


def show_success(title: str, message: str, parent=None) -> None:
    _InfoDialog(parent, title, message, kind="success").exec_and_get()


def show_warning(title: str, message: str, parent=None) -> None:
    _InfoDialog(parent, title, message, kind="warning").exec_and_get()


def ask_yes_no(title: str, message: str, parent=None,
               yes_text: str = "Tak", no_text: str = "Nie",
               destructive: bool = False) -> bool:
    """Zwraca True jeśli użytkownik kliknął przycisk potwierdzenia."""
    return _YesNoDialog(
        parent, title, message, kind="question",
        yes_text=yes_text, no_text=no_text,
        destructive=destructive,
    ).exec_and_get()


# ── Helper ────────────────────────────────────────────────────

def _darken(hex_color: str, amount: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = max(0, int(r * (1 - amount)))
    g = max(0, int(g * (1 - amount)))
    b = max(0, int(b * (1 - amount)))
    return f"#{r:02x}{g:02x}{b:02x}"
