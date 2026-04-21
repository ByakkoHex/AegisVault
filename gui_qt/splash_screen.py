"""
splash_screen.py — Ekran startowy AegisVault (JetBrains-style)
===============================================================
Bezramkowe okno wyśrodkowane na ekranie.
Tło: HexBackground z animacją "breath".
Zawiera: logo, nazwa, wersja, pasek postępu, status, copyright.
"""

import os
import sys
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore    import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui     import QPixmap, QPainter, QColor, QFont, QPen

_ASSETS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "assets"))

from gui_qt.hex_background import HexBackground
from utils.prefs_manager   import PrefsManager


_ACCENT_FB = "#4F8EF7"
_VERSION_COLOR = "#666"
_STATUS_COLOR  = "#555"
_COPYRIGHT_COLOR = "#444"


class SplashScreen(QWidget):
    """
    Ekran startowy — wyświetlany podczas ładowania aplikacji.

    Użycie:
        splash = SplashScreen("1.3.0")
        splash.show()
        splash.set_progress(40, "Ładowanie bazy...")
        ...
        splash.finish(callback)   # fade-out + callback po zakończeniu
    """

    def __init__(self, version: str = ""):
        super().__init__(None)
        self._version = version
        self._prefs   = PrefsManager()
        self._accent  = self._prefs.get_accent() or _ACCENT_FB
        self._opacity_val = 1.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(600, 340)
        self._center_on_screen()
        self._build_ui()

    # ── Publiczne API ─────────────────────────────────────────────────

    def set_progress(self, percent: int, status: str = "") -> None:
        """Aktualizuje pasek postępu i tekst statusu (thread-safe przez QTimer)."""
        QTimer.singleShot(0, lambda: self._apply_progress(percent, status))

    def finish(self, callback=None) -> None:
        """Fade-out, potem wywołuje callback."""
        anim = QPropertyAnimation(self, b"opacity", self)
        anim.setDuration(350)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self._on_finished(callback))
        anim.start()
        self._anim = anim   # keep ref

    # ── Qt property dla animacji opacity ──────────────────────────────

    def getOpacity(self) -> float:
        return self._opacity_val

    def setOpacity(self, val: float) -> None:
        self._opacity_val = val
        self.setWindowOpacity(val)

    opacity = pyqtProperty(float, fget=getOpacity, fset=setOpacity)

    # ── UI ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Tło hexagonalne
        self._hex_bg = HexBackground(
            self,
            hex_size=28,
            glow_max=12,
            glow_interval_ms=200,
            glow_mode="breath",
        )
        self._hex_bg.setGeometry(0, 0, self.width(), self.height())
        self._hex_bg.lower()
        self._hex_bg.start_animation()

        # Overlay z treścią
        overlay = QWidget(self)
        overlay.setGeometry(0, 0, self.width(), self.height())
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        overlay.setStyleSheet("background: transparent;")

        vl = QVBoxLayout(overlay)
        vl.setContentsMargins(40, 32, 40, 24)
        vl.setSpacing(0)

        # ── Logo + tytuł ──────────────────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(18)
        top_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        icon_lbl = QLabel()
        _icon_path = os.path.join(_ASSETS_DIR, "icon.png")
        px = QPixmap(_icon_path)
        if not px.isNull():
            icon_lbl.setPixmap(px.scaled(
                64, 64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            icon_lbl.setText("🛡")
            icon_lbl.setStyleSheet("font-size: 52px;")
        icon_lbl.setFixedSize(68, 68)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        title_lbl = QLabel("AegisVault")
        title_lbl.setStyleSheet(
            f"font-size: 34px; font-weight: 700; color: #f0f0f0;"
            f"letter-spacing: 1px; background: transparent;"
        )
        title_col.addWidget(title_lbl)

        ver_lbl = QLabel(f"v{self._version}")
        ver_lbl.setStyleSheet(
            f"font-size: 13px; color: {_VERSION_COLOR}; background: transparent;"
        )
        title_col.addWidget(ver_lbl)
        top_row.addLayout(title_col)
        top_row.addStretch()

        vl.addLayout(top_row)
        vl.addStretch()

        # ── Tagline ───────────────────────────────────────────────────
        tagline = QLabel("Bezpieczny menedżer haseł")
        tagline.setStyleSheet(
            "font-size: 12px; color: #4a4a4a; background: transparent; letter-spacing: 1px;"
        )
        tagline.setAlignment(Qt.AlignmentFlag.AlignLeft)
        vl.addWidget(tagline)
        vl.addSpacing(14)

        # ── Pasek postępu ─────────────────────────────────────────────
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(3)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: #2a2a2a;
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {self._accent};
                border-radius: 2px;
            }}
        """)
        vl.addWidget(self._progress_bar)
        vl.addSpacing(6)

        # ── Status + copyright ────────────────────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(0)

        self._status_lbl = QLabel("Uruchamianie...")
        self._status_lbl.setStyleSheet(
            f"font-size: 11px; color: {_STATUS_COLOR}; background: transparent;"
        )
        bottom_row.addWidget(self._status_lbl)
        bottom_row.addStretch()

        copy_lbl = QLabel(f"© 2024–2026 AegisVault")
        copy_lbl.setStyleSheet(
            f"font-size: 10px; color: {_COPYRIGHT_COLOR}; background: transparent;"
        )
        bottom_row.addWidget(copy_lbl)
        vl.addLayout(bottom_row)

    # ── Helpers ───────────────────────────────────────────────────────

    def _apply_progress(self, percent: int, status: str) -> None:
        self._progress_bar.setValue(max(0, min(100, percent)))
        if status:
            self._status_lbl.setText(status)

    def _center_on_screen(self) -> None:
        try:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().geometry()
            self.move(
                screen.x() + (screen.width()  - self.width())  // 2,
                screen.y() + (screen.height() - self.height()) // 2,
            )
        except Exception:
            pass

    def _on_finished(self, callback) -> None:
        self._hex_bg.stop_animation()
        self.close()
        if callback:
            callback()
