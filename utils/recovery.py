"""
recovery.py - Klucz recovery do resetu masterhasła bez TOTP
===========================================================
Format klucza:  XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX  (32 znaki base32, 160 bitów)
Derywacja:      Argon2id (lżejszy niż login — time=2, mem=32MB)
Przechowywanie: recovery_salt + recovery_encrypted_master w tabeli users
                (masterhasło zaszyfrowane kluczem derived z phrase)

Ograniczenie:   Zmiana masterhasła kasuje recovery (nie można re-szyfrować bez phrase).
                Użytkownik musi skonfigurować recovery ponownie po zmianie hasła.
"""

import secrets
import base64
from argon2.low_level import hash_secret_raw, Type as Argon2Type
from cryptography.fernet import Fernet, InvalidToken

_A2_TIME_COST   = 2
_A2_MEMORY_COST = 32768   # 32 MB
_A2_PARALLELISM = 2
_A2_HASH_LEN    = 32


def generate_recovery_key() -> str:
    """
    Generuje losowy klucz recovery: 32 znaki base32 (160 bitów),
    podzielony na 8 grup po 4 znaki: ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567
    """
    raw = secrets.token_bytes(20)
    key = base64.b32encode(raw).decode("ascii")   # 32 znaków
    return "-".join(key[i:i+4] for i in range(0, 32, 4))


def generate_recovery_salt() -> bytes:
    return secrets.token_bytes(16)


def _normalize(phrase: str) -> bytes:
    """Normalizuje phrase: wielkie litery, usuwa myślniki i spacje."""
    return phrase.upper().replace("-", "").replace(" ", "").encode("ascii")


def _derive_fernet_key(phrase: str, salt: bytes) -> bytes:
    raw = hash_secret_raw(
        secret=_normalize(phrase),
        salt=salt,
        time_cost=_A2_TIME_COST,
        memory_cost=_A2_MEMORY_COST,
        parallelism=_A2_PARALLELISM,
        hash_len=_A2_HASH_LEN,
        type=Argon2Type.ID,
    )
    return base64.urlsafe_b64encode(raw)


def encrypt_with_recovery(master_password: str, phrase: str, salt: bytes) -> bytes:
    """Szyfruje masterhasło kluczem derived z phrase."""
    fk = _derive_fernet_key(phrase, salt)
    return Fernet(fk).encrypt(master_password.encode("utf-8"))


def decrypt_with_recovery(encrypted: bytes, phrase: str, salt: bytes) -> str | None:
    """
    Odszyfrowuje masterhasło kluczem derived z phrase.
    Zwraca None jeśli klucz nieprawidłowy.
    """
    try:
        fk = _derive_fernet_key(phrase, salt)
        return Fernet(fk).decrypt(encrypted).decode("utf-8")
    except (InvalidToken, Exception):
        return None
