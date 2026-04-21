"""
updater.py - Sprawdzanie aktualizacji AegisVault
=================================================
Strategia:
  1. GitHub Releases API — pełne info (changelog, download URL)
  2. Fallback: GitHub Tags API — działa nawet gdy CI nie ukończył joba release
"""

import logging
import sys
from typing import Optional

from version import APP_VERSION

logger = logging.getLogger(__name__)

_OWNER = "ByakkoHex"
_REPO  = "AegisVault"

GITHUB_RELEASES_URL = f"https://api.github.com/repos/{_OWNER}/{_REPO}/releases/latest"
GITHUB_TAGS_URL     = f"https://api.github.com/repos/{_OWNER}/{_REPO}/tags"
GITHUB_RELEASES_PAGE = f"https://github.com/{_OWNER}/{_REPO}/releases"

_PLATFORM_EXT = {
    "win32":  ".exe",
    "darwin": ".dmg",
    "linux":  ".deb",
}

_HEADERS = {"Accept": "application/vnd.github+json"}


def _parse_version(v: str) -> tuple:
    """Zamienia "1.2.3" lub "v1.2.3" na (1, 2, 3) do porównania."""
    import re
    try:
        parts = v.strip().lstrip("v").split(".")
        return tuple(int(re.sub(r"[^0-9].*", "", x) or "0") for x in parts)
    except Exception:
        return (0, 0, 0)


def _pick_download_url(assets: list, html_url: str) -> str:
    ext = _PLATFORM_EXT.get(sys.platform, "")
    for asset in assets:
        name = asset.get("name", "")
        if ext and name.endswith(ext):
            return asset.get("browser_download_url", html_url)
    return html_url


def _get(url: str) -> Optional[dict]:
    import httpx
    try:
        resp = httpx.get(url, timeout=8, headers=_HEADERS, follow_redirects=True)
        logger.debug(f"GET {url} → {resp.status_code}")
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        logger.warning(f"HTTP error checking update ({url}): {e}")
        return None


def check_for_update() -> Optional[dict]:
    """
    Sprawdza GitHub pod kątem nowszej wersji.
    Próbuje Releases API, przy braku odpowiedzi (np. CI nie ukończyło release joba)
    sięga po Tags API.

    Returns:
        dict z polami: version, download_url, changelog
        jeśli dostępna jest nowsza wersja, None w przeciwnym razie.
    """
    logger.info(f"Checking for update (current: {APP_VERSION})")

    # ── 1. Releases API ──────────────────────────────────────────
    data = _get(GITHUB_RELEASES_URL)
    if data:
        tag = data.get("tag_name", "")
        if tag and _parse_version(tag) > _parse_version(APP_VERSION):
            logger.info(f"Update found via Releases API: {tag}")
            return {
                "current":      APP_VERSION,
                "version":      tag.lstrip("v"),
                "download_url": _pick_download_url(
                    data.get("assets", []),
                    data.get("html_url", GITHUB_RELEASES_PAGE),
                ),
                "changelog": data.get("body", "Brak informacji."),
            }
        if tag:
            logger.info(f"No update (latest release: {tag}, current: {APP_VERSION})")
            return None

    # ── 2. Fallback: Tags API ────────────────────────────────────
    logger.info("Releases API unavailable or empty, falling back to Tags API")
    tags_data = _get(GITHUB_TAGS_URL)
    if not tags_data or not isinstance(tags_data, list):
        logger.warning("Tags API returned no data")
        return None

    # Tagi są posortowane od najnowszego — bierzemy pierwszy
    latest_tag = tags_data[0].get("name", "") if tags_data else ""
    if latest_tag and _parse_version(latest_tag) > _parse_version(APP_VERSION):
        logger.info(f"Update found via Tags API: {latest_tag}")
        return {
            "current":      APP_VERSION,
            "version":      latest_tag.lstrip("v"),
            "download_url": GITHUB_RELEASES_PAGE,
            "changelog":    "Szczegóły na stronie GitHub Releases.",
        }

    logger.info(f"No update (latest tag: {latest_tag}, current: {APP_VERSION})")
    return None
