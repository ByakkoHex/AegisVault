"""
changelog_dialog.py — Dialog "Co nowego" po aktualizacji AegisVault (PyQt6)
============================================================================
Pokazywany raz po uruchomieniu aplikacji w nowej wersji.
"""

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QFrame,
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve

from utils.prefs_manager import PrefsManager


def _accent() -> str:
    return PrefsManager().get_accent()


def _accent_hover() -> str:
    return PrefsManager().get_accent_hover()


def _is_dark() -> bool:
    from gui_qt.style import current_dark
    try:
        return current_dark()
    except Exception:
        return True


class ChangelogDialog(QDialog):
    """Dialog 'Co nowego w wersji X.Y.Z' pokazywany po pierwszym uruchomieniu po aktualizacji."""

    def __init__(self, parent: QWidget, version: str, changelog: str, accent: str = ""):
        super().__init__(parent)
        self._version   = version
        self._changelog = changelog
        self._accent    = accent or _accent()

        self.setWindowTitle("")
        self.setFixedSize(500, 480)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self._build()

        # Fade-in przez windowOpacity (nie QGraphicsOpacityEffect)
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
        acc  = self._accent
        acc_h = _accent_hover()

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

        # ── Nagłówek (accent color) ──────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(70)
        hdr.setStyleSheet(f"""
            QFrame {{
                background: {acc};
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }}
        """)
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 0, 20, 0)

        rocket_lbl = QLabel("🚀  Co nowego?")
        rocket_lbl.setStyleSheet(
            "color: #ffffff; font-size: 20px; font-weight: bold; background: transparent;"
        )
        hdr_lay.addWidget(rocket_lbl, 1)

        ver_hdr_lbl = QLabel(f"v{self._version}")
        ver_hdr_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.7); font-size: 13px; background: transparent;"
        )
        hdr_lay.addWidget(ver_hdr_lbl)
        root.addWidget(hdr)

        # ── Treść ────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(24, 16, 24, 16)
        body_lay.setSpacing(8)

        subtitle = QLabel(f"AegisVault został zaktualizowany do wersji {self._version}.")
        subtitle.setStyleSheet(f"color: {sub}; font-size: 12px;")
        body_lay.addWidget(subtitle)

        changelog_box = QTextEdit()
        changelog_box.setReadOnly(True)
        changelog_box.setPlainText(self._changelog.strip())
        cl_bg  = "#252525" if dark else "#f5f5f5"
        cl_brd = "#333333" if dark else "#cccccc"
        changelog_box.setStyleSheet(f"""
            QTextEdit {{
                background: {cl_bg};
                color: {fg};
                border: 1px solid {cl_brd};
                border-radius: 10px;
                padding: 10px;
                font-size: 12px;
                font-family: Consolas, 'Courier New', monospace;
            }}
        """)
        body_lay.addWidget(changelog_box, 1)

        # ── Przycisk OK ──────────────────────────────────────────
        ok_btn = QPushButton("✓  Super, dzięki!")
        ok_btn.setFixedHeight(42)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: {acc};
                color: #ffffff;
                border: none;
                border-radius: 12px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {acc_h}; }}
        """)
        ok_btn.clicked.connect(self.accept)
        body_lay.addWidget(ok_btn)

        root.addWidget(body, 1)
