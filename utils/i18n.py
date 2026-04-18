"""
i18n.py — Prosty system tłumaczeń dla AegisVault
=================================================
Użycie:
    from utils.i18n import t
    label = t("settings.title")          # → "Ustawienia" / "Settings"
    label = t("main.n_passwords", n=42)  # → "42 haseł" / "42 passwords"
"""

from __future__ import annotations

_PL: dict[str, str] = {}
_EN: dict[str, str] = {}
_loaded = False


def _ensure_loaded() -> None:
    global _PL, _EN, _loaded
    if _loaded:
        return
    from locales.pl import STRINGS as pl
    from locales.en import STRINGS as en
    _PL = pl
    _EN  = en
    _loaded = True


def t(key: str, **kw) -> str:
    """Zwraca przetłumaczony string dla bieżącego języka."""
    try:
        _ensure_loaded()
        from utils.prefs_manager import PrefsManager
        lang = PrefsManager().get("language") or "pl"
        pool = _EN if lang == "en" else _PL
        # Fallback: EN → PL → klucz
        text = pool.get(key) or _PL.get(key, key)
        return text.format(**kw) if kw else text
    except Exception:
        return key
