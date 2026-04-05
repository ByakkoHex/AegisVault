"""
tray.py — Ikona w zasobniku systemowym (PyQt6 QSystemTrayIcon)
=============================================================
Zamiennik gui/tray.py (pystray). QSystemTrayIcon działa natywnie
na Windows, macOS i Linux bez dodatkowych zależności.

Użycie:
    tray = TrayIcon(parent_window)
    tray.start()
    # ...
    tray.stop()
"""

import os
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter, QBrush
from PyQt6.QtCore import Qt, QSize


_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")


def _make_tray_icon() -> QIcon:
    """Wczytuje icon.png lub generuje ikonę tarczy awaryjną."""
    icon_path = os.path.join(_ASSETS_DIR, "icon.png")
    if os.path.exists(icon_path):
        return QIcon(icon_path)

    # Fallback — rysowana ikona tarczy
    size = 32
    pix  = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Tło — ciemne koło
    painter.setBrush(QBrush(QColor("#1e1e1e")))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(1, 1, size - 2, size - 2)

    # Wewnętrzne koło — kolor akcentu
    painter.setBrush(QBrush(QColor("#4F8EF7")))
    pad = size // 5
    painter.drawEllipse(pad, pad, size - pad * 2, size - pad * 2)

    painter.end()
    return QIcon(pix)


class TrayIcon:
    """
    Ikona w zasobniku systemowym z menu kontekstowym.

    Callbacks:
        on_show   — wywołany gdy użytkownik kliknie "Pokaż"
        on_quit   — wywołany gdy użytkownik kliknie "Zakończ"
    """

    def __init__(self, parent, on_show=None, on_quit=None):
        self._parent  = parent
        self._on_show = on_show
        self._on_quit = on_quit
        self._tray: QSystemTrayIcon | None = None

    def start(self):
        """Tworzy i pokazuje ikonę w zasobniku."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self._tray = QSystemTrayIcon(self._parent)
        self._tray.setIcon(_make_tray_icon())
        self._tray.setToolTip("AegisVault")

        menu = QMenu()

        show_action = menu.addAction("🔓  Pokaż AegisVault")
        show_action.triggered.connect(self._show)

        menu.addSeparator()

        quit_action = menu.addAction("🚪  Zakończ")
        quit_action.triggered.connect(self._quit)

        self._tray.setContextMenu(menu)

        # Podwójne kliknięcie = pokaż okno
        self._tray.activated.connect(self._on_activated)

        self._tray.show()

    def stop(self):
        """Ukrywa i usuwa ikonę z zasobnika."""
        if self._tray:
            self._tray.hide()
            self._tray.deleteLater()
            self._tray = None

    def show_message(self, title: str, message: str, kind: str = "info",
                     duration_ms: int = 3000):
        """Systemowe powiadomienie balonowe (opcjonalne)."""
        if not self._tray:
            return
        icon_map = {
            "info":    QSystemTrayIcon.MessageIcon.Information,
            "warning": QSystemTrayIcon.MessageIcon.Warning,
            "error":   QSystemTrayIcon.MessageIcon.Critical,
            "success": QSystemTrayIcon.MessageIcon.Information,
        }
        self._tray.showMessage(
            title, message,
            icon_map.get(kind, QSystemTrayIcon.MessageIcon.Information),
            duration_ms,
        )

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show()

    def _show(self):
        if self._on_show:
            self._on_show()
        elif self._parent:
            self._parent.showNormal()
            self._parent.activateWindow()
            self._parent.raise_()

    def _quit(self):
        if self._on_quit:
            self._on_quit()
        else:
            QApplication.quit()
