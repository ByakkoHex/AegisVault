"""
tray.py - Ikona w zasobniku systemowym (pystray)
=================================================
Wymaga: pip install pystray
"""

import os
import threading
from PIL import Image, ImageDraw

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")


def _make_icon_image(size: int = 64) -> Image.Image:
    """Ładuje icon.png z assets/ lub generuje ikonę awaryjną."""
    icon_path = os.path.join(_ASSETS_DIR, "icon.png")
    if os.path.exists(icon_path):
        try:
            img = Image.open(icon_path).convert("RGBA")
            return img.resize((size, size), Image.LANCZOS)
        except Exception:
            pass

    # Fallback — generowana ikona tarczy
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, size - 2, size - 2], fill="#1e1e1e")
    pad = size // 6
    draw.ellipse([pad, pad, size - pad, size - pad], fill="#4F8EF7")
    cx, cy = size // 2, size // 2
    lw = size // 5
    lh = size // 4
    draw.rectangle([cx - lw, cy - 2, cx + lw, cy + lh], fill="#1e1e1e", outline="#1e1e1e")
    draw.arc([cx - lw + 2, cy - lh - 2, cx + lw - 2, cy + 4],
             start=0, end=180, fill="#ffffff", width=max(2, size // 16))
    return img


class TrayIcon:
    """Zarządza ikoną w zasobniku systemowym."""

    def __init__(self, username: str, on_show, on_lock, on_quit):
        self._icon   = None
        self._thread = None
        self.username = username
        self._on_show = on_show
        self._on_lock = on_lock
        self._on_quit = on_quit

    def start(self):
        """Uruchamia ikonę w tle (osobny wątek)."""
        try:
            import pystray
        except ImportError:
            return  # pystray niedostępne — tray wyłączony

        icon_img = _make_icon_image(64)

        menu = pystray.Menu(
            pystray.MenuItem(f"AegisVault  —  {self.username}",
                             None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Otwórz",        lambda: self._on_show(),  default=True),
            pystray.MenuItem("🔒 Zablokuj",   lambda: self._on_lock()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Wyjdź",         lambda: self._quit_all()),
        )

        self._icon = pystray.Icon(
            name="AegisVault",
            icon=icon_img,
            title=f"AegisVault — {self.username}",
            menu=menu,
        )

        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    def _quit_all(self):
        self.stop()
        self._on_quit()
