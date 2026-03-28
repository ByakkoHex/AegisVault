"""
font_manager.py - Manager fontów aplikacji AegisVault (cross-platform)
=======================================================================
Pobiera font Roboto i rejestruje go odpowiednio dla systemu:
  Windows : GDI32  AddFontResourceExW
  macOS   : customtkinter FontManager (CoreText)
  Linux   : customtkinter FontManager (Fontconfig / Pango)

Fallback: Segoe UI (Win) / Helvetica Neue (Mac) / DejaVu Sans (Linux)
"""

import os
import sys
import tkinter.font as tkfont
from utils.paths import get_assets_dir

FONTS_DIR = os.path.join(get_assets_dir(), "fonts")

ROBOTO_FILES = {
    "Roboto-Regular.ttf": "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Regular.ttf",
    "Roboto-Bold.ttf":    "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf",
    "Roboto-Light.ttf":   "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Light.ttf",
}

# Fonty fallback priorytetowane według systemu
_FALLBACK_FONTS = {
    "win32":  ["Segoe UI", "Arial"],
    "darwin": ["Helvetica Neue", "Helvetica", "Arial"],
    "linux":  ["DejaVu Sans", "Liberation Sans", "Ubuntu", "Arial"],
}


def _fallback_font() -> str:
    platform = sys.platform if sys.platform in _FALLBACK_FONTS else "linux"
    available = set(tkfont.families())
    for font in _FALLBACK_FONTS[platform]:
        if font in available:
            print(f"[FontManager] Fallback: {font}")
            return font
    return "TkDefaultFont"


def download_roboto() -> bool:
    """
    Pobiera pliki Roboto jeśli jeszcze nie ma lokalnie.
    Zwraca True gdy wszystkie pliki są dostępne.
    """
    try:
        import requests
    except ImportError:
        print("[FontManager] Brak 'requests' — pomijam pobieranie fontu.")
        return False

    os.makedirs(FONTS_DIR, exist_ok=True)

    for filename, url in ROBOTO_FILES.items():
        filepath = os.path.join(FONTS_DIR, filename)
        if not os.path.exists(filepath):
            print(f"[FontManager] Pobieranie {filename}...")
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                with open(filepath, "wb") as f:
                    f.write(response.content)
                print(f"[FontManager] OK  {filename}")
            except Exception as e:
                print(f"[FontManager] Błąd {filename}: {e}")
                return False

    return True


def _load_windows() -> str:
    """Rejestruje font w GDI32 (Windows)."""
    try:
        import ctypes
        gdi32 = ctypes.WinDLL("gdi32")
        loaded = 0
        for filename in ROBOTO_FILES:
            path = os.path.join(FONTS_DIR, filename)
            if os.path.exists(path):
                if gdi32.AddFontResourceExW(path, 0x10, 0):
                    loaded += 1
        if loaded > 0:
            print(f"[FontManager] Załadowano {loaded} plików Roboto (GDI32).")
            return "Roboto"
    except Exception as e:
        print(f"[FontManager] GDI32 błąd: {e}")
    return _fallback_font()


def _load_unix() -> str:
    """
    Rejestruje font przez customtkinter FontManager (działa na macOS i Linux).
    customtkinter używa wewnętrznie tkinter.font + platform-specific loading.
    """
    try:
        import customtkinter as ctk  # noqa: F401
        from customtkinter.windows.widgets.font import FontManager as CTkFontManager

        loaded = 0
        for filename in ROBOTO_FILES:
            path = os.path.join(FONTS_DIR, filename)
            if os.path.exists(path):
                CTkFontManager.load_font(path)
                loaded += 1

        if loaded > 0:
            print(f"[FontManager] Załadowano {loaded} plików Roboto (CTkFontManager).")
            return "Roboto"
    except Exception as e:
        print(f"[FontManager] CTkFontManager błąd: {e}")
    return _fallback_font()


def load_fonts() -> str:
    """
    Ładuje font Roboto do aplikacji.
    Wybiera odpowiednią metodę dla bieżącego systemu.
    Zwraca nazwę fontu do użycia w CTkFont.
    """
    if sys.platform == "win32":
        return _load_windows()
    else:
        return _load_unix()


def setup_fonts() -> str:
    """
    Główna funkcja — pobiera i ładuje Roboto.
    Wywołaj raz przy starcie aplikacji.
    """
    if download_roboto():
        return load_fonts()
    return _fallback_font()
