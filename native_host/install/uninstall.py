"""
uninstall.py — Usuwa AegisVault Native Messaging Host z systemu
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NATIVE_HOST_DIR = os.path.dirname(SCRIPT_DIR)
HOST_NAME = "com.aegisvault.host"


def remove_file(path: str, label: str) -> None:
    if os.path.exists(path):
        os.remove(path)
        print(f"  [OK] Usunięto: {label}")
    else:
        print(f"  [--] Nie istnieje: {label}")


def remove_registry_key(reg_path: str, browser: str) -> None:
    try:
        import winreg
        full_key = f"{reg_path}\\{HOST_NAME}"
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, full_key)
        print(f"  [OK] {browser}: usunięto klucz rejestru")
    except FileNotFoundError:
        print(f"  [--] {browser}: klucz nie istniał")
    except Exception as e:
        print(f"  [BŁĄD] {browser}: {e}")


def main():
    print("\n=== AegisVault Native Host Uninstaller ===\n")

    # Usuń launchery
    for filename in ["aegisvault_host_launcher.bat", "aegisvault_host_launcher.sh"]:
        path = os.path.join(NATIVE_HOST_DIR, filename)
        remove_file(path, filename)

    # Usuń pliki manifestów
    for suffix in ["chrome", "firefox", "edge"]:
        path = os.path.join(NATIVE_HOST_DIR, f"{HOST_NAME}_{suffix}.json")
        remove_file(path, f"{HOST_NAME}_{suffix}.json")

    if sys.platform == "win32":
        remove_registry_key(r"SOFTWARE\Google\Chrome\NativeMessagingHosts", "Chrome")
        remove_registry_key(r"SOFTWARE\Microsoft\Edge\NativeMessagingHosts",  "Edge")
        remove_registry_key(r"SOFTWARE\Mozilla\NativeMessagingHosts",         "Firefox")

    elif sys.platform == "darwin":
        home = os.path.expanduser("~")
        paths = [
            os.path.join(home, f"Library/Application Support/Google/Chrome/NativeMessagingHosts/{HOST_NAME}.json"),
            os.path.join(home, f"Library/Application Support/Microsoft Edge/NativeMessagingHosts/{HOST_NAME}.json"),
            os.path.join(home, f"Library/Application Support/Chromium/NativeMessagingHosts/{HOST_NAME}.json"),
            os.path.join(home, f"Library/Application Support/Mozilla/NativeMessagingHosts/{HOST_NAME}.json"),
        ]
        for p in paths:
            remove_file(p, os.path.basename(p))

    else:  # Linux
        home = os.path.expanduser("~")
        paths = [
            os.path.join(home, f".config/google-chrome/NativeMessagingHosts/{HOST_NAME}.json"),
            os.path.join(home, f".config/chromium/NativeMessagingHosts/{HOST_NAME}.json"),
            os.path.join(home, f".config/microsoft-edge/NativeMessagingHosts/{HOST_NAME}.json"),
            os.path.join(home, f".mozilla/native-messaging-hosts/{HOST_NAME}.json"),
        ]
        for p in paths:
            remove_file(p, os.path.basename(p))

    print("\n✅ Odinstalowanie zakończone.")


if __name__ == "__main__":
    main()
