"""
install.py — AegisVault Native Messaging Host Installer
=========================================================
Rejestruje hosta natywnego w przeglądarkach: Chrome, Firefox, Edge.

Użycie:
    python install.py [--extension-id CHROME_EXTENSION_ID]

Po zainstalowaniu rozszerzenia w Chrome, skopiuj jego ID z chrome://extensions
i podaj jako argument. Dla Firefox używany jest gecko ID z manifest.json.

Platformy:
  Windows : rejestr HKCU\SOFTWARE\{Browser}\NativeMessagingHosts\...
  macOS   : ~/Library/Application Support/{Browser}/NativeMessagingHosts/
  Linux   : ~/.config/{browser}/NativeMessagingHosts/  lub  ~/.mozilla/...
"""

import argparse
import json
import os
import platform
import shutil
import stat
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NATIVE_HOST_DIR = os.path.dirname(SCRIPT_DIR)
HOST_SCRIPT = os.path.join(NATIVE_HOST_DIR, "aegisvault_host.py")

HOST_NAME = "com.aegisvault.host"
GECKO_ID  = "aegisvault@aegisvault.pl"

PYTHON_BIN = sys.executable


# ─────────────────────────────────────────────────────────────
# MANIFEST JSON
# ─────────────────────────────────────────────────────────────

def make_chrome_manifest(launcher_path: str, extension_ids: list[str]) -> dict:
    return {
        "name": HOST_NAME,
        "description": "AegisVault Native Messaging Host",
        "path": launcher_path,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{eid}/" for eid in extension_ids],
    }


def make_firefox_manifest(launcher_path: str) -> dict:
    return {
        "name": HOST_NAME,
        "description": "AegisVault Native Messaging Host",
        "path": launcher_path,
        "type": "stdio",
        "allowed_extensions": [GECKO_ID],
    }


# ─────────────────────────────────────────────────────────────
# LAUNCHER WRAPPER (bat na Windows, sh na Unix)
# ─────────────────────────────────────────────────────────────

def create_launcher_windows() -> str:
    """Tworzy .bat launchera i zwraca jego ścieżkę."""
    bat_path = os.path.join(NATIVE_HOST_DIR, "aegisvault_host_launcher.bat")
    with open(bat_path, "w") as f:
        f.write(f'@echo off\n"{PYTHON_BIN}" "{HOST_SCRIPT}" %*\n')
    print(f"  [+] Launcher: {bat_path}")
    return bat_path


def create_launcher_unix() -> str:
    """Tworzy shell script launchera i zwraca jego ścieżkę."""
    sh_path = os.path.join(NATIVE_HOST_DIR, "aegisvault_host_launcher.sh")
    with open(sh_path, "w") as f:
        f.write(f'#!/usr/bin/env bash\nexec "{PYTHON_BIN}" "{HOST_SCRIPT}" "$@"\n')
    # Ustaw bit wykonywalny
    st = os.stat(sh_path)
    os.chmod(sh_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print(f"  [+] Launcher: {sh_path}")
    return sh_path


# ─────────────────────────────────────────────────────────────
# REJESTRACJA
# ─────────────────────────────────────────────────────────────

def write_manifest_file(manifest_dir: str, content: dict, browser_name: str) -> bool:
    """Zapisuje manifest JSON do katalogu przeglądarki."""
    try:
        os.makedirs(manifest_dir, exist_ok=True)
        manifest_path = os.path.join(manifest_dir, f"{HOST_NAME}.json")
        with open(manifest_path, "w") as f:
            json.dump(content, f, indent=2)
        print(f"  [OK] {browser_name}: {manifest_path}")
        return True
    except Exception as e:
        print(f"  [BŁĄD] {browser_name}: {e}")
        return False


# ─── Windows ──────────────────────────────────────────────────

def register_windows(launcher_path: str, chrome_ids: list[str]) -> None:
    import winreg

    browsers = {
        "Chrome": (r"SOFTWARE\Google\Chrome\NativeMessagingHosts", make_chrome_manifest(launcher_path, chrome_ids)),
        "Edge":   (r"SOFTWARE\Microsoft\Edge\NativeMessagingHosts",  make_chrome_manifest(launcher_path, chrome_ids)),
        "Firefox":(r"SOFTWARE\Mozilla\NativeMessagingHosts",         make_firefox_manifest(launcher_path)),
    }

    for browser_name, (reg_path, manifest) in browsers.items():
        # Zapisz manifest JSON
        manifest_path = os.path.join(NATIVE_HOST_DIR, f"{HOST_NAME}_{browser_name.lower()}.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        # Zarejestruj w rejestrze
        full_key = f"{reg_path}\\{HOST_NAME}"
        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, full_key)
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, manifest_path)
            winreg.CloseKey(key)
            print(f"  [OK] {browser_name}: HKCU\\{full_key}")
        except Exception as e:
            print(f"  [BŁĄD] {browser_name} (rejestr): {e}")


# ─── macOS ────────────────────────────────────────────────────

def register_macos(launcher_path: str, chrome_ids: list[str]) -> None:
    home = os.path.expanduser("~")
    browsers = {
        "Chrome":  (os.path.join(home, "Library/Application Support/Google/Chrome/NativeMessagingHosts"),  make_chrome_manifest(launcher_path, chrome_ids)),
        "Chromium":(os.path.join(home, "Library/Application Support/Chromium/NativeMessagingHosts"),        make_chrome_manifest(launcher_path, chrome_ids)),
        "Edge":    (os.path.join(home, "Library/Application Support/Microsoft Edge/NativeMessagingHosts"),  make_chrome_manifest(launcher_path, chrome_ids)),
        "Firefox": (os.path.join(home, "Library/Application Support/Mozilla/NativeMessagingHosts"),         make_firefox_manifest(launcher_path)),
    }
    for name, (d, manifest) in browsers.items():
        write_manifest_file(d, manifest, name)


# ─── Linux ────────────────────────────────────────────────────

def register_linux(launcher_path: str, chrome_ids: list[str]) -> None:
    home = os.path.expanduser("~")
    browsers = {
        "Chrome":    (os.path.join(home, ".config/google-chrome/NativeMessagingHosts"),   make_chrome_manifest(launcher_path, chrome_ids)),
        "Chromium":  (os.path.join(home, ".config/chromium/NativeMessagingHosts"),         make_chrome_manifest(launcher_path, chrome_ids)),
        "Edge":      (os.path.join(home, ".config/microsoft-edge/NativeMessagingHosts"),   make_chrome_manifest(launcher_path, chrome_ids)),
        "Firefox":   (os.path.join(home, ".mozilla/native-messaging-hosts"),               make_firefox_manifest(launcher_path)),
    }
    for name, (d, manifest) in browsers.items():
        write_manifest_file(d, manifest, name)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Instaluje AegisVault Native Messaging Host w przeglądarkach."
    )
    parser.add_argument(
        "--extension-id",
        metavar="CHROME_EXTENSION_ID",
        default="",
        help="ID rozszerzenia Chrome/Edge (znajdziesz na chrome://extensions po załadowaniu rozszerzenia).",
    )
    args = parser.parse_args()

    chrome_ids = [args.extension_id] if args.extension_id else []

    print(f"\n=== AegisVault Native Host Installer ===")
    print(f"System:  {platform.system()} {platform.release()}")
    print(f"Python:  {PYTHON_BIN}")
    print(f"Skrypt:  {HOST_SCRIPT}")
    if chrome_ids:
        print(f"Chrome Extension ID: {chrome_ids[0]}")
    else:
        print(f"[!] Nie podano --extension-id. Manifest Chrome będzie pusty.")
        print(f"    Uruchom ponownie po zainstalowaniu rozszerzenia w Chrome:")
        print(f"    python install.py --extension-id TWOJE_EXTENSION_ID")
    print()

    if not os.path.exists(HOST_SCRIPT):
        print(f"[BŁĄD] Nie znaleziono: {HOST_SCRIPT}")
        sys.exit(1)

    print("[1/2] Tworzenie launchera...")
    if sys.platform == "win32":
        launcher = create_launcher_windows()
    else:
        launcher = create_launcher_unix()

    print("\n[2/2] Rejestrowanie hosta w przeglądarkach...")
    if sys.platform == "win32":
        register_windows(launcher, chrome_ids)
    elif sys.platform == "darwin":
        register_macos(launcher, chrome_ids)
    else:
        register_linux(launcher, chrome_ids)

    print(f"\n✅ Instalacja zakończona!")
    print(f"   Zrestartuj przeglądarkę i załaduj rozszerzenie AegisVault.")


if __name__ == "__main__":
    main()
