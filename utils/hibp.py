"""
hibp.py - HaveIBeenPwned sprawdzanie wycieków haseł
=====================================================
Używa k-anonymity: wysyłamy tylko pierwsze 5 znaków SHA-1.
Hasło nigdy nie opuszcza urządzenia w całości.
API: https://api.pwnedpasswords.com/range/{prefix}
"""

import hashlib
import httpx

HIBP_URL = "https://api.pwnedpasswords.com/range/{prefix}"
TIMEOUT  = 8


def check_password(plaintext: str) -> tuple[bool, int]:
    """
    Sprawdza czy hasło wystąpiło w znanych wyciekach.

    Zwraca (wyciekło: bool, liczba_wycieków: int).
    W razie błędu sieci zwraca (False, -1).
    """
    sha1    = hashlib.sha1(plaintext.encode("utf-8")).hexdigest().upper()
    prefix  = sha1[:5]
    suffix  = sha1[5:]

    try:
        resp = httpx.get(HIBP_URL.format(prefix=prefix), timeout=TIMEOUT,
                         headers={"Add-Padding": "true"})
        resp.raise_for_status()
    except Exception:
        return False, -1

    for line in resp.text.splitlines():
        if ":" not in line:
            continue
        hash_suffix, count = line.split(":", 1)
        if hash_suffix.strip() == suffix:
            return True, int(count.strip())

    return False, 0
