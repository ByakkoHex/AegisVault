"""
windows_hello.py - Integracja z Windows Hello dla AegisVault
=============================================================
Weryfikacja tożsamości przez Windows Hello (PIN, odcisk palca, twarz).
Hasło masterowe przechowywane bezpiecznie w Windows Credential Manager.

Wymaga: winrt-runtime, winrt-Windows.Security.Credentials.UI,
        winrt-Windows.Foundation, keyring
"""

import sys
import asyncio
import threading

_SERVICE = "AegisVault"

# Cache — sprawdzamy raz na sesję (WinRT call jest nieblokujący,
# ale nie ma powodu powtarzać go wielokrotnie)
_availability_cache: int | None = None   # 0=Available, 1=DeviceBusy, 2=DeviceNotPresent, 3=DisabledByPolicy, 4=NotConfiguredForUser
_cache_lock = threading.Lock()


def is_windows() -> bool:
    return sys.platform == "win32"


def _run_async(coro):
    """Uruchamia coroutine WinRT synchronicznie z nowego event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _get_avail_module():
    """Importuje winrt.windows.security.credentials.ui — lazy import."""
    import winrt.windows.security.credentials.ui as m  # noqa
    return m


# ── Dostępność ─────────────────────────────────────────────────────────────

def check_availability() -> str:
    """
    Zwraca status WH jako string:
      'Available' | 'DeviceBusy' | 'DeviceNotPresent' |
      'DisabledByPolicy' | 'NotConfiguredForUser' | 'Error'
    """
    if not is_windows():
        return "Error"

    global _availability_cache
    with _cache_lock:
        cached = _availability_cache

    if cached is not None:
        return _int_to_status(cached)

    try:
        m = _get_avail_module()
        result = _run_async(m.UserConsentVerifier.check_availability_async())
        code = int(result)
    except Exception:
        code = -1

    with _cache_lock:
        _availability_cache = code

    return _int_to_status(code)


def _int_to_status(code: int) -> str:
    return {
        0: "Available",
        1: "DeviceBusy",
        2: "DeviceNotPresent",
        3: "DisabledByPolicy",
        4: "NotConfiguredForUser",
    }.get(code, "Error")


def is_available() -> bool:
    """Zwraca True jeśli Windows Hello jest skonfigurowane i gotowe."""
    return check_availability() == "Available"


def invalidate_cache() -> None:
    """Wyczyść cache dostępności."""
    global _availability_cache
    with _cache_lock:
        _availability_cache = None


# ── Weryfikacja ─────────────────────────────────────────────────────────────

def verify(message: str = "Zweryfikuj tożsamość — AegisVault") -> bool:
    """
    Otwiera natywny dialog Windows Hello i zwraca True po pomyślnej weryfikacji.
    Blokuje wątek wywołujący — uruchamiaj w osobnym wątku!
    """
    if not is_windows():
        return False
    try:
        import ctypes
        # Pozwól dialogowi WH (systemowemu) przejąć fokus — bez tego zostaje za oknem aplikacji
        # ASFW_ANY = (DWORD)-1 = 0xFFFFFFFF
        ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
        m = _get_avail_module()
        result = _run_async(m.UserConsentVerifier.request_verification_async(message))
        # UserConsentVerificationResult: 0=Verified, pozostałe = błąd/anulowanie
        return int(result) == 0
    except Exception:
        return False


# ── Windows Credential Manager (keyring) ───────────────────────────────────

def store_credential(username: str, master_password: str) -> bool:
    """Zapisuje hasło masterowe w Windows Credential Manager."""
    try:
        import keyring
        keyring.set_password(_SERVICE, username, master_password)
        return True
    except Exception:
        return False


def get_credential(username: str) -> str | None:
    """Pobiera hasło masterowe z Windows Credential Manager. Zwraca None jeśli brak."""
    try:
        import keyring
        return keyring.get_password(_SERVICE, username)
    except Exception:
        return None


def delete_credential(username: str) -> bool:
    """Usuwa poświadczenie z Windows Credential Manager."""
    try:
        import keyring
        keyring.delete_password(_SERVICE, username)
        return True
    except Exception:
        return False


def has_credential(username: str) -> bool:
    """Sprawdza czy jest zapisane poświadczenie WH dla danego użytkownika."""
    return get_credential(username) is not None


# ── Komunikaty błędów dla UI ────────────────────────────────────────────────

STATUS_MESSAGES = {
    "Available":            "Windows Hello jest aktywne i gotowe.",
    "NotConfiguredForUser": "Windows Hello nie jest skonfigurowane.\nUstaw PIN lub biometrię w Ustawieniach systemu.",
    "DisabledByPolicy":     "Windows Hello jest wyłączone przez politykę organizacji.",
    "DeviceBusy":           "Urządzenie biometryczne jest zajęte. Spróbuj ponownie.",
    "DeviceNotPresent":     "Brak urządzenia biometrycznego. Zaloguj się PIN-em.",
    "Error":                "Nie można sprawdzić dostępności Windows Hello.\nUpewnij się, że pakiet winrt jest zainstalowany.",
}
