"""
models.py - Modele bazy danych serwera synchronizacji
"""

import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, LargeBinary, DateTime, Text
from datetime import timedelta
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

# W kontenerze Docker ustaw DB_PATH na ścieżkę wewnątrz wolumenu, np. /data/server_data.db
_db_path = os.environ.get("DB_PATH", "server_data.db")
engine = create_engine(f"sqlite:///{_db_path}", echo=False)


class ServerUser(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    username   = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ServerPassword(Base):
    __tablename__ = "passwords"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    username           = Column(String(64), nullable=False)       # właściciel
    client_id          = Column(String(64), nullable=False)       # unikalny ID z klienta
    title              = Column(String(128), nullable=False)
    encrypted_blob     = Column(Text, nullable=False)             # cały zaszyfrowany wpis (base64)
    category           = Column(String(64), nullable=True)
    updated_at         = Column(DateTime, default=datetime.utcnow)
    deleted            = Column(Integer, default=0)               # soft delete: 0=aktywny, 1=usunięty


class PushChallenge(Base):
    """Jednorazowe wyzwanie do push-approve 2FA (ważne 2 minuty)."""
    __tablename__ = "push_challenges"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    token      = Column(String(64), unique=True, nullable=False)
    username   = Column(String(64), nullable=False)
    status     = Column(String(16), default="pending")  # pending / approved / denied
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at


PUSH_TTL_SECONDS = 120


def init_db():
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()
