"""
changelog_dialog.py — Dialog "Co nowego" po aktualizacji AegisVault (PyQt6)
============================================================================
Pokazywany raz po uruchomieniu aplikacji w nowej wersji.
Wyświetla historię wersji z tytułami i listą zmian.
"""

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame,
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
    """Dialog 'Co nowego' pokazywany po pierwszym uruchomieniu po aktualizacji."""

    def __init__(self, parent: QWidget, version: str, changelog: str, accent: str = ""):
        super().__init__(parent)
        self._version = version
        self._accent  = accent or _accent()

        self.setWindowTitle("")
        self.setFixedSize(520, 560)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self._build()

        # Fade-in przez windowOpacity
        self.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(150)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.start()

    def _build(self):
        dark  = _is_dark()
        bg    = "#1a1a1a" if dark else "#f5f5f5"
        fg    = "#e8e8e8" if dark else "#1a1a1a"
        muted = "#888888" if dark else "#666666"
        brd   = "#2e2e2e" if dark else "#d0d0d0"
        card  = "#242424" if dark else "#ffffff"
        acc   = self._accent
        acc_h = _accent_hover()

        self.setStyleSheet(f"""
            QDialog {{
                background: {bg};
                border: 1px solid {brd};
                border-radius: 14px;
            }}
            QLabel {{ background: transparent; border: none; color: {fg}; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 5px; }}
            QScrollBar::handle:vertical {{
                background: {'#444' if dark else '#ccc'};
                border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Nagłówek ──────────────────────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(76)
        hdr.setStyleSheet(f"""
            QFrame {{
                background: {acc};
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }}
        """)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(24, 0, 24, 0)

        title_lbl = QLabel("🚀  Co nowego w AegisVault?")
        title_lbl.setStyleSheet(
            "color: white; font-size: 18px; font-weight: bold;"
        )
        hl.addWidget(title_lbl, 1)

        ver_lbl = QLabel(f"v{self._version}")
        ver_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.75); font-size: 13px; font-weight: 600;"
        )
        hl.addWidget(ver_lbl)
        root.addWidget(hdr)

        # ── Scroll z kartami wersji ───────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setStyleSheet(f"background: {bg};")
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(20, 16, 20, 8)
        vl.setSpacing(12)

        # Wczytaj historię wersji
        try:
            from version import VERSION_HISTORY
            history = VERSION_HISTORY
        except Exception:
            history = []

        for i, (ver, title, changes) in enumerate(history):
            card_w = QFrame()
            card_w.setStyleSheet(f"""
                QFrame {{
                    background: {card};
                    border-radius: 10px;
                    border: 1px solid {brd};
                }}
            """)
            cl = QVBoxLayout(card_w)
            cl.setContentsMargins(16, 12, 16, 14)
            cl.setSpacing(6)

            # Nagłówek karty: wersja + tytuł
            hdr_row = QWidget()
            hdr_row.setStyleSheet("background: transparent; border: none;")
            hr = QHBoxLayout(hdr_row)
            hr.setContentsMargins(0, 0, 0, 0)
            hr.setSpacing(10)

            ver_badge = QLabel(f"v{ver}")
            badge_bg  = acc if i == 0 else ("#3a3a3a" if dark else "#e0e0e0")
            badge_fg  = "white" if i == 0 else muted
            ver_badge.setStyleSheet(
                f"background: {badge_bg}; color: {badge_fg}; "
                "font-size: 11px; font-weight: bold; "
                "padding: 2px 8px; border-radius: 6px; border: none;"
            )
            ver_badge.setFixedHeight(20)
            hr.addWidget(ver_badge)

            title_l = QLabel(title)
            title_l.setStyleSheet(
                f"color: {fg}; font-size: 13px; font-weight: {'bold' if i == 0 else '600'};"
            )
            hr.addWidget(title_l, 1)
            cl.addWidget(hdr_row)

            # Separator
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color: {brd}; border: none; background: {brd}; max-height: 1px;")
            cl.addWidget(sep)

            # Lista zmian
            for change in changes:
                row = QWidget()
                row.setStyleSheet("background: transparent; border: none;")
                rl = QHBoxLayout(row)
                rl.setContentsMargins(0, 1, 0, 1)
                rl.setSpacing(8)

                dot = QLabel("•")
                dot.setFixedWidth(10)
                dot.setStyleSheet(f"color: {acc if i == 0 else muted}; font-size: 14px;")
                rl.addWidget(dot)

                txt = QLabel(change)
                txt.setWordWrap(True)
                txt.setStyleSheet(f"color: {fg if i == 0 else muted}; font-size: 12px;")
                rl.addWidget(txt, 1)
                cl.addWidget(row)

            vl.addWidget(card_w)

        vl.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # ── Stopka z przyciskiem ──────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet(f"background: {bg}; border-bottom-left-radius: 14px; border-bottom-right-radius: 14px;")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 10, 20, 16)

        ok_btn = QPushButton("✓  Super, dzięki!")
        ok_btn.setFixedHeight(42)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: {acc};
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {acc_h}; }}
        """)
        ok_btn.clicked.connect(self.accept)
        fl.addWidget(ok_btn)
        root.addWidget(footer)
