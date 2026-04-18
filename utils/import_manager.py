"""
import_manager.py - Import haseł z popularnych menedżerów
==========================================================
Obsługiwane formaty:
  - LastPass   CSV  (Name, URL, Username, Password, Notes, Grouping, ...)
  - Bitwarden  JSON (items[].login)
  - 1Password  CSV  (Title, Website, Username, Password, Notes, ...)
  - Generic    CSV  (dowolna kombinacja kolumn title/name, url, username/login, password)
  - KeePass    KDBX (.kdbx v3/v4, wymaga hasła do bazy)
"""

import csv
import json
import io
import re
from typing import List, Dict
from urllib.parse import urlparse, parse_qs, unquote


PasswordItem = Dict[str, str]   # title, username, password, url, notes, category, otp_secret


def _parse_otp_secret(otp_field: str) -> str:
    """Wyciąga Base32 sekret z pola OTPAuth (URI lub czysty sekret)."""
    if not otp_field:
        return ""
    otp_field = otp_field.strip()
    if otp_field.startswith("otpauth://"):
        try:
            parsed = urlparse(otp_field)
            secret = parse_qs(parsed.query).get("secret", [""])[0]
            return secret.upper().strip()
        except Exception:
            return ""
    # Czysty Base32
    clean = re.sub(r"[^A-Z2-7=]", "", otp_field.upper())
    return clean


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
    { "items": [ { "name", "type", "login": {...}, "secureNote": {...}, "notes", "folderId" } ] }
    type 1 = Login, type 2 = Secure Note, type 3 = Card, type 4 = Identity (3/4 pomijane).
    """
    data  = json.loads(content)
    items = []
    for item in data.get("items", []):
        item_type = item.get("type")
        name      = item.get("name", "").strip()
        if not name:
            continue

        if item_type == 1:  # Login
            login = item.get("login") or {}
            uris  = login.get("uris") or []
            url   = uris[0].get("uri", "") if uris else ""
            otp   = _parse_otp_secret(login.get("totp") or "")
            items.append({
                "title":      name,
                "username":   (login.get("username") or "").strip(),
                "password":   (login.get("password") or "").strip(),
                "url":        url.strip(),
                "notes":      (item.get("notes") or "").strip(),
                "category":   "Inne",
                "otp_secret": otp,
                "entry_type": "password",
            })
        elif item_type == 2:  # Secure Note
            items.append({
                "title":      name,
                "username":   "",
                "password":   "",
                "url":        "",
                "notes":      (item.get("notes") or "").strip(),
                "category":   "Notatki",
                "otp_secret": "",
                "entry_type": "note",
            })
        # type 3 (Card) i 4 (Identity) — pomijane, nieobsługiwany typ
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
        otp = _parse_otp_secret(row.get("OTPAuth") or row.get("otpauth") or "")
        items.append({
            "title":      title.strip(),
            "username":   (row.get("Username") or row.get("username") or "").strip(),
            "password":   (row.get("Password") or row.get("password") or "").strip(),
            "url":        (row.get("Website") or row.get("website") or row.get("URL") or "").strip(),
            "notes":      (row.get("Notes") or row.get("notes") or "").strip(),
            "category":   "Inne",
            "otp_secret": otp,
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
# KEEPASS KDBX
# ──────────────────────────────────────────────

def _from_keepass(filepath: str, kdbx_password: str) -> List[PasswordItem]:
    """
    Czyta plik .kdbx (KeePass v3/v4) przy użyciu pykeepass.
    Grupy KeePass → category (pełna ścieżka, np. "Internet / Praca").
    Obsługuje OTP przechowywane jako custom property.
    """
    try:
        from pykeepass import PyKeePass
        from pykeepass.exceptions import CredentialsError
    except ImportError:
        raise ValueError(
            "Brak biblioteki pykeepass.\n"
            "Zainstaluj: pip install pykeepass"
        )

    try:
        kp = PyKeePass(filepath, password=kdbx_password or None)
    except CredentialsError:
        raise ValueError("Nieprawidłowe hasło do bazy KeePass.")
    except Exception as e:
        raise ValueError(f"Nie można otworzyć bazy KeePass: {e}")

    items: List[PasswordItem] = []
    for entry in kp.entries:
        if getattr(entry, "is_a_history_entry", False):
            continue

        # Spłaszczamy ścieżkę grup → kategoria (pomijamy "Root")
        path_parts: list[str] = []
        g = entry.group
        while g is not None:
            name = getattr(g, "name", None) or ""
            if name and name.lower() != "root":
                path_parts.insert(0, name)
            g = getattr(g, "parentgroup", None)
        category = " / ".join(path_parts) if path_parts else "Inne"

        # OTP — KeePass przechowuje w różnych custom properties
        otp_secret = ""
        custom = getattr(entry, "custom_properties", {}) or {}
        for key in ("otp", "TimeOtp-Secret-Base32", "TOTP Seed", "totp_secret", "OTPAuth"):
            val = custom.get(key, "") or ""
            if val:
                otp_secret = _parse_otp_secret(val)
                break

        title = (entry.title or "").strip()
        if not title:
            continue

        items.append({
            "title":      title,
            "username":   (entry.username or "").strip(),
            "password":   (entry.password or "").strip(),
            "url":        (entry.url or "").strip(),
            "notes":      (entry.notes or "").strip(),
            "category":   category,
            "otp_secret": otp_secret,
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
    Wczytuje i parsuje plik eksportu innego menedżera (CSV/JSON).
    Zwraca (lista_wpisów, wykryty_format).
    Dla plików .kdbx użyj ImportManager.import_keepass().
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


class ImportManager:
    """Fasada do importowania wpisów do bazy AegisVault."""

    def __init__(self, db, crypto, user):
        self.db     = db
        self.crypto = crypto
        self.user   = user

    def import_file(self, filepath: str) -> int:
        """Import CSV / JSON — auto-detekcja formatu."""
        items, _fmt = import_file(filepath)
        return self._save(items)

    def import_keepass(self, filepath: str, kdbx_password: str) -> int:
        """Import pliku .kdbx. Rzuca ValueError przy złym haśle."""
        items = _from_keepass(filepath, kdbx_password)
        if not items:
            raise ValueError("Nie znaleziono żadnych wpisów w bazie KeePass.")
        return self._save(items)

    def _save(self, items: List[PasswordItem]) -> int:
        count = 0
        for item in items:
            entry_type = item.get("entry_type", "password")
            if entry_type == "note":
                self.db.add_note(self.user,
                                 title=item["title"],
                                 content=item.get("notes", ""))
            else:
                self.db.add_password(
                    self.user, self.crypto,
                    title=item["title"],
                    username=item.get("username", ""),
                    plaintext_password=item.get("password", ""),
                    url=item.get("url", ""),
                    notes=item.get("notes", ""),
                    category=item.get("category", "Inne"),
                    otp_secret=item.get("otp_secret") or None,
                )
            count += 1
        return count
