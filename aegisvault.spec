# -*- mode: python ; coding: utf-8 -*-
# aegisvault.spec — PyInstaller build config (cross-platform)
#
# Windows  → dist/AegisVault/        (katalog, pakowany przez Inno Setup)
# macOS    → dist/AegisVault.app     (bundle, pakowany przez build_dmg.sh)
# Linux    → dist/aegisvault         (single-file exe, pakowany przez build_deb.sh)

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

# winrt — Windows only
winrt_hidden = []
if sys.platform == "win32":
    import importlib.util as _ilu
    if _ilu.find_spec("winrt"):
        winrt_hidden = collect_submodules("winrt")

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
    # Stdlib
    "email.mime.text",
    "email.mime.multipart",
    "ctypes",
] + winrt_hidden + kr_hidden + pt_hidden

# Windows-only imports
if sys.platform == "win32":
    hidden += ["winrt", "ctypes.wintypes"]

# ── Ikona ─────────────────────────────────────────────────────────────────────
if sys.platform == "darwin":
    icon_path = "assets/icon.icns" if os.path.exists("assets/icon.icns") else None
elif sys.platform == "win32":
    icon_path = "assets/icon.ico" if os.path.exists("assets/icon.ico") else None
else:
    icon_path = None

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
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Linux — single-file exe ───────────────────────────────────────────────────
if sys.platform == "linux":
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        name="aegisvault",
        debug=False,
        bootloader_ignore_signals=False,
        strip=True,
        upx=True,
        console=False,
        icon=icon_path,
    )

# ── macOS — .app bundle ───────────────────────────────────────────────────────
elif sys.platform == "darwin":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="AegisVault",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        icon=icon_path,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        name="AegisVault",
    )
    app = BUNDLE(
        coll,
        name="AegisVault.app",
        icon=icon_path,
        bundle_identifier="pl.aegisvault.AegisVault",
        info_plist={
            "CFBundleShortVersionString": "1.2.0",
            "CFBundleVersion": "1.2.0",
            "NSHighResolutionCapable": True,
        },
    )

# ── Windows — katalog (pakowany Inno Setup) ───────────────────────────────────
else:
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
        console=False,
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
