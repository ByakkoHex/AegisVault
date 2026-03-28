"""
import_manager.py - Import haseł z popularnych menedżerów
==========================================================
Obsługiwane formaty:
  - LastPass   CSV  (Name, URL, Username, Password, Notes, Grouping, ...)
  - Bitwarden  JSON (items[].login)
  - 1Password  CSV  (Title, Website, Username, Password, Notes, ...)
  - Generic    CSV  (dowolna kombinacja kolumn title/name, url, username/login, password)
"""

import csv
import json
import io
from typing import List, Dict


PasswordItem = Dict[str, str]   # title, username, password, url, notes, category


# ──────────────────────────────────────────────
# LASTPASS
# ──────────────────────────────────────────────

def _from_lastpass(content: str) -> List[PasswordItem]:
    """
    Format LastPass CSV:
    url,username,password,totp,extra,name,grouping,fav
    """
    items = []
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        title = row.get("name") or row.get("Name") or ""
        if not title:
            continue
        items.append({
            "title":    title.strip(),
            "username": (row.get("username") or row.get("Username") or "").strip(),
            "password": (row.get("password") or row.get("Password") or "").strip(),
            "url":      (row.get("url") or row.get("URL") or "").strip(),
            "notes":    (row.get("extra") or row.get("Notes") or "").strip(),
            "category": (row.get("grouping") or row.get("Group") or "Inne").strip() or "Inne",
        })
    return items


# ──────────────────────────────────────────────
# BITWARDEN
# ──────────────────────────────────────────────

def _from_bitwarden(content: str) -> List[PasswordItem]:
    """
    Format Bitwarden JSON:
    { "items": [ { "name", "login": { "username", "password", "uris": [{"uri"}] }, "notes", "folderId" } ] }
    """
    data  = json.loads(content)
    items = []
    for item in data.get("items", []):
        if item.get("type") != 1:   # type 1 = Login
            continue
        login = item.get("login") or {}
        uris  = login.get("uris") or []
        url   = uris[0].get("uri", "") if uris else ""
        items.append({
            "title":    item.get("name", "").strip(),
            "username": (login.get("username") or "").strip(),
            "password": (login.get("password") or "").strip(),
            "url":      url.strip(),
            "notes":    (item.get("notes") or "").strip(),
            "category": "Inne",
        })
    return items


# ──────────────────────────────────────────────
# 1PASSWORD
# ──────────────────────────────────────────────

def _from_1password(content: str) -> List[PasswordItem]:
    """
    Format 1Password CSV (eksport przez File → Export):
    Title,Website,Username,Password,Notes,OTPAuth
    """
    items = []
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        title = row.get("Title") or row.get("title") or ""
        if not title:
            continue
        items.append({
            "title":    title.strip(),
            "username": (row.get("Username") or row.get("username") or "").strip(),
            "password": (row.get("Password") or row.get("password") or "").strip(),
            "url":      (row.get("Website") or row.get("website") or row.get("URL") or "").strip(),
            "notes":    (row.get("Notes") or row.get("notes") or "").strip(),
            "category": "Inne",
        })
    return items


# ──────────────────────────────────────────────
# GENERIC CSV
# ──────────────────────────────────────────────

_TITLE_KEYS    = ("title", "name", "service", "site", "account")
_USERNAME_KEYS = ("username", "login", "user", "email", "login_name")
_PASSWORD_KEYS = ("password", "pass", "passwd", "secret")
_URL_KEYS      = ("url", "website", "uri", "link", "web")
_NOTES_KEYS    = ("notes", "note", "comment", "extra", "memo")


def _find(row: dict, keys) -> str:
    for k in keys:
        for rk in row:
            if rk.lower().strip() == k:
                val = row[rk]
                if val:
                    return val.strip()
    return ""


def _from_generic_csv(content: str) -> List[PasswordItem]:
    items = []
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        title    = _find(row, _TITLE_KEYS)
        password = _find(row, _PASSWORD_KEYS)
        if not title or not password:
            continue
        items.append({
            "title":    title,
            "username": _find(row, _USERNAME_KEYS),
            "password": password,
            "url":      _find(row, _URL_KEYS),
            "notes":    _find(row, _NOTES_KEYS),
            "category": "Inne",
        })
    return items


# ──────────────────────────────────────────────
# DETEKCJA FORMATU
# ──────────────────────────────────────────────

def _detect_format(content: str, filepath: str) -> str:
    lower = filepath.lower()
    if lower.endswith(".json"):
        return "bitwarden"

    first_line = content.splitlines()[0].lower() if content else ""
    if "grouping" in first_line or ("url" in first_line and "extra" in first_line):
        return "lastpass"
    if "otpauth" in first_line or ("title" in first_line and "website" in first_line):
        return "1password"
    return "generic"


# ──────────────────────────────────────────────
# PUBLICZNE API
# ──────────────────────────────────────────────

def import_file(filepath: str) -> tuple[List[PasswordItem], str]:
    """
    Wczytuje i parsuje plik eksportu innego menedżera.
    Zwraca (lista_wpisów, wykryty_format).
    Rzuca ValueError jeśli format nieobsługiwany lub plik uszkodzony.
    """
    with open(filepath, "r", encoding="utf-8-sig") as f:
        content = f.read()

    fmt = _detect_format(content, filepath)

    parsers = {
        "lastpass":  _from_lastpass,
        "bitwarden": _from_bitwarden,
        "1password": _from_1password,
        "generic":   _from_generic_csv,
    }

    items = parsers[fmt](content)
    if not items:
        raise ValueError("Nie znaleziono żadnych wpisów w pliku.")
    return items, fmt
