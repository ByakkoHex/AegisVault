"""
sync_client.py - Klient synchronizacji
=======================================
Odpowiada za komunikację z serwerem FastAPI.
Hasła są szyfrowane przed wysłaniem — serwer widzi tylko zaszyfrowane dane.
"""

import json
import uuid
import base64
from datetime import datetime
from typing import Optional
import httpx

SERVER_URL = "http://localhost:8000"


class SyncClient:
    def __init__(self, server_url: str = SERVER_URL):
        self.server_url = server_url.rstrip("/")
        self.token: Optional[str] = None
        self.username: Optional[str] = None

    # ──────────────────────────────────────────────
    # AUTORYZACJA
    # ──────────────────────────────────────────────

    def register(self, username: str, password: str) -> dict:
        """Rejestruje konto na serwerze synchronizacji."""
        resp = httpx.post(f"{self.server_url}/register",
                          json={"username": username, "password": password}, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def login(self, username: str, password: str) -> bool:
        """Loguje się na serwer i zapisuje token JWT."""
        resp = httpx.post(f"{self.server_url}/login",
                          json={"username": username, "password": password}, timeout=10)
        if resp.status_code != 200:
            return False
        data = resp.json()
        self.token = data["token"]
        self.username = data["username"]
        return True

    def is_connected(self) -> bool:
        """Sprawdza czy serwer jest dostępny."""
        try:
            resp = httpx.get(f"{self.server_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    # ──────────────────────────────────────────────
    # SYNCHRONIZACJA
    # ──────────────────────────────────────────────

    def push(self, db, crypto, user) -> dict:
        """
        Wysyła wszystkie lokalne hasła na serwer.
        Każdy wpis jest szyfrowany — serwer nie widzi plaintext.
        """
        entries = db.get_all_passwords(user)
        payload = []

        for entry in entries:
            # Serializuj cały wpis do JSON i zaszyfruj
            plaintext = db.decrypt_password(entry, crypto)
            entry_data = json.dumps({
                "title":    entry.title,
                "username": entry.username or "",
                "password": plaintext,
                "url":      entry.url or "",
                "notes":    entry.notes or "",
                "category": entry.category or "Inne",
            })
            encrypted = crypto.encrypt(entry_data)
            blob = base64.b64encode(encrypted).decode("utf-8")

            # Użyj ID z bazy jako client_id (stabilne)
            client_id = f"{user.username}-{entry.id}"

            payload.append({
                "client_id":      client_id,
                "title":          entry.title,
                "encrypted_blob": blob,
                "category":       entry.category or "Inne",
                "updated_at":     entry.updated_at.isoformat() if entry.updated_at else None,
            })

        resp = httpx.post(f"{self.server_url}/sync/push",
                          json={"entries": payload},
                          headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()

    def pull(self, db, crypto, user, since: Optional[datetime] = None) -> dict:
        """
        Pobiera hasła z serwera i importuje nowe/zaktualizowane lokalnie.
        Pomija wpisy które już istnieją lokalnie (po tytule).
        """
        params = {}
        if since:
            params["since"] = since.isoformat()

        resp = httpx.get(f"{self.server_url}/sync/pull",
                         params=params, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()

        existing_titles = {e.title for e in db.get_all_passwords(user)}
        imported = 0
        updated  = 0

        for item in data["entries"]:
            try:
                encrypted = base64.b64decode(item["encrypted_blob"])
                decrypted_json = crypto.decrypt(encrypted)
                entry_data = json.loads(decrypted_json)
            except Exception:
                continue  # pomiń jeśli nie można odszyfrować (inne urządzenie, inny klucz)

            if entry_data["title"] not in existing_titles:
                db.add_password(
                    user, crypto,
                    title=entry_data["title"],
                    username=entry_data.get("username", ""),
                    plaintext_password=entry_data["password"],
                    url=entry_data.get("url", ""),
                    notes=entry_data.get("notes", ""),
                    category=entry_data.get("category", "Inne"),
                )
                imported += 1
            else:
                updated += 1

        return {"imported": imported, "skipped": updated, "total": data["count"]}

    def delete_remote(self, user, entry_ids: list[int]) -> dict:
        """Oznacza wpisy jako usunięte na serwerze."""
        client_ids = [f"{user.username}-{eid}" for eid in entry_ids]
        resp = httpx.post(f"{self.server_url}/sync/delete",
                          json={"client_ids": client_ids},
                          headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()
