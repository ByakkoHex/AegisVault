"""
main.py - Serwer synchronizacji FastAPI
========================================
Uruchomienie: py -m uvicorn server.main:app --reload --port 8000
Dokumentacja API: http://localhost:8000/docs

Endpointy:
  POST /register     - rejestracja konta serwera
  POST /login        - logowanie, zwraca JWT token
  POST /sync/push    - wysyłanie haseł na serwer
  GET  /sync/pull    - pobieranie haseł z serwera
  POST /sync/delete  - oznaczenie hasła jako usuniętego
  GET  /health       - status serwera
"""

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional
import secrets
import json
import os
from server.models import init_db, ServerUser, ServerPassword, PushChallenge, PUSH_TTL_SECONDS
from server.auth import hash_password, verify_password, create_token, decode_token

app = FastAPI(title="AegisVault Sync Server", version="1.0.0")
db = init_db()


# ──────────────────────────────────────────────
# MODELE REQUESTÓW
# ──────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class PasswordEntry(BaseModel):
    client_id:      str       # UUID generowany przez klienta
    title:          str
    encrypted_blob: str       # zaszyfrowane dane (base64) — serwer tego nie odczytuje
    category:       Optional[str] = "Inne"
    updated_at:     Optional[str] = None

class PushRequest(BaseModel):
    entries: list[PasswordEntry]

class DeleteRequest(BaseModel):
    client_ids: list[str]


# ──────────────────────────────────────────────
# AUTORYZACJA
# ──────────────────────────────────────────────

def get_current_user(authorization: str = Header(...)) -> str:
    """Weryfikuje JWT token z nagłówka Authorization: Bearer <token>"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Nieprawidłowy format tokenu")
    token = authorization[7:]
    username = decode_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Token nieważny lub wygasł")
    return username


# ──────────────────────────────────────────────
# ENDPOINTY
# ──────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/version")
def get_version():
    """Zwraca aktualną wersję aplikacji dostępną na serwerze."""
    version_file = os.path.join(os.path.dirname(__file__), "app_version.json")
    try:
        with open(version_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": "1.0.0", "download_url": "", "changelog": ""}


@app.post("/register")
def register(req: RegisterRequest):
    if len(req.username) < 3:
        raise HTTPException(400, "Nazwa użytkownika musi mieć co najmniej 3 znaki")
    if len(req.password) < 8:
        raise HTTPException(400, "Hasło musi mieć co najmniej 8 znaków")

    existing = db.query(ServerUser).filter_by(username=req.username).first()
    if existing:
        raise HTTPException(400, "Użytkownik już istnieje")

    user = ServerUser(username=req.username, password_hash=hash_password(req.password))
    db.add(user)
    db.commit()
    return {"message": f"Konto '{req.username}' zostało utworzone"}


@app.post("/login")
def login(req: LoginRequest):
    user = db.query(ServerUser).filter_by(username=req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Nieprawidłowa nazwa użytkownika lub hasło")

    token = create_token(req.username)
    return {"token": token, "username": req.username}


@app.post("/sync/push")
def push(req: PushRequest, username: str = Depends(get_current_user)):
    """
    Przyjmuje listę zaszyfrowanych wpisów od klienta.
    Jeśli wpis z danym client_id już istnieje — aktualizuje go.
    Serwer NIE odczytuje encrypted_blob — tylko go przechowuje.
    Używa bulk lookup (1 zapytanie) zamiast N zapytań SELECT per wpis.
    """
    if not req.entries:
        return {"created": 0, "updated": 0}

    # Pobierz wszystkie istniejące client_id jednym zapytaniem
    incoming_ids = [e.client_id for e in req.entries]
    existing_rows = db.query(ServerPassword).filter(
        ServerPassword.username == username,
        ServerPassword.client_id.in_(incoming_ids),
    ).all()
    existing_map = {row.client_id: row for row in existing_rows}

    updated = 0
    created = 0

    for entry in req.entries:
        ts = datetime.utcnow()
        if entry.updated_at:
            try:
                ts = datetime.fromisoformat(entry.updated_at)
            except ValueError:
                pass

        existing = existing_map.get(entry.client_id)
        if existing:
            existing.title          = entry.title
            existing.encrypted_blob = entry.encrypted_blob
            existing.category       = entry.category
            existing.updated_at     = ts
            existing.deleted        = 0
            updated += 1
        else:
            db.add(ServerPassword(
                username=username,
                client_id=entry.client_id,
                title=entry.title,
                encrypted_blob=entry.encrypted_blob,
                category=entry.category,
                updated_at=ts
            ))
            created += 1

    db.commit()
    return {"created": created, "updated": updated}


@app.get("/sync/pull")
def pull(since: Optional[str] = None, username: str = Depends(get_current_user)):
    """
    Zwraca wszystkie aktywne wpisy użytkownika.
    Opcjonalnie filtruje po dacie (since=ISO timestamp) — tylko nowsze.
    """
    query = db.query(ServerPassword).filter_by(username=username, deleted=0)

    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            query = query.filter(ServerPassword.updated_at > since_dt)
        except ValueError:
            pass

    entries = query.all()
    return {
        "entries": [
            {
                "client_id":      e.client_id,
                "title":          e.title,
                "encrypted_blob": e.encrypted_blob,
                "category":       e.category,
                "updated_at":     e.updated_at.isoformat() if e.updated_at else None,
            }
            for e in entries
        ],
        "count": len(entries)
    }


@app.post("/sync/delete")
def delete(req: DeleteRequest, username: str = Depends(get_current_user)):
    """Oznacza wpisy jako usunięte (soft delete)."""
    count = 0
    for client_id in req.client_ids:
        entry = db.query(ServerPassword).filter_by(
            username=username, client_id=client_id
        ).first()
        if entry:
            entry.deleted = 1
            count += 1
    db.commit()
    return {"deleted": count}


# ──────────────────────────────────────────────
# PUSH-APPROVE 2FA
# ──────────────────────────────────────────────

class PushCreateRequest(BaseModel):
    username: str


@app.post("/auth/push/create")
def push_create(req: PushCreateRequest):
    """Tworzy jednorazowe wyzwanie push-approve dla podanego użytkownika."""
    # Wyczyść stare wygasłe wyzwania tego użytkownika
    db.query(PushChallenge).filter(
        PushChallenge.username == req.username,
        PushChallenge.expires_at < datetime.utcnow()
    ).delete()
    db.commit()

    token = secrets.token_urlsafe(32)
    challenge = PushChallenge(
        token=token,
        username=req.username,
        expires_at=datetime.utcnow() + timedelta(seconds=PUSH_TTL_SECONDS),
    )
    db.add(challenge)
    db.commit()
    return {"token": token, "expires_in": PUSH_TTL_SECONDS}


@app.get("/auth/push/{token}", response_class=HTMLResponse)
def push_page(token: str):
    """Strona HTML do zatwierdzenia logowania na telefonie."""
    challenge = db.query(PushChallenge).filter_by(token=token).first()
    if not challenge:
        return HTMLResponse(_push_html("???", token, 0, error="Nieznane żądanie."), status_code=404)
    if challenge.status != "pending":
        msg = "Zatwierdzono już wcześniej." if challenge.status == "approved" else "Odmówiono."
        return HTMLResponse(_push_html(challenge.username, token, 0, error=msg))
    if challenge.is_expired:
        return HTMLResponse(_push_html(challenge.username, token, 0, error="Żądanie wygasło."))

    remaining = max(0, int((challenge.expires_at - datetime.utcnow()).total_seconds()))
    return HTMLResponse(_push_html(challenge.username, token, remaining))


@app.post("/auth/push/{token}/approve")
def push_approve(token: str):
    challenge = db.query(PushChallenge).filter_by(token=token).first()
    if not challenge or challenge.is_expired:
        raise HTTPException(410, "Żądanie wygasło lub nie istnieje")
    if challenge.status != "pending":
        raise HTTPException(409, "Żądanie już zostało rozpatrzone")
    challenge.status = "approved"
    db.commit()
    return {"ok": True}


@app.post("/auth/push/{token}/deny")
def push_deny(token: str):
    challenge = db.query(PushChallenge).filter_by(token=token).first()
    if not challenge:
        raise HTTPException(404, "Nie znaleziono żądania")
    challenge.status = "denied"
    db.commit()
    return {"ok": True}


@app.get("/auth/push/{token}/status")
def push_status(token: str):
    challenge = db.query(PushChallenge).filter_by(token=token).first()
    if not challenge:
        return {"status": "expired"}
    if challenge.status == "pending" and challenge.is_expired:
        challenge.status = "expired"
        db.commit()
        return {"status": "expired"}
    return {"status": challenge.status}


def _push_html(username: str, token: str, remaining: int, error: str = "") -> str:
    if error:
        body = f"""
        <div class="icon">⚠️</div>
        <h1>Nie można przetworzyć</h1>
        <p class="sub">{error}</p>
        """
    else:
        body = f"""
        <div class="icon">🔐</div>
        <h1>AegisVault</h1>
        <p class="sub">Prośba o logowanie</p>
        <div class="username">{username}</div>
        <p class="info">Czy to Ty próbujesz się zalogować?</p>
        <button class="btn approve" onclick="respond('approve')">✓&nbsp; Zatwierdź logowanie</button>
        <button class="btn deny"   onclick="respond('deny')">✗&nbsp; Odmów</button>
        <div class="timer">Żądanie wygasa za <span id="t">{remaining}</span>s</div>
        <script>
          var t = {remaining};
          var iv = setInterval(function(){{
            t--;
            var el = document.getElementById('t');
            if (el) el.textContent = t;
            if (t <= 0) {{
              clearInterval(iv);
              document.body.innerHTML = '<div style="text-align:center;padding:60px;color:#888">⏰<br>Żądanie wygasło</div>';
            }}
          }}, 1000);
          function respond(action) {{
            clearInterval(iv);
            fetch('/auth/push/{token}/' + action, {{method: 'POST'}})
              .then(function() {{
                document.body.innerHTML = action === 'approve'
                  ? '<div style="text-align:center;padding:60px"><div style="font-size:64px">✅</div><h2 style="color:#4caf50">Zatwierdzono!</h2><p style="color:#888">Możesz zamknąć tę stronę.</p></div>'
                  : '<div style="text-align:center;padding:60px"><div style="font-size:64px">❌</div><h2 style="color:#e05252">Odmówiono</h2><p style="color:#888">Logowanie zostało zablokowane.</p></div>';
              }});
          }}
        </script>
        """
    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>AegisVault — Potwierdź logowanie</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          background:#1a1a1a;color:#e8e8e8;
          display:flex;align-items:center;justify-content:center;
          min-height:100vh;padding:20px}}
    .card{{background:#1e1e1e;border:1px solid #3a3a3a;border-radius:16px;
           padding:36px 24px;max-width:380px;width:100%;text-align:center}}
    .icon{{font-size:52px;margin-bottom:10px}}
    h1{{font-size:24px;font-weight:700;margin-bottom:4px}}
    .sub{{color:#888;font-size:14px;margin-bottom:20px}}
    .username{{background:#252525;border-radius:10px;padding:14px;
               margin-bottom:20px;font-size:20px;font-weight:700;color:#4F8EF7}}
    .info{{color:#aaa;font-size:13px;margin-bottom:22px}}
    .btn{{width:100%;padding:16px;border:none;border-radius:12px;
          font-size:16px;font-weight:700;cursor:pointer;margin-bottom:10px;
          transition:opacity .15s}}
    .btn:hover{{opacity:.85}}
    .approve{{background:#4F8EF7;color:#fff}}
    .deny{{background:#2a2a2a;color:#888;border:1px solid #3a3a3a}}
    .timer{{font-size:12px;color:#555;margin-top:14px}}
  </style>
</head>
<body><div class="card">{body}</div></body>
</html>"""
