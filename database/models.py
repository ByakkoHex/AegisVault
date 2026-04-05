"""
models.py - Modele bazy danych dla Password Managera
=====================================================
Tabele:
  users            — konta użytkowników
  passwords        — hasła (z koszem + datą ważności)
  password_history — historia zmian haseł (ostatnie 10)
  custom_categories — własne kategorie użytkownika
"""

from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, String,
    LargeBinary, ForeignKey, DateTime, Text, Index, event
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

DEFAULT_CATEGORIES = ["Social Media", "Praca", "Bankowość", "Rozrywka", "Inne"]
CATEGORIES = ["Wszystkie"] + DEFAULT_CATEGORIES  # widok listy


class User(Base):
    __tablename__ = "users"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    username             = Column(String(64), unique=True, nullable=False)
    master_password_hash = Column(LargeBinary, nullable=False)
    salt                 = Column(LargeBinary, nullable=False)
    totp_secret                = Column(String(32), nullable=True)
    kdf_version                = Column(Integer, default=0, nullable=False, server_default="0")
    recovery_salt              = Column(LargeBinary, nullable=True)   # sól do Argon2id recovery
    recovery_encrypted_master  = Column(LargeBinary, nullable=True)   # masterhasło zaszyfrowane kluczem recovery
    created_at                 = Column(DateTime, default=datetime.utcnow)

    passwords         = relationship("Password", back_populates="user", cascade="all, delete-orphan")
    custom_categories = relationship("CustomCategory", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User id={self.id} username={self.username}>"


class Password(Base):
    __tablename__ = "passwords"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    user_id            = Column(Integer, ForeignKey("users.id"), nullable=False)
    title              = Column(String(128), nullable=False)
    username           = Column(String(128), nullable=True)
    encrypted_password = Column(LargeBinary, nullable=False)
    url                = Column(String(256), nullable=True)
    notes              = Column(Text, nullable=True)
    category           = Column(String(64), nullable=True, default="Inne")
    expires_at         = Column(DateTime, nullable=True)       # data ważności
    is_deleted         = Column(Integer, default=0)            # 0=aktywne, 1=kosz
    deleted_at         = Column(DateTime, nullable=True)       # kiedy przeniesiono do kosza
    is_favorite        = Column(Integer, default=0)            # 0=normalne, 1=ulubione
    last_used_at       = Column(DateTime, nullable=True)       # kiedy ostatnio skopiowano
    otp_secret         = Column(String(256), nullable=True)    # Base32 sekret TOTP (opcjonalny)
    created_at         = Column(DateTime, default=datetime.utcnow)
    updated_at         = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user    = relationship("User", back_populates="passwords")
    history = relationship("PasswordHistory", back_populates="password",
                           cascade="all, delete-orphan", order_by="PasswordHistory.changed_at.desc()")

    __table_args__ = (
        Index("ix_pwd_user_cat",     "user_id", "is_deleted", "category"),
        Index("ix_pwd_user_expiry",  "user_id", "is_deleted", "expires_at"),
        Index("ix_pwd_user_deleted", "user_id", "is_deleted", "deleted_at"),
    )

    @property
    def expiry_status(self) -> str:
        """Zwraca 'expired', 'soon' (≤7 dni), 'ok', lub None."""
        if not self.expires_at:
            return None
        delta = (self.expires_at - datetime.now(timezone.utc)).days
        if delta < 0:
            return "expired"
        if delta <= 7:
            return "soon"
        return "ok"

    def __repr__(self):
        return f"<Password id={self.id} title={self.title}>"


class PasswordHistory(Base):
    """Archiwum poprzednich wersji hasła (maks. 10 na wpis)."""
    __tablename__ = "password_history"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    password_id        = Column(Integer, ForeignKey("passwords.id"), nullable=False)
    encrypted_password = Column(LargeBinary, nullable=False)
    changed_at         = Column(DateTime, default=datetime.utcnow)

    password = relationship("Password", back_populates="history")


class CustomCategory(Base):
    """Własne kategorie tworzone przez użytkownika."""
    __tablename__ = "custom_categories"

    id      = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name    = Column(String(64), nullable=False)
    color   = Column(String(7), default="#718096")   # hex kolor
    icon    = Column(String(8), default="🏷")        # emoji ikona

    user = relationship("User", back_populates="custom_categories")

    __table_args__ = (
        Index("ix_customcat_user_name", "user_id", "name"),
    )


def init_db(db_path: str = "password_manager.db") -> object:
    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-32000")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    Base.metadata.create_all(engine)

    # Migracje dla istniejących baz danych
    from sqlalchemy import text, inspect
    with engine.connect() as conn:
        inspector = inspect(engine)
        pw_cols = [c["name"] for c in inspector.get_columns("passwords")]

        migrations = {
            "category":    "ALTER TABLE passwords ADD COLUMN category VARCHAR(64) DEFAULT 'Inne'",
            "expires_at":  "ALTER TABLE passwords ADD COLUMN expires_at DATETIME",
            "is_deleted":  "ALTER TABLE passwords ADD COLUMN is_deleted INTEGER DEFAULT 0",
            "deleted_at":  "ALTER TABLE passwords ADD COLUMN deleted_at DATETIME",
            "is_favorite":  "ALTER TABLE passwords ADD COLUMN is_favorite INTEGER DEFAULT 0",
            "last_used_at": "ALTER TABLE passwords ADD COLUMN last_used_at DATETIME",
        }
        for col, sql in migrations.items():
            if col not in pw_cols:
                conn.execute(text(sql))

        # Migracja passwords.otp_secret (TOTP w wpisach)
        if "otp_secret" not in pw_cols:
            conn.execute(text("ALTER TABLE passwords ADD COLUMN otp_secret VARCHAR(256)"))

        # Migracja users.kdf_version (Argon2id)
        user_cols = [c["name"] for c in inspector.get_columns("users")]
        if "kdf_version" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN kdf_version INTEGER NOT NULL DEFAULT 0"))

        # Migracja users — klucz recovery
        if "recovery_salt" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN recovery_salt BLOB"))
        if "recovery_encrypted_master" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN recovery_encrypted_master BLOB"))

        # Migracja custom_categories.icon
        cc_cols = [c["name"] for c in inspector.get_columns("custom_categories")]
        if "icon" not in cc_cols:
            conn.execute(text("ALTER TABLE custom_categories ADD COLUMN icon VARCHAR(8) DEFAULT '🏷'"))

        # Indeksy przyspieszające zapytania
        existing_indexes = [i["name"] for i in inspector.get_indexes("passwords")]
        if "ix_pwd_user_cat" not in existing_indexes:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_pwd_user_cat "
                "ON passwords (user_id, is_deleted, category)"
            ))
        if "ix_pwd_user_expiry" not in existing_indexes:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_pwd_user_expiry "
                "ON passwords (user_id, is_deleted, expires_at)"
            ))
        if "ix_pwd_user_deleted" not in existing_indexes:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_pwd_user_deleted "
                "ON passwords (user_id, is_deleted, deleted_at)"
            ))

        cc_indexes = [i["name"] for i in inspector.get_indexes("custom_categories")]
        if "ix_customcat_user_name" not in cc_indexes:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_customcat_user_name "
                "ON custom_categories (user_id, name)"
            ))

        conn.commit()

    return engine
