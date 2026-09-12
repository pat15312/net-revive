import base64
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.exceptions import InvalidKey
from fastapi import HTTPException, Request


def hash_password(password):
    return Argon2id(
        salt=secrets.token_bytes(16), length=32, iterations=2, lanes=1, memory_cost=19456
    ).derive_phc_encoded(password.encode())


def verify_password(password, encoded):
    try:
        if encoded.startswith("$argon2id$"):
            # Only our bounded parameters are accepted, including for damaged databases.
            if not encoded.startswith("$argon2id$v=19$m=19456,t=2,p=1$"):
                return False
            Argon2id.verify_phc_encoded(password.encode(), encoded)
            return True
        # Backwards-compatible verification; a successful login upgrades this legacy hash.
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) != 80:
            return False
        value = hashlib.scrypt(password.encode(), salt=raw[:16], n=16384, r=8, p=1)
        return hmac.compare_digest(value, raw[16:])
    except (InvalidKey, ValueError, TypeError):
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


def insert_session(conn, admin=False):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    conn.execute("DELETE FROM sessions WHERE expires_at<?", (time.time(),))
    if conn.execute("SELECT count(*) FROM sessions").fetchone()[0] >= 1024:
        # Anonymous churn cannot fill the database indefinitely or evict administrator sessions.
        removed = conn.execute(
            "DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM sessions WHERE admin=0 ORDER BY expires_at LIMIT 1)"
        )
        if not removed.rowcount:
            raise HTTPException(429, "Session capacity reached. Please try again later.")
    conn.execute("INSERT INTO sessions VALUES (?,?,?,?)", (digest(token), csrf, admin, time.time() + 28800))
    return token, {"csrf": csrf, "admin": admin}


def new_session(db, admin=False):
    with db.connect(write=True) as conn:
        return insert_session(conn, admin)


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
