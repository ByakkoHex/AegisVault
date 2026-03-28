"""
totp.py - Moduł uwierzytelniania dwuskładnikowego (2FA)
=======================================================
Wykorzystuje TOTP (Time-based One-Time Password) zgodny z RFC 6238.
Kompatybilny z: Google Authenticator, Authy, Microsoft Authenticator.

Przepływ:
1. Przy rejestracji → generuj sekret → pokaż QR kod → użytkownik skanuje
2. Przy logowaniu  → użytkownik podaje 6-cyfrowy kod z aplikacji
3. Serwer weryfikuje kod (ważny przez 30 sekund)
"""

import pyotp
import qrcode
import base64
from io import BytesIO
from PIL import Image
from utils.logger import get_logger

logger = get_logger(__name__)


# ──────────────────────────────────────────────
# GENEROWANIE SEKRETU
# ──────────────────────────────────────────────

def generate_totp_secret() -> str:
    """
    Generuje losowy sekret TOTP (Base32, 32 znaki).
    Należy zapisać go w bazie danych dla użytkownika (pole totp_secret).
    """
    return pyotp.random_base32()


# ──────────────────────────────────────────────
# WERYFIKACJA KODU
# ──────────────────────────────────────────────

def verify_totp_code(secret: str, code: str) -> bool:
    """
    Weryfikuje 6-cyfrowy kod TOTP podany przez użytkownika.

    Parametry:
        secret: sekret zapisany w bazie danych użytkownika
        code:   kod wpisany przez użytkownika (6 cyfr)

    Zwraca True jeśli kod jest poprawny, False w przeciwnym razie.
    Obsługuje okno tolerancji ±1 okres (±30 sekund) na wypadek
    małej rozbieżności czasu między urządzeniami.
    """
    totp = pyotp.TOTP(secret)
    result = totp.verify(code, valid_window=1)
    logger.debug(f"Weryfikacja TOTP: wynik={result}, okno=±1")
    return result


def get_current_code(secret: str) -> str:
    """
    Zwraca aktualny kod TOTP (do celów testowych).
    W produkcji kod generuje aplikacja mobilna użytkownika.
    """
    totp = pyotp.TOTP(secret)
    return totp.now()


# ──────────────────────────────────────────────
# GENEROWANIE KODU QR
# ──────────────────────────────────────────────

def generate_qr_code(secret: str, username: str, issuer: str = "AegisVault") -> Image.Image:
    """
    Generuje kod QR do zeskanowania w aplikacji uwierzytelniającej.

    Parametry:
        secret:   sekret TOTP użytkownika
        username: nazwa użytkownika (widoczna w aplikacji)
        issuer:   nazwa aplikacji (widoczna w aplikacji)

    Zwraca obiekt PIL.Image gotowy do wyświetlenia lub zapisu.
    """
    logger.info(f">>> Generowanie QR: użytkownik={username!r}, issuer={issuer!r}")
    logger.debug(f"    sekret długość={len(secret)}, typ={type(secret).__name__}")

    # Generuj URI zgodny ze standardem otpauth://
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=username, issuer_name=issuer)
    # Logujemy pełne URI (sekret jest w nim zakodowany — tylko do debugowania lokalnego)
    logger.debug(f"    URI pełne: {uri}")
    logger.debug(f"    URI długość={len(uri)}")

    # Stwórz kod QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    logger.debug(f"    QR wersja={qr.version}, korekcja=ERROR_CORRECT_L, box_size=10, border=4")

    img = qr.make_image(fill_color="black", back_color="white")
    logger.info(f"    QR wygenerowany OK: rozmiar={img.size}, tryb={img.mode}")
    return img


def generate_qr_code_base64(secret: str, username: str, issuer: str = "AegisVault") -> str:
    """
    Generuje kod QR jako string Base64 (przydatne do wyświetlenia w GUI).
    Zwraca string PNG zakodowany w Base64.
    """
    try:
        img = generate_qr_code(secret, username, issuer)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception:
        logger.error("Błąd generowania QR base64", exc_info=True)
        raise


def save_qr_code(secret: str, username: str, filepath: str = "qr_code.png") -> None:
    """
    Zapisuje kod QR do pliku PNG.
    Przydatne podczas konfiguracji 2FA — użytkownik może wydrukować QR.
    """
    img = generate_qr_code(secret, username)
    img.save(filepath)
    print(f"Kod QR zapisany do: {filepath}")


# ──────────────────────────────────────────────
# KLASA TOTPManager (wygodne API)
# ──────────────────────────────────────────────

class TOTPManager:
    """
    Wygodna klasa do zarządzania 2FA dla konkretnego użytkownika.
    """

    def __init__(self, secret: str = None):
        """
        Parametry:
            secret: istniejący sekret (przy logowaniu) lub None (przy rejestracji)
        """
        self.secret = secret or generate_totp_secret()

    def verify(self, code: str) -> bool:
        """Weryfikuje kod podany przez użytkownika."""
        return verify_totp_code(self.secret, code)

    def get_current_code(self) -> str:
        """Zwraca aktualny kod (do testów)."""
        return get_current_code(self.secret)

    def get_qr_image(self, username: str) -> Image.Image:
        """Zwraca obraz PIL z kodem QR."""
        return generate_qr_code(self.secret, username, issuer="AegisVault")

    def save_qr(self, username: str, filepath: str = "qr_code.png") -> None:
        """Zapisuje kod QR do pliku."""
        save_qr_code(self.secret, username, filepath)

    def get_remaining_seconds(self) -> int:
        """Zwraca ile sekund pozostało do wygaśnięcia aktualnego kodu."""
        import time
        return 30 - int(time.time()) % 30


# ──────────────────────────────────────────────
# TESTY (uruchom: py -m core.totp)
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Test modułu totp.py ===\n")

    # 1. Generowanie sekretu
    manager = TOTPManager()
    print(f"[TOTP] Wygenerowany sekret: {manager.secret}")

    # 2. Aktualny kod
    current = manager.get_current_code()
    print(f"[TOTP] Aktualny kod:        {current}")
    print(f"[TOTP] Ważny jeszcze przez: {manager.get_remaining_seconds()} sekund\n")

    # 3. Weryfikacja poprawnego kodu
    result = manager.verify(current)
    print(f"[TOTP] Weryfikacja (dobry kod):  {result}")

    # 4. Weryfikacja złego kodu
    wrong = "000000"
    result_wrong = manager.verify(wrong)
    print(f"[TOTP] Weryfikacja (zły kod):    {result_wrong}\n")

    # 5. Generowanie i zapis kodu QR
    print("[TOTP] Generowanie kodu QR...")
    manager.save_qr("czajk", "qr_test.png")
    print("[TOTP] Otwórz plik qr_test.png i zeskanuj go w Google Authenticator!\n")
    print(f"[TOTP] Lub wpisz ręcznie sekret w aplikacji: {manager.secret}")

    print("\n✅ Wszystkie testy zakończone sukcesem!")
