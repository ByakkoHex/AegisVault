"""
push_auth.py - Klient push-approve 2FA dla AegisVault
=======================================================
Umożliwia zatwierdzanie logowania z telefonu zamiast wpisywania kodu TOTP.
Wymaga działającego serwera sync AegisVault (localhost:8000 domyślnie).
"""

import socket
import httpx

SERVER_URL = "http://localhost:8000"


def get_local_ip() -> str:
    """Zwraca lokalny adres IP komputera (widoczny w sieci lokalnej)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


class PushAuthClient:
    def __init__(self, server_url: str = SERVER_URL):
        self.server_url = server_url.rstrip("/")

    def is_available(self) -> bool:
        """Sprawdza czy serwer sync jest dostępny."""
        try:
            resp = httpx.get(f"{self.server_url}/health", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def create_challenge(self, username: str) -> dict:
        """
        Tworzy nowe wyzwanie push-approve.
        Zwraca {'token': str, 'expires_in': int}.
        """
        resp = httpx.post(
            f"{self.server_url}/auth/push/create",
            json={"username": username},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()

    def poll_status(self, token: str) -> str:
        """
        Sprawdza status wyzwania.
        Zwraca: 'pending' | 'approved' | 'denied' | 'expired'
        """
        try:
            resp = httpx.get(
                f"{self.server_url}/auth/push/{token}/status",
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json().get("status", "expired")
            return "expired"
        except Exception:
            return "error"

    def get_approve_url(self, token: str) -> str:
        """
        Zwraca URL strony zatwierdzenia z lokalnym IP (dostępny z telefonu w sieci).
        """
        local_ip = get_local_ip()
        port = self._extract_port()
        return f"http://{local_ip}:{port}/auth/push/{token}"

    def _extract_port(self) -> int:
        try:
            return int(self.server_url.split(":")[-1])
        except Exception:
            return 8000
