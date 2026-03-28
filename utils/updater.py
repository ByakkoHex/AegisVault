"""
updater.py - Sprawdzanie aktualizacji AegisVault
=================================================
Pobiera informację o najnowszej wersji z serwera synchronizacji
i porównuje z lokalną wersją aplikacji.
"""

import httpx
from typing import Optional
from version import APP_VERSION


def _parse_version(v: str) -> tuple:
    """Zamienia "1.2.3" na (1, 2, 3) do porównania."""
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0, 0, 0)


def check_for_update(server_url: str) -> Optional[dict]:
    """
    Sprawdza serwer pod kątem nowszej wersji.

    Returns:
        dict z polami: version, download_url, changelog
        jeśli dostępna jest nowsza wersja, None w przeciwnym razie.
    """
    try:
        url = server_url.rstrip("/") + "/version"
        resp = httpx.get(url, timeout=8)
        if resp.status_code != 200:
            return None

        data = resp.json()
        server_ver = data.get("version", "0.0.0")

        if _parse_version(server_ver) > _parse_version(APP_VERSION):
            return {
                "current":      APP_VERSION,
                "version":      server_ver,
                "download_url": data.get("download_url", ""),
                "changelog":    data.get("changelog", ""),
            }
        return None
    except Exception:
        return None
