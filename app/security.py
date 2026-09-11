import base64
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi import HTTPException, Request


def hash_password(password):
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return base64.b64encode(salt + value).decode()


def verify_password(password, encoded):
    try:
        raw = base64.b64decode(encoded)
        value = hashlib.scrypt(password.encode(), salt=raw[:16], n=16384, r=8, p=1)
        return hmac.compare_digest(value, raw[16:])
    except (ValueError, TypeError):
        return False


def cipher_for(bootstrap):
    secret = bootstrap.secret_key
    if not secret:
        path = Path(bootstrap.database_path).parent / "secret.key"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            secret = path.read_text().strip()
        else:
            secret = secrets.token_urlsafe(48)
            with os.fdopen(fd, "w") as handle:
                handle.write(secret)
    if len(secret) < 32:
        raise RuntimeError("SECRET_KEY must contain at least 32 characters.")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(db, admin=False):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with db.connect(write=True) as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at<?", (time.time(),))
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?)", (digest(token), csrf, admin, time.time() + 28800)
        )
    return token, {"csrf": csrf, "admin": admin}


def require_admin(request: Request):
    if not request.state.session["admin"]:
        raise HTTPException(401, "Administrator sign-in required.")


def rate_limit(db, key, maximum=30, window=60):
    now = time.time()
    with db.connect(write=True) as conn:
        conn.execute("DELETE FROM rate_limits WHERE start<?", (now - 3600,))
        row = conn.execute("SELECT * FROM rate_limits WHERE key=?", (key,)).fetchone()
        if row and row["start"] > now - window:
            if row["count"] >= maximum:
                raise HTTPException(429, "Too many attempts. Please wait before trying again.")
            conn.execute("UPDATE rate_limits SET count=count+1 WHERE key=?", (key,))
        else:
            conn.execute("INSERT OR REPLACE INTO rate_limits VALUES (?,?,1)", (key, now))
