"""
update_dialog.py — Dialogi aktualizacji AegisVault (PyQt6)
===========================================================
UpdateNotification — QDialog po zalogowaniu ("Hej, jest nowa wersja!")
UpdateDropdown     — QFrame popup otwierany z ikonki w topbarze
"""

import webbrowser

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QFrame, QApplication,
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QFont

from utils.prefs_manager import PrefsManager

_ORANGE      = "#f0a500"
_ORANGE_DARK = "#d4920a"


def _accent() -> str:
    return PrefsManager().get_accent()


def _is_dark() -> bool:
    from gui_qt.style import current_dark
    try:
        return current_dark()
    except Exception:
        return True


# ─────────────────────────────────────────────────────────────────────────────
# 1. Popup po zalogowaniu
# ─────────────────────────────────────────────────────────────────────────────

class UpdateNotification(QDialog):
    """Przyjazna karta 'Hej! Dostępna jest nowa wersja' pokazywana po zalogowaniu."""

    def __init__(self, parent: QWidget, update_info: dict):
        super().__init__(parent)
        self._info = update_info
        self.setWindowTitle("Dostępna aktualizacja")
        self.setFixedSize(460, 400)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self._build()

        # Fade-in przez windowOpacity
        from PyQt6.QtCore import QPropertyAnimation, QEasingCurve
        self.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(150)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.start()

    def _build(self):
        dark = _is_dark()
        bg   = "#1e1e1e" if dark else "#ffffff"
        fg   = "#e8e8e8" if dark else "#1a1a1a"
        sub  = "#888888"
        brd  = "#2e2e2e" if dark else "#d0d0d0"

        self.setStyleSheet(f"""
            QDialog {{
                background: {bg};
                border: 1px solid {brd};
                border-radius: 12px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Nagłówek (pomarańczowy) ──────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(62)
        hdr.setStyleSheet(f"""
            QFrame {{
                background: {_ORANGE};
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }}
        """)
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 0, 20, 0)

        title_lbl = QLabel(f"🎉  Hej! Dostępna jest wersja {self._info.get('version', '?')}")
        title_lbl.setStyleSheet("color: #ffffff; font-size: 15px; font-weight: bold; background: transparent;")
        hdr_lay.addWidget(title_lbl)
        hdr_lay.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: #ffffff;
                border: none;
                font-size: 13px;
                border-radius: 14px;
            }}
            QPushButton:hover {{ background: {_ORANGE_DARK}; }}
        """)
        close_btn.clicked.connect(self.reject)
        hdr_lay.addWidget(close_btn)
        root.addWidget(hdr)

        # ── Treść ────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(24, 14, 24, 14)
        body_lay.setSpacing(8)

        ver_lbl = QLabel(
            f"Aktualna wersja: {self._info.get('current', '?')}   →   "
            f"Nowa: {self._info.get('version', '?')}"
        )
        ver_lbl.setStyleSheet(f"color: {sub}; font-size: 11px;")
        body_lay.addWidget(ver_lbl)

        what_lbl = QLabel("Co nowego:")
        what_lbl.setStyleSheet(f"color: {fg}; font-size: 12px; font-weight: bold; margin-top: 8px;")
        body_lay.addWidget(what_lbl)

        changelog_box = QTextEdit()
        changelog_box.setReadOnly(True)
        changelog_box.setFixedHeight(150)
        changelog_box.setPlainText(self._info.get("changelog", "Brak informacji."))
        cl_bg  = "#252525" if dark else "#f5f5f5"
        cl_brd = "#333333" if dark else "#cccccc"
        changelog_box.setStyleSheet(f"""
            QTextEdit {{
                background: {cl_bg};
                color: {fg};
                border: 1px solid {cl_brd};
                border-radius: 8px;
                padding: 8px;
                font-size: 11px;
            }}
        """)
        body_lay.addWidget(changelog_box)

        body_lay.addStretch()

        # ── Przyciski ──────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        dl_btn = QPushButton("⬇  Pobierz teraz")
        dl_btn.setFixedHeight(40)
        dl_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ORANGE};
                color: #ffffff;
                border: none;
                border-radius: 10px;
                font-size: 13px;
                font-weight: bold;
                padding: 0 16px;
            }}
            QPushButton:hover {{ background: {_ORANGE_DARK}; }}
        """)
        dl_btn.clicked.connect(self._download)
        btn_row.addWidget(dl_btn, 1)

        later_btn = QPushButton("Później")
        later_btn.setFixedHeight(40)
        later_bg  = "#2a2a2a" if dark else "#e4e4e4"
        later_fg  = "#cccccc" if dark else "#333333"
        later_hov = "#383838" if dark else "#d0d0d0"
        later_btn.setStyleSheet(f"""
            QPushButton {{
                background: {later_bg};
                color: {later_fg};
                border: none;
                border-radius: 10px;
                font-size: 13px;
                padding: 0 16px;
            }}
            QPushButton:hover {{ background: {later_hov}; }}
        """)
        later_btn.clicked.connect(self.reject)
        btn_row.addWidget(later_btn)

        body_lay.addLayout(btn_row)
        root.addWidget(body, 1)

    def _download(self):
        url = self._info.get("download_url", "")
        if url:
            webbrowser.open(url)
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Dropdown panel z topbaru
# ─────────────────────────────────────────────────────────────────────────────

class UpdateDropdown(QFrame):
    """Borderless panel otwierany z ikonki w topbarze. Zamknij klikając poza nim."""

    WIDTH = 320

    def __init__(self, parent: QWidget, update_info: dict, anchor_widget: QWidget):
        super().__init__(parent)
        self._info = update_info
        self.setFixedWidth(self.WIDTH)
        # Tool zamiast Popup — Popup na Windows zamyka się natychmiast
        # przez mouse-release z kliknięcia przycisku który go otworzył
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        dark = _is_dark()
        self._bg  = "#1e1e1e" if dark else "#f9f9f9"
        self._brd = "#3a3a3a" if dark else "#d0d0d0"
        self._fg  = "#e8e8e8" if dark else "#1a1a1a"
        self._sub = "#888888"

        self._build()
        self.adjustSize()
        self._position(anchor_widget)
        self.show()
        self.raise_()
        QApplication.instance().installEventFilter(self)

    def _build(self):
        self.setStyleSheet(f"""
            QFrame {{
                background: {self._bg};
                border: 1px solid {self._brd};
                border-radius: 10px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Nagłówek ──────────────────────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(38)
        hdr.setStyleSheet(f"""
            QFrame {{
                background: {_ORANGE};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}
        """)
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(12, 0, 8, 0)

        hdr_lbl = QLabel(f"⬆  Aktualizacja {self._info.get('version', '?')}")
        hdr_lbl.setStyleSheet("color: #ffffff; font-size: 10px; font-weight: bold; background: transparent;")
        hdr_lay.addWidget(hdr_lbl, 1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: #ffffff;
                border: none;
                font-size: 11px;
                border-radius: 11px;
            }}
            QPushButton:hover {{ background: {_ORANGE_DARK}; }}
        """)
        close_btn.clicked.connect(self.close)
        hdr_lay.addWidget(close_btn)
        root.addWidget(hdr)

        # ── Wersje ────────────────────────────────────────────────
        ver_block = QWidget()
        ver_block.setStyleSheet("background: transparent;")
        ver_lay = QVBoxLayout(ver_block)
        ver_lay.setContentsMargins(14, 8, 14, 8)
        ver_lay.setSpacing(2)

        cur_lbl = QLabel(f"Twoja wersja:  {self._info.get('current', '?')}")
        cur_lbl.setStyleSheet(f"color: {self._sub}; font-size: 9px;")
        ver_lay.addWidget(cur_lbl)

        new_lbl = QLabel(f"Nowa wersja:  {self._info.get('version', '?')}")
        new_lbl.setStyleSheet(f"color: {_ORANGE}; font-size: 10px; font-weight: bold;")
        ver_lay.addWidget(new_lbl)
        root.addWidget(ver_block)

        # ── Separator ─────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {self._brd};")
        root.addWidget(sep)

        # ── Changelog ─────────────────────────────────────────────
        cl_block = QWidget()
        cl_block.setStyleSheet("background: transparent;")
        cl_lay = QVBoxLayout(cl_block)
        cl_lay.setContentsMargins(14, 8, 14, 8)
        cl_lay.setSpacing(4)

        wn_lbl = QLabel("Co nowego:")
        wn_lbl.setStyleSheet(f"color: {self._fg}; font-size: 9px; font-weight: bold;")
        cl_lay.addWidget(wn_lbl)

        changelog = self._info.get("changelog", "Brak informacji.")
        if len(changelog) > 320:
            changelog = changelog[:320].rstrip() + "…"

        cl_lbl = QLabel(changelog)
        cl_lbl.setWordWrap(True)
        cl_lbl.setStyleSheet(f"color: {self._sub}; font-size: 9px;")
        cl_lay.addWidget(cl_lbl)
        root.addWidget(cl_block)

        # ── Separator ─────────────────────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {self._brd};")
        root.addWidget(sep2)

        # ── Przyciski ─────────────────────────────────────────────
        btn_block = QWidget()
        btn_block.setStyleSheet("background: transparent;")
        btn_lay = QHBoxLayout(btn_block)
        btn_lay.setContentsMargins(14, 10, 14, 10)
        btn_lay.setSpacing(8)

        dl_btn = QPushButton("⬇  Pobierz")
        dl_btn.setFixedHeight(30)
        dl_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ORANGE};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 10px;
                font-weight: bold;
                padding: 0 14px;
            }}
            QPushButton:hover {{ background: {_ORANGE_DARK}; }}
        """)
        dl_btn.clicked.connect(self._download)
        btn_lay.addWidget(dl_btn)

        later_bg = "#3a3a3a" if _is_dark() else "#e4e4e4"
        later_fg = "#cccccc" if _is_dark() else "#333333"
        later_btn = QPushButton("Później")
        later_btn.setFixedHeight(30)
        later_btn.setStyleSheet(f"""
            QPushButton {{
                background: {later_bg};
                color: {later_fg};
                border: none;
                border-radius: 6px;
                font-size: 10px;
                padding: 0 14px;
            }}
            QPushButton:hover {{ background: #484848; }}
        """)
        later_btn.clicked.connect(self.close)
        btn_lay.addWidget(later_btn)
        btn_lay.addStretch()
        root.addWidget(btn_block)

    def _position(self, anchor: QWidget) -> None:
        gpos = anchor.mapToGlobal(QPoint(0, anchor.height() + 4))
        screen = QApplication.primaryScreen().availableGeometry()
        x = min(gpos.x(), screen.right() - self.WIDTH - 8)
        y = gpos.y()
        if y + self.height() > screen.bottom():
            y = anchor.mapToGlobal(QPoint(0, -self.height() - 4)).y()
        self.move(x, y)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.MouseButtonPress:
            try:
                gpos = event.globalPosition().toPoint()
            except AttributeError:
                gpos = event.globalPos()
            if not self.geometry().contains(gpos):
                self.close()
        return False

    def closeEvent(self, event):
        try:
            QApplication.instance().removeEventFilter(self)
        except Exception:
            pass
        super().closeEvent(event)

    def _download(self) -> None:
        url = self._info.get("download_url", "")
        if url:
            webbrowser.open(url)
        self.close()
