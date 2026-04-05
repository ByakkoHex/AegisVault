"""
db_manager.py - Operacje na bazie danych dla Password Managera
"""

import json
import base64
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.orm import sessionmaker
from database.models import User, Password, PasswordHistory, CustomCategory, init_db, DEFAULT_CATEGORIES
from core.crypto import (
    hash_master_password, verify_master_password,
    generate_salt, CryptoManager
)

HISTORY_LIMIT = 10   # maks. wersji historii na wpis
TRASH_DAYS    = 30   # dni w koszu przed auto-usunięciem


class DatabaseManager:
    def __init__(self, db_path: str = "password_manager.db"):
        self.db_path = db_path
        engine = init_db(db_path)
        Session = sessionmaker(bind=engine)
        self.session = Session()

    # ──────────────────────────────────────────────
    # UŻYTKOWNICY
    # ──────────────────────────────────────────────

    def register_user(self, username: str, master_password: str) -> User | None:
        if self.session.query(User).filter_by(username=username).first():
            return None
        salt = generate_salt()
        user = User(
            username=username,
            master_password_hash=hash_master_password(master_password),
            salt=salt
        )
        self.session.add(user)
        self.session.commit()
        return user

    def get_user(self, username: str) -> User | None:
        return self.session.query(User).filter_by(username=username).first()

    def login_user(self, username: str, master_password: str) -> User | None:
        user = self.session.query(User).filter_by(username=username).first()
        if not user or not verify_master_password(master_password, user.master_password_hash):
            return None
        return user

    def set_totp_secret(self, user: User, secret: str) -> None:
        user.totp_secret = secret
        self.session.commit()

    # ──────────────────────────────────────────────
    # HASŁA — ODCZYT (tylko aktywne, poza koszem)
    # ──────────────────────────────────────────────

    def get_all_passwords(self, user) -> list[Password]:
        return (self.session.query(Password)
                .filter_by(user_id=user.id, is_deleted=0).all())

    def get_passwords_by_category(self, user, category: str) -> list[Password]:
        if category == "Wszystkie":
            return self.get_all_passwords(user)
        if category == "Wygasające":
            return self.get_expiring_passwords(user)
        return (self.session.query(Password)
                .filter_by(user_id=user.id, category=category, is_deleted=0).all())

    def search_passwords(self, user, query: str, category: str = "Wszystkie") -> list[Password]:
        q = (self.session.query(Password)
             .filter(
                 Password.user_id == user.id,
                 Password.is_deleted == 0,
                 Password.title.ilike(f"%{query}%") | Password.url.ilike(f"%{query}%")
             ))
        if category not in ("Wszystkie", "Wygasające"):
            q = q.filter(Password.category == category)
        return q.all()

    def get_password_by_id(self, password_id: int, user) -> Password | None:
        return (self.session.query(Password)
                .filter_by(id=password_id, user_id=user.id, is_deleted=0).first())

    def get_expiring_passwords(self, user) -> list[Password]:
        """Hasła wygasłe lub wygasające w ciągu 7 dni."""
        threshold = datetime.now(timezone.utc) + timedelta(days=7)
        return (self.session.query(Password)
                .filter(
                    Password.user_id == user.id,
                    Password.is_deleted == 0,
                    Password.expires_at != None,
                    Password.expires_at <= threshold,
                ).all())

    def toggle_favorite(self, entry) -> bool:
        """Przełącza status ulubionego. Zwraca nowy stan (True = ulubione)."""
        new_val = 0 if getattr(entry, "is_favorite", 0) else 1
        entry.is_favorite = new_val
        self.session.commit()
        return bool(new_val)

    def mark_used(self, entry) -> None:
        """Aktualizuje last_used_at (przy kopiowaniu hasła)."""
        entry.last_used_at = datetime.now(timezone.utc)
        self.session.commit()

    # ──────────────────────────────────────────────
    # HASŁA — ZAPIS / EDYCJA
    # ──────────────────────────────────────────────

    def add_password(self, user, crypto, title, username, plaintext_password,
                     url="", notes="", category="Inne", expires_at=None) -> Password:
        entry = Password(
            user_id=user.id,
            title=title,
            username=username,
            encrypted_password=crypto.encrypt(plaintext_password),
            url=url,
            notes=notes,
            category=category,
            expires_at=expires_at,
        )
        self.session.add(entry)
        self.session.commit()
        return entry

    def update_password(self, entry, crypto, title=None, username=None,
                        plaintext_password=None, url=None, notes=None,
                        category=None, expires_at=None) -> Password:
        # Zapisz historię przed zmianą hasła
        if plaintext_password is not None:
            self._save_history(entry)

        if title is not None:              entry.title = title
        if username is not None:           entry.username = username
        if plaintext_password is not None: entry.encrypted_password = crypto.encrypt(plaintext_password)
        if url is not None:                entry.url = url
        if notes is not None:              entry.notes = notes
        if category is not None:           entry.category = category
        if expires_at is not None:         entry.expires_at = expires_at
        entry.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        return entry

    def decrypt_password(self, entry, crypto) -> str:
        return crypto.decrypt(entry.encrypted_password)

    # ──────────────────────────────────────────────
    # HISTORIA HASEŁ
    # ──────────────────────────────────────────────

    def _save_history(self, entry: Password) -> None:
        """Zapisuje bieżące hasło do historii (maks. HISTORY_LIMIT wpisów)."""
        hist = PasswordHistory(
            password_id=entry.id,
            encrypted_password=entry.encrypted_password,
        )
        self.session.add(hist)

        # Usuń nadmiarowe (najstarsze) wpisy historii
        count = self.session.query(func.count(PasswordHistory.id)).filter_by(password_id=entry.id).scalar()
        if count >= HISTORY_LIMIT:
            oldest = (self.session.query(PasswordHistory.id)
                      .filter_by(password_id=entry.id)
                      .order_by(PasswordHistory.changed_at.asc())
                      .limit(count - HISTORY_LIMIT + 1)
                      .all())
            for (old_id,) in oldest:
                self.session.query(PasswordHistory).filter_by(id=old_id).delete()

    def get_history(self, entry: Password) -> list[PasswordHistory]:
        return (self.session.query(PasswordHistory)
                .filter_by(password_id=entry.id)
                .order_by(PasswordHistory.changed_at.desc())
                .all())

    def restore_from_history(self, entry: Password, hist: PasswordHistory) -> None:
        """Przywraca hasło z wybranego wpisu historii."""
        self._save_history(entry)
        entry.encrypted_password = hist.encrypted_password
        entry.updated_at = datetime.now(timezone.utc)
        self.session.commit()

    # ──────────────────────────────────────────────
    # KOSZ
    # ──────────────────────────────────────────────

    def trash_password(self, entry: Password) -> None:
        """Przenosi hasło do kosza (soft delete)."""
        entry.is_deleted = 1
        entry.deleted_at = datetime.now(timezone.utc)
        self.session.commit()

    def restore_password(self, entry: Password) -> None:
        """Przywraca hasło z kosza."""
        entry.is_deleted = 0
        entry.deleted_at = None
        self.session.commit()

    def delete_password(self, entry: Password) -> None:
        """Permanentnie usuwa hasło (używaj z kosza)."""
        self.session.delete(entry)
        self.session.commit()

    def get_trashed_passwords(self, user) -> list[Password]:
        return (self.session.query(Password)
                .filter_by(user_id=user.id, is_deleted=1)
                .order_by(Password.deleted_at.desc())
                .all())

    def purge_old_trash(self, user) -> int:
        """Trwale usuwa wpisy w koszu starsze niż TRASH_DAYS dni. Zwraca liczbę usuniętych."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=TRASH_DAYS)
        old = (self.session.query(Password)
               .filter(
                   Password.user_id == user.id,
                   Password.is_deleted == 1,
                   Password.deleted_at < cutoff,
               ).all())
        for entry in old:
            self.session.delete(entry)
        self.session.commit()
        return len(old)

    # ──────────────────────────────────────────────
    # WŁASNE KATEGORIE
    # ──────────────────────────────────────────────

    def get_all_categories(self, user) -> list[str]:
        """Zwraca domyślne + własne kategorie użytkownika."""
        custom = [c.name for c in
                  self.session.query(CustomCategory).filter_by(user_id=user.id).all()]
        return DEFAULT_CATEGORIES + custom

    def add_custom_category(self, user, name: str, color: str = "#718096",
                            icon: str = "🏷") -> CustomCategory | None:
        name = name.strip()
        if not name or name in DEFAULT_CATEGORIES:
            return None
        exists = (self.session.query(CustomCategory)
                  .filter_by(user_id=user.id, name=name).first())
        if exists:
            return None
        cat = CustomCategory(user_id=user.id, name=name, color=color, icon=icon)
        self.session.add(cat)
        self.session.commit()
        return cat

    def get_category_icons(self, user) -> dict[str, str]:
        """Zwraca mapę {nazwa: ikona} dla własnych kategorii użytkownika."""
        return {c.name: (c.icon or "🏷")
                for c in self.session.query(CustomCategory).filter_by(user_id=user.id).all()}

    def delete_custom_category(self, user, name: str) -> None:
        cat = (self.session.query(CustomCategory)
               .filter_by(user_id=user.id, name=name).first())
        if cat:
            # Przenieś hasła z tej kategorii do "Inne"
            (self.session.query(Password)
             .filter_by(user_id=user.id, category=name)
             .update({"category": "Inne"}))
            self.session.delete(cat)
            self.session.commit()

    def get_custom_category_color(self, user, name: str) -> str:
        cat = (self.session.query(CustomCategory)
               .filter_by(user_id=user.id, name=name).first())
        return cat.color if cat else "#718096"

    # ──────────────────────────────────────────────
    # EKSPORT / IMPORT
    # ──────────────────────────────────────────────

    def export_passwords(self, user, crypto: CryptoManager, filepath: str) -> int:
        entries = self.get_all_passwords(user)
        data = []
        for entry in entries:
            plaintext = self.decrypt_password(entry, crypto)
            data.append({
                "title":      entry.title,
                "username":   entry.username or "",
                "password":   plaintext,
                "url":        entry.url or "",
                "notes":      entry.notes or "",
                "category":   entry.category or "Inne",
                "expires_at": entry.expires_at.isoformat() if entry.expires_at else "",
                "created_at": entry.created_at.isoformat() if entry.created_at else "",
                "updated_at": entry.updated_at.isoformat() if entry.updated_at else "",
            })

        json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        encrypted  = crypto.encrypt(json_bytes.decode("utf-8"))
        export_obj = {
            "version":     "2.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "username":    user.username,
            "count":       len(data),
            "data":        base64.b64encode(encrypted).decode("utf-8"),
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(export_obj, f, ensure_ascii=False, indent=2)
        return len(data)

    def import_passwords(self, user, crypto: CryptoManager, filepath: str) -> tuple[int, int]:
        with open(filepath, "r", encoding="utf-8") as f:
            export_data = json.load(f)

        encrypted = base64.b64decode(export_data["data"])
        json_str  = crypto.decrypt(encrypted)
        entries   = json.loads(json_str)

        existing_titles = {e.title for e in self.get_all_passwords(user)}
        imported = skipped = 0

        for item in entries:
            if item["title"] in existing_titles:
                skipped += 1
                continue
            expires = None
            if item.get("expires_at"):
                try:
                    expires = datetime.fromisoformat(item["expires_at"])
                except ValueError:
                    pass
            self.add_password(
                user, crypto,
                title=item["title"],
                username=item.get("username", ""),
                plaintext_password=item["password"],
                url=item.get("url", ""),
                notes=item.get("notes", ""),
                category=item.get("category", "Inne"),
                expires_at=expires,
            )
            imported += 1

        return imported, skipped

    def close(self):
        self.session.close()
