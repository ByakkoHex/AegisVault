# -*- mode: python ; coding: utf-8 -*-
# aegisvault.spec — PyInstaller build config (Windows)
#
# Budowanie (z katalogu projektu):
#   pip install pyinstaller
#   pyinstaller aegisvault.spec --noconfirm
#
# Następnie instalator (wymaga Inno Setup 6):
#   iscc /DAppVersion=1.0.0 installer\windows\aegisvault.iss

import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# ── Dane dodatkowe ────────────────────────────────────────────────────────────
added_files = [
    ("assets", "assets"),
]

# customtkinter — znajdź katalog pakietu przez site-packages (bez importu)
import site
_ctk_path = None
for _sp in site.getsitepackages() + [site.getusersitepackages()]:
    _candidate = os.path.join(_sp, "customtkinter")
    if os.path.isdir(_candidate):
        _ctk_path = _candidate
        break
if _ctk_path:
    added_files += [(_ctk_path, "customtkinter")]
else:
    print("WARNING: customtkinter package directory not found in site-packages!")

# Zbierz pliki pozostałych pakietów (ignoruj błędy jeśli nie zainstalowane)
def _safe_collect(pkg):
    try:
        return collect_all(pkg)
    except Exception:
        return [], [], []

kr_datas,  kr_binaries,  kr_hidden  = _safe_collect("keyring")
pt_datas,  pt_binaries,  pt_hidden  = _safe_collect("pystray")
tc_datas,  _,            _          = _safe_collect("tkcalendar")

added_files += kr_datas + pt_datas + tc_datas

# winrt — zbierz submoduły (te pakiety są .pyd, nie zwykłe foldery)
winrt_hidden = collect_submodules("winrt") if __import__("importlib.util").util.find_spec("winrt") else []

# ── Hidden imports ────────────────────────────────────────────────────────────
hidden = [
    # GUI
    "customtkinter",
    "PIL._tkinter_finder",
    "PIL.Image",
    "PIL.ImageTk",
    "tkcalendar",
    # Krypto
    "cryptography",
    "cryptography.hazmat.primitives.kdf.pbkdf2",
    "cryptography.hazmat.primitives.kdf.scrypt",
    "cryptography.hazmat.primitives.ciphers.aead",
    "cryptography.hazmat.backends.openssl",
    "bcrypt",
    "pyotp",
    "qrcode",
    "qrcode.image.pil",
    # Baza danych
    "sqlalchemy",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
    "sqlalchemy.orm",
    "sqlalchemy.pool",
    # Sieć
    "httpx",
    "httpx._transports.default",
    "requests",
    "certifi",
    # Schowek / system
    "pyperclip",
    # Tray
    "pystray",
    # Keyring
    "keyring",
    # WinRT (Windows Hello)
    "winrt",
    # Stdlib których PyInstaller czasem nie zbiera automatycznie
    "email.mime.text",
    "email.mime.multipart",
    "ctypes",
    "ctypes.wintypes",
] + winrt_hidden + kr_hidden + pt_hidden

# ── Ikona — obsłuż brak pliku ─────────────────────────────────────────────────
icon_path = "assets/icon.ico" if os.path.exists("assets/icon.ico") else None

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=kr_binaries + pt_binaries,
    datas=added_files,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter.test",
        "unittest",
        "email.test",
        "test",
        "xmlrpc",
        "ftplib",
        "imaplib",
        "nntplib",
        "poplib",
        "smtplib",
        "telnetlib",
        "antigravity",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Windows build ─────────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AegisVault",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # brak czarnego okna konsoli
    icon=icon_path,
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime140.dll", "python*.dll"],
    name="AegisVault",
)
