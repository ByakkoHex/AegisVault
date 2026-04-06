"""
crypto.py - Moduł szyfrowania dla AegisVault
=============================================
KDF v0 (legacy):  PBKDF2-HMAC-SHA256 (480k iter) + bcrypt (rounds=12)
KDF v1 (current): Argon2id (time=3, mem=64MB, par=4) — złoty standard od 2015
"""

import os
import base64
import bcrypt
from argon2 import PasswordHasher
from argon2.low_level import hash_secret_raw, Type as Argon2Type
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# Wersje KDF
KDF_PBKDF2   = 0   # stare: PBKDF2 + bcrypt
KDF_ARGON2ID = 1   # nowe: Argon2id

# Parametry Argon2id (OWASP 2023 minimum dla interaktywnego logowania)
_A2_TIME_COST   = 3
_A2_MEMORY_COST = 65536   # 64 MB
_A2_PARALLELISM = 4
_A2_HASH_LEN    = 32

_ph = PasswordHasher(
    time_cost=_A2_TIME_COST,
    memory_cost=_A2_MEMORY_COST,
    parallelism=_A2_PARALLELISM,
)


# ──────────────────────────────────────────────
# HASŁO MASTEROWE
# ──────────────────────────────────────────────

def hash_master_password(password: str, version: int = KDF_ARGON2ID) -> bytes:
    """Hashuje hasło masterowe. Zwraca bajty gotowe do zapisu w bazie."""
    if version == KDF_ARGON2ID:
        return _ph.hash(password).encode("utf-8")
    # Legacy: bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))


def verify_master_password(password: str, hashed: bytes, version: int | None = None) -> bool:
    """Weryfikuje hasło masterowe. Obsługuje oba formaty (bcrypt i Argon2id).
    Jeśli version=None, autodetektuje format z treści hasha."""
    if version is None:
        h_str = hashed.decode("utf-8") if isinstance(hashed, bytes) else hashed
        version = KDF_ARGON2ID if h_str.startswith("$argon2") else KDF_PBKDF2
    if version == KDF_ARGON2ID:
        try:
            return _ph.verify(hashed.decode("utf-8"), password)
        except Exception:
            return False
    # Legacy: bcrypt
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed)
    except Exception:
        return False


# ──────────────────────────────────────────────
# DERYWACJA KLUCZA AES Z HASŁA MASTEROWEGO
# ──────────────────────────────────────────────

def derive_key(password: str, salt: bytes, version: int = KDF_PBKDF2) -> bytes:
    """
    Derywuje 256-bitowy klucz AES z hasła masterowego.
    Zwraca klucz w formacie base64 URL-safe (wymagany przez Fernet).
    """
    if version == KDF_ARGON2ID:
        raw = hash_secret_raw(
            secret=password.encode("utf-8"),
            salt=salt,
            time_cost=_A2_TIME_COST,
            memory_cost=_A2_MEMORY_COST,
            parallelism=_A2_PARALLELISM,
            hash_len=_A2_HASH_LEN,
            type=Argon2Type.ID,
        )
        return base64.urlsafe_b64encode(raw)
    # Legacy: PBKDF2-HMAC-SHA256
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def generate_salt(size: int = 32) -> bytes:
    """Generuje kryptograficznie bezpieczną sól. Domyślnie 32 bajty (Argon2id)."""
    return os.urandom(size)


# ──────────────────────────────────────────────
# SZYFROWANIE I DESZYFROWANIE HASEŁ (AES-256)
# ──────────────────────────────────────────────

class CryptoManager:
    """
    Zarządza szyfrowaniem haseł podczas sesji.
    Klucz przechowywany tylko w RAM — nigdy na dysku.
    """

    def __init__(self, master_password: str, salt: bytes, kdf_version: int = KDF_PBKDF2):
        key = derive_key(master_password, salt, version=kdf_version)
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        return self._fernet.decrypt(ciphertext).decode("utf-8")

    def reencrypt(self, ciphertext: bytes, new_master_password: str,
                  salt: bytes, kdf_version: int = KDF_PBKDF2) -> bytes:
        """Ponownie szyfruje hasło przy zmianie hasła masterowego."""
        plaintext = self.decrypt(ciphertext)
        new_key = derive_key(new_master_password, salt, version=kdf_version)
        return Fernet(new_key).encrypt(plaintext.encode("utf-8"))


# ──────────────────────────────────────────────
# GENERATOR HASEŁ
# ──────────────────────────────────────────────

import secrets
import string

def generate_password(
    length: int = 16,
    use_uppercase: bool = True,
    use_digits: bool = True,
    use_special: bool = True,
    exclude_ambiguous: bool = False
) -> str:
    if length < 8:
        raise ValueError("Hasło powinno mieć co najmniej 8 znaków.")

    charset = string.ascii_lowercase
    required_chars = [secrets.choice(string.ascii_lowercase)]

    if use_uppercase:
        chars = string.ascii_uppercase
        if exclude_ambiguous:
            chars = chars.translate(str.maketrans("", "", "OI"))
        charset += chars
        required_chars.append(secrets.choice(chars))

    if use_digits:
        chars = string.digits
        if exclude_ambiguous:
            chars = chars.translate(str.maketrans("", "", "01"))
        charset += chars
        required_chars.append(secrets.choice(chars))

    if use_special:
        chars = "!@#$%^&*()-_=+[]{}|;:,.<>?"
        charset += chars
        required_chars.append(secrets.choice(chars))

    if exclude_ambiguous:
        charset = charset.translate(str.maketrans("", "", "0OIl1"))

    remaining = [secrets.choice(charset) for _ in range(length - len(required_chars))]
    password_list = required_chars + remaining
    secrets.SystemRandom().shuffle(password_list)
    return "".join(password_list)
