"""
host_session.py — Zarządzanie sesją w pamięci
==============================================
Przechowuje CryptoManager i dane użytkownika na czas sesji.
Sesja wygasa po SESSION_DURATION sekundach bezczynności (sliding window).
"""

from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.crypto import CryptoManager
    from database.models import User

SESSION_DURATION = 300  # sekund = 5 minut (jak w desktop auto-lock)

# Stan sesji (moduł-level — żyje przez cały czas procesu hosta)
_user: Optional["User"] = None
_crypto: Optional["CryptoManager"] = None
_username: Optional[str] = None
_expires_at: Optional[datetime] = None


def create_session(user: "User", crypto: "CryptoManager") -> datetime:
    """Tworzy nową sesję. Zwraca czas wygaśnięcia."""
    global _user, _crypto, _username, _expires_at
    _user = user
    _crypto = crypto
    _username = user.username
    _expires_at = datetime.utcnow() + timedelta(seconds=SESSION_DURATION)
    return _expires_at


def destroy_session() -> None:
    """Niszczy sesję i usuwa klucz szyfrujący z pamięci."""
    global _user, _crypto, _username, _expires_at
    _user = None
    _crypto = None
    _username = None
    _expires_at = None


def is_valid() -> bool:
    """Zwraca True jeśli sesja istnieje i nie wygasła."""
    if _crypto is None or _expires_at is None:
        return False
    return datetime.utcnow() < _expires_at


def refresh() -> None:
    """Przesuwa okno wygaśnięcia sesji (sliding expiry)."""
    global _expires_at
    if _expires_at is not None:
        _expires_at = datetime.utcnow() + timedelta(seconds=SESSION_DURATION)


def get_crypto() -> Optional["CryptoManager"]:
    return _crypto if is_valid() else None


def get_user() -> Optional["User"]:
    return _user if is_valid() else None


def get_username() -> Optional[str]:
    return _username if is_valid() else None


def get_expires_at() -> Optional[datetime]:
    return _expires_at if is_valid() else None
