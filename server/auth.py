"""
auth.py - Autoryzacja JWT dla serwera synchronizacji
=====================================================
"""

import os
from datetime import datetime, timedelta
from jose import JWTError, jwt
import bcrypt

# W produkcji ustaw zmienną środowiskową JWT_SECRET_KEY
# Generuj: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = os.environ.get(
    "JWT_SECRET_KEY",
    "zmien-mnie-na-losowy-string-w-produkcji-32-znaki!"
)
ALGORITHM  = "HS256"
TOKEN_EXPIRE_DAYS = 30


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(username: str) -> str:
    expire = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None
