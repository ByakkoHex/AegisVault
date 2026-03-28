"""
crypto.py - Moduł szyfrowania dla Password Managera
====================================================
Wykorzystuje:
- AES-256 (przez Fernet z biblioteki cryptography)
- PBKDF2-HMAC-SHA256 do derywacji klucza z hasła masterowego
- bcrypt do bezpiecznego hashowania hasła masterowego
"""

import os
import base64
import bcrypt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


# ──────────────────────────────────────────────
# HASŁO MASTEROWE
# ──────────────────────────────────────────────

def hash_master_password(password: str) -> bytes:
    """
    Hashuje hasło masterowe przy użyciu bcrypt.
    Zwraca hash, który można bezpiecznie zapisać w bazie danych.
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)  # wyższy rounds = wolniejszy brute-force
    return bcrypt.hashpw(password_bytes, salt)


def verify_master_password(password: str, hashed: bytes) -> bool:
    """
    Weryfikuje czy podane hasło zgadza się z zapisanym hashem bcrypt.
    """
    password_bytes = password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed)


# ──────────────────────────────────────────────
# DERYWACJA KLUCZA AES Z HASŁA MASTEROWEGO
# ──────────────────────────────────────────────

def derive_key(password: str, salt: bytes) -> bytes:
    """
    Derywuje 256-bitowy klucz AES z hasła masterowego używając PBKDF2.

    Parametry:
        password: hasło masterowe użytkownika
        salt: losowa sól (przechowywana w bazie, nie jest sekretem)

    Zwraca klucz w formacie base64 URL-safe (wymagany przez Fernet).
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,           # 256 bitów
        salt=salt,
        iterations=480_000,  # rekomendacja OWASP 2023
    )
    key = kdf.derive(password.encode("utf-8"))
    return base64.urlsafe_b64encode(key)


def generate_salt() -> bytes:
    """
    Generuje kryptograficznie bezpieczną losową sól (16 bajtów).
    Każdy użytkownik powinien mieć własną sól.
    """
    return os.urandom(16)


# ──────────────────────────────────────────────
# SZYFROWANIE I DESZYFROWANIE HASEŁ (AES-256)
# ──────────────────────────────────────────────

class CryptoManager:
    """
    Klasa zarządzająca szyfrowaniem haseł podczas sesji.
    Klucz jest przechowywany tylko w pamięci RAM — nigdy na dysku.
    """

    def __init__(self, master_password: str, salt: bytes):
        """
        Inicjalizuje menadżer kryptograficzny.
        
        Parametry:
            master_password: hasło masterowe użytkownika
            salt: sól pobrana z bazy danych dla danego użytkownika
        """
        key = derive_key(master_password, salt)
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> bytes:
        """
        Szyfruje hasło (lub inny tekst) algorytmem AES-256.

        Zwraca zaszyfrowane bajty gotowe do zapisu w bazie danych.
        Każde wywołanie generuje inny wynik (losowy IV wewnątrz Fernet).
        """
        return self._fernet.encrypt(plaintext.encode("utf-8"))


    def decrypt(self, ciphertext: bytes) -> str:
        """
        Deszyfruje wcześniej zaszyfrowane hasło.
        
        Rzuca wyjątek InvalidToken jeśli klucz jest nieprawidłowy
        lub dane zostały zmodyfikowane (integralność HMAC).
        """
        return self._fernet.decrypt(ciphertext).decode("utf-8")

    def reencrypt(self, ciphertext: bytes, new_master_password: str, salt: bytes) -> bytes:
        """
        Ponownie szyfruje hasło przy zmianie hasła masterowego.
        Odszyfrowanie starym kluczem → zaszyfrowanie nowym.
        """
        plaintext = self.decrypt(ciphertext)
        new_key = derive_key(new_master_password, salt)
        new_fernet = Fernet(new_key)
        return new_fernet.encrypt(plaintext.encode("utf-8"))


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
    """
    Generuje kryptograficznie bezpieczne losowe hasło.
    
    Parametry:
        length:            długość hasła (min. 8)
        use_uppercase:     czy używać wielkich liter
        use_digits:        czy używać cyfr
        use_special:       czy używać znaków specjalnych
        exclude_ambiguous: wyklucza mylące znaki (0, O, l, 1, I)
    """
    if length < 8:
        raise ValueError("Hasło powinno mieć co najmniej 8 znaków.")

    # Budowanie zestawu znaków
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

    # Wypełnij resztę hasła losowymi znakami
    remaining = [secrets.choice(charset) for _ in range(length - len(required_chars))]
    
    # Połącz i przetasuj (żeby wymagane znaki nie były zawsze na początku)
    password_list = required_chars + remaining
    secrets.SystemRandom().shuffle(password_list)
    
    return "".join(password_list)


# ──────────────────────────────────────────────
# TESTY (uruchom: python crypto.py)
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Test modułu crypto.py ===\n")

    # 1. Hasło masterowe
    master_pwd = "MojeHasloMasterowe123!"
    hashed = hash_master_password(master_pwd)
    print(f"[bcrypt] Hash hasła masterowego: {hashed[:30]}...")
    print(f"[bcrypt] Weryfikacja (prawidłowe): {verify_master_password(master_pwd, hashed)}")
    print(f"[bcrypt] Weryfikacja (złe hasło):  {verify_master_password('zlehaslo', hashed)}\n")

    # 2. Szyfrowanie / deszyfrowanie
    salt = generate_salt()
    crypto = CryptoManager(master_pwd, salt)

    secret = "moje_tajne_haslo_do_banku_99!"
    encrypted = crypto.encrypt(secret)
    decrypted = crypto.decrypt(encrypted)

    print(f"[AES]   Oryginał:    {secret}")
    print(f"[AES]   Zaszyfrowane: {encrypted[:40]}...")
    print(f"[AES]   Odszyfrowane: {decrypted}")
    print(f"[AES]   Zgodność:     {secret == decrypted}\n")

    # 3. Generator haseł
    for i in range(3):
        pwd = generate_password(length=20, exclude_ambiguous=True)
        print(f"[GEN]   Hasło {i+1}: {pwd}")
