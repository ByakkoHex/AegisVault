"""
export_manager.py - Eksport haseł do popularnych formatów
==========================================================
Obsługiwane formaty wyjściowe:
  - Generic CSV  — tytuł, login, hasło, URL, notatki
  - Bitwarden JSON — {"encrypted": false, "items": [...]}
  - 1Password CSV  — Title, Website, Username, Password, Notes, OTPAuth
  - KeePass XML    — format eksportu KeePass 2

UWAGA: Wszystkie formaty poza .aegis zawierają hasła w postaci jawnej (plaintext).
"""

import csv
import json
import io
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent


# ──────────────────────────────────────────────
# GENERIC CSV
# ──────────────────────────────────────────────

def export_csv(entries: list[dict], filepath: str) -> int:
    """
    Generic CSV: Title, Username, Password, URL, Notes, OTPAuth
    Kompatybilny z importem w AegisVault (import_manager._from_generic_csv).
    """
    fieldnames = ["Title", "Username", "Password", "URL", "Notes", "OTPAuth"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in entries:
            writer.writerow({
                "Title":    e.get("title", ""),
                "Username": e.get("username", ""),
                "Password": e.get("password", ""),
                "URL":      e.get("url", ""),
                "Notes":    e.get("notes", ""),
                "OTPAuth":  e.get("otp_secret", ""),
            })
    return len(entries)


# ──────────────────────────────────────────────
# BITWARDEN JSON
# ──────────────────────────────────────────────

def export_bitwarden_json(entries: list[dict], filepath: str) -> int:
    """
    Format Bitwarden JSON (niezaszyfrowany eksport):
    {"encrypted": false, "items": [{type:1, name, login:{username,password,uris,totp}, notes}]}
    Kompatybilny z importem w Bitwarden i importem w AegisVault.
    """
    items = []
    for e in entries:
        item = {
            "id":       None,
            "type":     1,         # 1 = Login
            "name":     e.get("title", ""),
            "notes":    e.get("notes") or None,
            "favorite": False,
            "login": {
                "username": e.get("username") or None,
                "password": e.get("password", ""),
                "uris": [{"match": None, "uri": e["url"]}] if e.get("url") else [],
                "totp": e.get("otp_secret") or None,
            },
        }
        items.append(item)

    data = {
        "encrypted": False,
        "folders":   [],
        "items":     items,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return len(entries)


# ──────────────────────────────────────────────
# 1PASSWORD CSV
# ──────────────────────────────────────────────

def export_1password_csv(entries: list[dict], filepath: str) -> int:
    """
    Format 1Password CSV (File → Export → CSV):
    Title, Website, Username, Password, Notes, OTPAuth
    """
    fieldnames = ["Title", "Website", "Username", "Password", "Notes", "OTPAuth"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in entries:
            writer.writerow({
                "Title":    e.get("title", ""),
                "Website":  e.get("url", ""),
                "Username": e.get("username", ""),
                "Password": e.get("password", ""),
                "Notes":    e.get("notes", ""),
                "OTPAuth":  e.get("otp_secret", ""),
            })
    return len(entries)


# ──────────────────────────────────────────────
# KEEPASS XML
# ──────────────────────────────────────────────

def export_keepass_xml(entries: list[dict], filepath: str) -> int:
    """
    Format KeePass 2 XML (File → Export → KeePass XML 2.x).
    Importowalny przez KeePass 2, KeePassXC i inne.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    root = Element("KeePassFile")

    # Meta
    meta = SubElement(root, "Meta")
    SubElement(meta, "Generator").text          = "AegisVault"
    SubElement(meta, "DatabaseName").text        = "AegisVault Export"
    SubElement(meta, "DatabaseNameChanged").text = now
    SubElement(meta, "RecycleBinEnabled").text   = "False"

    # Root group
    body  = SubElement(root, "Root")
    group = SubElement(body, "Group")
    SubElement(group, "UUID").text = "AAAAAAAAAAAAAAAAAAAAAA=="
    SubElement(group, "Name").text = "AegisVault"
    SubElement(group, "IsExpanded").text = "True"

    for e in entries:
        entry_el = SubElement(group, "Entry")
        SubElement(entry_el, "UUID").text = "AAAAAAAAAAAAAAAAAAAAAA=="

        def _str(key: str, value: str):
            s = SubElement(entry_el, "String")
            SubElement(s, "Key").text   = key
            v = SubElement(s, "Value")
            v.text = value or ""

        _str("Title",    e.get("title", ""))
        _str("UserName", e.get("username", ""))
        _str("Password", e.get("password", ""))
        _str("URL",      e.get("url", ""))
        _str("Notes",    e.get("notes", ""))
        if e.get("otp_secret"):
            _str("otp", f"otpauth://totp/{e.get('title','')}?secret={e['otp_secret']}")

    tree = ElementTree(root)
    indent(tree, space="  ")
    with open(filepath, "wb") as f:
        tree.write(f, xml_declaration=True, encoding="utf-8")
    return len(entries)


# ──────────────────────────────────────────────
# HELPER — pobierz plaintext entries z bazy
# ──────────────────────────────────────────────

def collect_entries(db, crypto, user) -> list[dict]:
    """Odszyfrowuje wszystkie aktywne hasła i zwraca jako listę słowników."""
    entries = []
    for e in db.get_all_passwords(user):
        try:
            pwd = db.decrypt_password(e, crypto)
        except Exception:
            pwd = ""
        entries.append({
            "title":      e.title or "",
            "username":   e.username or "",
            "password":   pwd,
            "url":        e.url or "",
            "notes":      e.notes or "",
            "category":   e.category or "Inne",
            "otp_secret": e.otp_secret or "",
            "expires_at": e.expires_at.isoformat() if e.expires_at else "",
        })
    return entries
