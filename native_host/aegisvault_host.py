"""
aegisvault_host.py — AegisVault Native Messaging Host
======================================================
Uruchamiany przez przeglądarkę jako podproces przez Native Messaging API.
Czyta wiadomości JSON ze stdin, odpowiada na stdout.

WAŻNE: Ten skrypt dodaje katalog projektu do sys.path, żeby móc importować
moduły core/ i database/ bezpośrednio — bez duplikowania kodu kryptograficznego.
"""

import os
import sys

# ─────────────────────────────────────────────────────────────
# sys.path — dodaj katalog projektu (rodzic native_host/)
# ─────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ─────────────────────────────────────────────────────────────
# Teraz możemy importować z projektu
# ─────────────────────────────────────────────────────────────
from urllib.parse import urlparse

from core.crypto import CryptoManager, verify_master_password
from core.totp import verify_totp_code
from database.db_manager import DatabaseManager
from database.models import User, Password
from utils.paths import get_db_path

from native_host.host_protocol import read_message, send_ok, send_error
import native_host.host_session as session

# ─────────────────────────────────────────────────────────────
# INICJALIZACJA BAZY DANYCH (tylko do odczytu)
# ─────────────────────────────────────────────────────────────

_db: DatabaseManager | None = None


def get_db() -> DatabaseManager:
    global _db
    if _db is None:
        db_path = get_db_path("aegisvault.db")
        _db = DatabaseManager(db_path)
    return _db


# ─────────────────────────────────────────────────────────────
# HANDLERY WIADOMOŚCI
# ─────────────────────────────────────────────────────────────

def handle_unlock(request_id: str, data: dict) -> None:
    username = data.get("username", "").strip()
    master_password = data.get("master_password", "")
    totp_code = data.get("totp_code")

    if not username or not master_password:
        send_error(request_id, "INVALID_CREDENTIALS")
        return

    db = get_db()
    user: User | None = db.session.query(User).filter_by(username=username).first()

    if not user or not verify_master_password(master_password, user.master_password_hash):
        send_error(request_id, "INVALID_CREDENTIALS")
        return

    # Sprawdź TOTP jeśli użytkownik ma włączone 2FA
    db = get_db()
    if db.has_totp(user):
        if not totp_code:
            send_error(request_id, "TOTP_REQUIRED")
            return
        if not verify_totp_code(db.get_totp_secret(user), totp_code):
            send_error(request_id, "INVALID_TOTP")
            return

    # Utwórz CryptoManager z kluczem pochodnym od hasła głównego
    crypto = CryptoManager(master_password, user.salt)

    # Zainicjuj sesję
    expires_at = session.create_session(user, crypto)

    send_ok(request_id, {
        "username": username,
        "has_totp": db.has_totp(user),
        "session_expires_at": expires_at.isoformat(),
    })


def handle_lock(request_id: str, _data: dict) -> None:
    session.destroy_session()
    send_ok(request_id, {"status": "locked"})


def handle_get_credentials_for_url(request_id: str, data: dict) -> None:
    if not session.is_valid():
        send_error(request_id, "SESSION_EXPIRED")
        return

    url = data.get("url", "")
    user = session.get_user()
    crypto = session.get_crypto()

    try:
        request_host = urlparse(url).hostname or ""
    except Exception:
        request_host = ""

    db = get_db()
    all_passwords: list[Password] = db.get_all_passwords(user)

    matched = []
    for entry in all_passwords:
        if not entry.url:
            continue
        try:
            entry_url = entry.url if "://" in entry.url else f"https://{entry.url}"
            entry_host = urlparse(entry_url).hostname or ""
        except Exception:
            continue

        # Dopasowanie: hostname zawiera lub jest równy szukanemu
        if request_host and (entry_host == request_host or entry_host.endswith(f".{request_host}") or request_host.endswith(f".{entry_host}")):
            # Odszyfruj hasło przy dopasowaniu (autofill wymaga hasła od razu)
            try:
                plaintext = db.decrypt_password(entry, crypto)
            except Exception:
                plaintext = ""

            matched.append({
                "id":       entry.id,
                "title":    entry.title,
                "username": entry.username or "",
                "password": plaintext,
                "url":      entry.url or "",
                "category": entry.category or "Inne",
            })

    session.refresh()
    send_ok(request_id, {"credentials": matched})


def handle_get_all_credentials(request_id: str, data: dict) -> None:
    if not session.is_valid():
        send_error(request_id, "SESSION_EXPIRED")
        return

    user = session.get_user()
    search = (data.get("search") or "").lower()

    db = get_db()
    all_passwords: list[Password] = db.get_all_passwords(user)

    results = []
    for entry in all_passwords:
        if search:
            haystack = f"{entry.title} {entry.username} {entry.url}".lower()
            if search not in haystack:
                continue

        # Lista: BEZ hasła (tylko przy GET_CREDENTIAL_BY_ID)
        results.append({
            "id":       entry.id,
            "title":    entry.title,
            "username": entry.username or "",
            "url":      entry.url or "",
            "category": entry.category or "Inne",
        })

    session.refresh()
    send_ok(request_id, {"credentials": results})


def handle_get_credential_by_id(request_id: str, data: dict) -> None:
    if not session.is_valid():
        send_error(request_id, "SESSION_EXPIRED")
        return

    entry_id = data.get("id")
    if not isinstance(entry_id, int):
        send_error(request_id, "INVALID_ID")
        return

    user = session.get_user()
    crypto = session.get_crypto()
    db = get_db()

    entry: Password | None = db.get_password_by_id(entry_id, user)
    if not entry:
        send_error(request_id, "NOT_FOUND")
        return

    try:
        plaintext = db.decrypt_password(entry, crypto)
    except Exception as e:
        send_error(request_id, f"DECRYPT_ERROR: {e}")
        return

    session.refresh()
    send_ok(request_id, {
        "id":       entry.id,
        "title":    entry.title,
        "username": entry.username or "",
        "password": plaintext,
        "url":      entry.url or "",
        "notes":    entry.notes or "",
        "category": entry.category or "Inne",
    })


def handle_ping(request_id: str, _data: dict) -> None:
    send_ok(request_id, {"status": "alive", "session_valid": session.is_valid()})


# ─────────────────────────────────────────────────────────────
# DISPATCH
# ─────────────────────────────────────────────────────────────

HANDLERS = {
    "UNLOCK":                   handle_unlock,
    "LOCK":                     handle_lock,
    "GET_CREDENTIALS_FOR_URL":  handle_get_credentials_for_url,
    "GET_ALL_CREDENTIALS":      handle_get_all_credentials,
    "GET_CREDENTIAL_BY_ID":     handle_get_credential_by_id,
    "PING":                     handle_ping,
}


def dispatch(message: dict) -> None:
    request_id = message.get("request_id", "unknown")
    msg_type = message.get("type", "")

    handler = HANDLERS.get(msg_type)
    if handler:
        handler(request_id, message)
    else:
        send_error(request_id, f"UNKNOWN_TYPE: {msg_type}")


# ─────────────────────────────────────────────────────────────
# PĘTLA GŁÓWNA
# ─────────────────────────────────────────────────────────────

def main():
    """
    Główna pętla — czeka na wiadomości od przeglądarki.
    Kończy działanie gdy stdin zostanie zamknięty (przeglądarka się rozłącza).
    """
    while True:
        try:
            message = read_message()
            if message is None:
                break  # EOF — przeglądarka zamknęła połączenie

            dispatch(message)

        except KeyboardInterrupt:
            break
        except Exception as exc:
            # Nie crashuj procesu — odpowiedz błędem
            request_id = "unknown"
            if isinstance(exc, dict):
                request_id = exc.get("request_id", "unknown")
            send_error(request_id, f"INTERNAL_ERROR: {exc}")


if __name__ == "__main__":
    main()
