"""
updater.py - Sprawdzanie aktualizacji AegisVault
=================================================
Pobiera informację o najnowszej wersji z GitHub Releases API
i porównuje z lokalną wersją aplikacji.
"""

import sys
import httpx
from typing import Optional
from version import APP_VERSION

GITHUB_API_URL = "https://api.github.com/repos/ByakkoHex/AegisVault/releases/latest"

# Rozszerzenie pliku instalatora dla bieżącej platformy
_PLATFORM_EXT = {
    "win32":  ".exe",
    "darwin": ".dmg",
    "linux":  ".deb",
}


def _parse_version(v: str) -> tuple:
    """Zamienia "1.2.3" na (1, 2, 3) do porównania."""
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except Exception:
        return (0, 0, 0)


def _pick_download_url(assets: list, html_url: str) -> str:
    """Zwraca URL odpowiedniego instalatora dla bieżącej platformy."""
    ext = _PLATFORM_EXT.get(sys.platform, "")
    for asset in assets:
        name = asset.get("name", "")
        if ext and name.endswith(ext):
            return asset.get("browser_download_url", html_url)
    return html_url  # fallback — strona release na GitHubie


def check_for_update() -> Optional[dict]:
    """
    Sprawdza GitHub Releases pod kątem nowszej wersji.

    Returns:
        dict z polami: version, download_url, changelog
        jeśli dostępna jest nowsza wersja, None w przeciwnym razie.
    """
    try:
        resp = httpx.get(
            GITHUB_API_URL,
            timeout=8,
            headers={"Accept": "application/vnd.github+json"},
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        tag = data.get("tag_name", "0.0.0")

        if _parse_version(tag) > _parse_version(APP_VERSION):
            return {
                "current":      APP_VERSION,
                "version":      tag.lstrip("v"),
                "download_url": _pick_download_url(
                    data.get("assets", []),
                    data.get("html_url", ""),
                ),
                "changelog":    data.get("body", "Brak informacji."),
            }
        return None
    except Exception:
        return None
