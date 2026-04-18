# -*- mode: python ; coding: utf-8 -*-
# aegisvault.spec — PyInstaller build config (cross-platform, PyQt6)
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

# Zbierz pliki pakietów (ignoruj błędy jeśli nie zainstalowane)
def _safe_collect(pkg):
    try:
        return collect_all(pkg)
    except Exception:
        return [], [], []

kr_datas, kr_binaries, kr_hidden = _safe_collect("keyring")
qt_datas, qt_binaries, qt_hidden = _safe_collect("PyQt6")

# Filtruj binarne frameworki Qt których nie używamy.
# excludes= w Analysis odfiltrowuje tylko moduły Pythona — nie pliki .framework/.so.
_QT_UNUSED = {
    "QtNfc", "QtBluetooth",
    "QtWebEngine", "QtWebEngineCore", "QtWebEngineWidgets", "QtWebEngineQuick",
    "QtMultimedia", "QtMultimediaWidgets", "QtMultimediaQuick",
    "QtLocation", "QtPositioning", "QtPositioningQuick",
    "QtSensors", "QtSensorsQuick",
    "QtSerialPort", "QtSerialBus",
    "QtCharts", "QtDataVisualization",
    "Qt3DCore", "Qt3DRender", "Qt3DInput", "Qt3DLogic",
    "Qt3DAnimation", "Qt3DExtras", "Qt3DQuick",
    "QtVirtualKeyboard",
    "QtQuick", "QtQuickWidgets", "QtQuickControls2", "QtQuickTemplates2",
    "QtQml", "QtQmlModels", "QtQmlWorkerScript",
    "QtPdf", "QtPdfQuick", "QtPdfWidgets",
    "QtRemoteObjects", "QtScxml", "QtStateMachine",
    "QtNetworkAuth", "QtSql", "QtTest", "QtXml", "QtDBus",
}

def _keep_qt(entry):
    name = entry[0] if isinstance(entry, tuple) else entry
    return not any(mod in name for mod in _QT_UNUSED)

qt_binaries = [e for e in qt_binaries if _keep_qt(e)]
qt_datas    = [e for e in qt_datas    if _keep_qt(e)]

added_files += kr_datas + qt_datas

# winrt — Windows only
winrt_hidden = []
if sys.platform == "win32":
    import importlib.util as _ilu
    if _ilu.find_spec("winrt"):
        winrt_hidden = collect_submodules("winrt")

# ── Hidden imports ────────────────────────────────────────────────────────────
hidden = [
    # Lokalizacja (lazy import wewnątrz funkcji — PyInstaller może pominąć)
    "locales",
    "locales.pl",
    "locales.en",
    # GUI
    "PyQt6",
    "PyQt6.QtWidgets",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.sip",
    "PIL.Image",
    "PIL.ImageQt",
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
    # Keyring
    "keyring",
    # Stdlib
    "email.mime.text",
    "email.mime.multipart",
    "ctypes",
] + winrt_hidden + kr_hidden + qt_hidden

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
    binaries=kr_binaries + qt_binaries,
    datas=added_files,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Stare GUI (usunięte)
        "tkinter", "customtkinter", "tkcalendar", "pystray",
        # Nieużywane moduły Qt6 — znacznie redukują rozmiar bundla
        "PyQt6.QtNfc", "PyQt6.QtBluetooth",
        "PyQt6.QtWebEngine", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtLocation", "PyQt6.QtPositioning", "PyQt6.QtSensors",
        "PyQt6.QtSerialPort", "PyQt6.QtSerialBus",
        "PyQt6.QtCharts", "PyQt6.QtDataVisualization",
        "PyQt6.Qt3DCore", "PyQt6.Qt3DRender", "PyQt6.Qt3DInput",
        "PyQt6.Qt3DLogic", "PyQt6.Qt3DAnimation", "PyQt6.Qt3DExtras",
        "PyQt6.QtVirtualKeyboard",
        "PyQt6.QtQuick", "PyQt6.QtQuickWidgets", "PyQt6.QtQml",
        "PyQt6.QtPdf", "PyQt6.QtPdfWidgets",
        "PyQt6.QtRemoteObjects", "PyQt6.QtScxml", "PyQt6.QtStateMachine",
        "PyQt6.QtNetworkAuth", "PyQt6.QtSql",
        "PyQt6.QtTest", "PyQt6.QtXml", "PyQt6.QtDBus",
        # Stdlib — niepotrzebne
        "unittest", "email.test", "test",
        "xmlrpc", "ftplib", "imaplib", "nntplib", "poplib", "smtplib",
        "telnetlib", "antigravity",
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
            "CFBundleShortVersionString": "1.3.3",
            "CFBundleVersion": "1.3.3",
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
