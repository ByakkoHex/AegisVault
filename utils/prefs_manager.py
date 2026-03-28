"""
prefs_manager.py - Preferencje UI aplikacji AegisVault
=======================================================
Przechowuje ustawienia interfejsu w %APPDATA%/AegisVault/prefs.json.
Niezależne od bazy danych (wspólne dla wszystkich kont na urządzeniu).
"""

import json
import os
from utils.paths import get_app_data_dir

DEFAULTS: dict = {
    "color_theme":      "blue",
    "accent_custom":    "#4F8EF7",   # używane gdy color_theme == "custom"
    "compact_mode":     False,
    "ctrl_w_action":    "minimize",   # "minimize" | "close"
    "autostart":        False,
    "last_username":    "",
    "auto_lock_seconds": 300,         # 0 = nigdy; 60,300,900,1800,3600
    "wh_lock_unlock":   False,        # odblokuj ekran blokady przez Windows Hello
    "log_retention_days": 7,
    "backup_interval":  "wyłączony",  # "wyłączony"|"codziennie"|"co 3 dni"|"tygodniowo"|"miesięcznie"
    "last_backup_at":   "",           # ISO datetime UTC ostatniego auto-backupu
    "grid_mode":        False,        # widok siatki (PasswordCard)
    "autotype_delay":    2,                                  # sekundy opóźnienia przed wpisaniem
    "autotype_sequence": "{USERNAME}{TAB}{PASSWORD}{ENTER}", # sekwencja wpisywania
}

THEMES: dict = {
    # Zimne
    "blue":    {"accent": "#4F8EF7", "hover": "#3a7ae0", "label": "Niebieski"},
    "cyan":    {"accent": "#00B5D8", "hover": "#0090b0", "label": "Cyjan"},
    "teal":    {"accent": "#319795", "hover": "#2c7a7b", "label": "Morski"},
    "indigo":  {"accent": "#5A67D8", "hover": "#4756c4", "label": "Indygo"},
    # Ciepłe
    "green":   {"accent": "#38A169", "hover": "#2d8a5a", "label": "Zielony"},
    "lime":    {"accent": "#6B9E00", "hover": "#547d00", "label": "Limonka"},
    "yellow":  {"accent": "#C8961E", "hover": "#a87a10", "label": "Złoty"},
    "orange":  {"accent": "#DD6B20", "hover": "#c05a15", "label": "Pomarańczowy"},
    # Fioletowo-różowe
    "red":     {"accent": "#E53E3E", "hover": "#c53030", "label": "Czerwony"},
    "pink":    {"accent": "#D53F8C", "hover": "#b83280", "label": "Różowy"},
    "purple":  {"accent": "#805AD5", "hover": "#6b46c1", "label": "Fioletowy"},
    "rose":    {"accent": "#F56565", "hover": "#e53e3e", "label": "Róż"},
}


class PrefsManager:
    _instance = None

    def __new__(cls):
        # Singleton — jeden obiekt na cały proces
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._path = os.path.join(get_app_data_dir(), "prefs.json")
        self._data = dict(DEFAULTS)
        self._load()

    # ──────────────────────────────────────────────
    # Publiczne API
    # ──────────────────────────────────────────────

    def get(self, key: str):
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self._save()

    def get_accent(self) -> str:
        if self._data.get("color_theme") == "custom":
            return self._data.get("accent_custom", "#4F8EF7")
        return THEMES.get(self._data.get("color_theme", "blue"), THEMES["blue"])["accent"]

    def get_accent_hover(self) -> str:
        if self._data.get("color_theme") == "custom":
            return self._darken_color(self._data.get("accent_custom", "#4F8EF7"))
        return THEMES.get(self._data.get("color_theme", "blue"), THEMES["blue"])["hover"]

    def get_theme_colors(self) -> dict:
        if self._data.get("color_theme") == "custom":
            acc = self._data.get("accent_custom", "#4F8EF7")
            return {"accent": acc, "hover": self._darken_color(acc), "label": "Własny"}
        return THEMES.get(self._data.get("color_theme", "blue"), THEMES["blue"])

    @staticmethod
    def _darken_color(hex_color: str, factor: float = 0.80) -> str:
        c = hex_color.lstrip("#")
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        return f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"

    # ──────────────────────────────────────────────
    # Wewnętrzne
    # ──────────────────────────────────────────────

    def _load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in saved.items():
                if k in DEFAULTS:
                    self._data[k] = v
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except OSError:
            pass
