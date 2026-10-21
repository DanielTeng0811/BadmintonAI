"""Password and revocable session storage. No plaintext credentials are persisted."""
from __future__ import annotations

import hashlib
import hmac
from contextlib import contextmanager
from pathlib import Path
import re
import secrets
import sqlite3
import time

ADMIN = "admin"
DOMAIN = "local.badminton"
SESSION_SECONDS = 7 * 24 * 3600


class AuthError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def username(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{2,31}", value.strip().lower()):
        raise AuthError("帳號需為 3–32 個小寫英文字母、數字、底線或連字號，並以字母開頭。")
    return value.strip().lower()


def password_hash(password, salt=None):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise AuthError("密碼需為 12–128 個字元。")
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=1,
                            maxmem=128 * 1024 * 1024).hex()
    return f"scrypt${salt}${digest}"


def password_matches(password, encoded):
    try:
        _, salt, _ = encoded.split("$")
        return hmac.compare_digest(password_hash(password, salt), encoded)
    except (AuthError, ValueError, TypeError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin','user')),
                    disabled INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    digest TEXT PRIMARY KEY, username TEXT NOT NULL REFERENCES users(username),
                    expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS failures (
                    bucket TEXT PRIMARY KEY, attempts INTEGER NOT NULL, since REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gateway_tokens (
                    digest TEXT PRIMARY KEY, username TEXT NOT NULL, expires REAL NOT NULL
                );
            """)
        self.path.chmod(0o600)
        self.dummy_hash = password_hash(secrets.token_urlsafe(24))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def setup_required(self):
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0

    def create(self, name, password, *, bootstrap=False):
        name = username(name)
        encoded = password_hash(password)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            empty = db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            if bootstrap:
                if not empty:
                    raise AuthError("管理員已建立，請登入。", 409)
                if name != ADMIN:
                    raise AuthError("初次管理員帳號固定為 admin。")
            elif empty:
                raise AuthError("請先建立管理員帳號。", 409)
            elif name == ADMIN:
                raise AuthError("此帳號不可用。", 409)
            try:
                db.execute("INSERT INTO users VALUES (?,?,?,0,?)", (
                    name, encoded, "admin" if bootstrap else "user", time.time()))
            except sqlite3.IntegrityError:
                raise AuthError("此帳號不可用。", 409) from None
        return name

    def limited(self, buckets, limit=10, window=600):
        now = time.time()
        with self.connect() as db:
            for bucket in buckets:
                row = db.execute("SELECT attempts,since FROM failures WHERE bucket=?", (token_hash(bucket),)).fetchone()
                if row and row["since"] > now - window and row["attempts"] >= limit:
                    raise AuthError("嘗試次數過多，請稍後再試。", 429)

    def failure(self, buckets):
        now = time.time()
        with self.connect() as db:
            for bucket in buckets:
                key = token_hash(bucket)
                row = db.execute("SELECT attempts,since FROM failures WHERE bucket=?", (key,)).fetchone()
                count, since = (row["attempts"] + 1, row["since"]) if row and row["since"] > now - 600 else (1, now)
                db.execute("INSERT OR REPLACE INTO failures VALUES (?,?,?)", (key, count, since))
            db.execute("DELETE FROM failures WHERE since<?", (now - 3600,))

    def login(self, name, password):
        name = username(name)
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE username=?", (name,)).fetchone()
        valid = password_matches(password, row["password_hash"] if row else self.dummy_hash)
        if not valid or not row or row["disabled"]:
            raise AuthError("帳號或密碼不正確。", 401)
        return self.issue(name, expected_hash=row["password_hash"])

    def issue(self, name, expected_hash=None):
        token = secrets.token_urlsafe(48)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT password_hash FROM users WHERE username=? AND disabled=0", (name,)).fetchone()
            if row is None or expected_hash is not None and row[0] != expected_hash:
                raise AuthError("帳號或密碼不正確。", 401)
            db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES (?,?,?)", (token_hash(token), name, time.time() + SESSION_SECONDS))
        return token

    def identity(self, token):
        if not token or len(token) > 200:
            return None
        with self.connect() as db:
            row = db.execute("SELECT u.username,u.role,s.expires FROM sessions s JOIN users u USING(username) "
                             "WHERE s.digest=? AND s.expires>? AND u.disabled=0", (token_hash(token), time.time())).fetchone()
        return dict(row) if row else None

    def revoke(self, token):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE digest=?", (token_hash(token),))

    def change_password(self, name, old, new):
        with self.connect() as db:
            row = db.execute("SELECT password_hash FROM users WHERE username=? AND disabled=0", (name,)).fetchone()
        if not row or not password_matches(old, row[0]):
            raise AuthError("目前密碼不正確。", 401)
        encoded = password_hash(new)
        with self.connect() as db:
            db.execute("UPDATE users SET password_hash=? WHERE username=?", (encoded, name))
            db.execute("DELETE FROM sessions WHERE username=?", (name,))
            db.execute("DELETE FROM gateway_tokens WHERE username=?", (name,))

    def users(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT username,role,disabled FROM users ORDER BY created")]

    def reset_password(self, name, new):
        """Privileged local-console recovery; deliberately not exposed as an HTTP endpoint."""
        name, encoded = username(name), password_hash(new)
        with self.connect() as db:
            cur = db.execute("UPDATE users SET password_hash=? WHERE username=?", (encoded, name))
            if not cur.rowcount:
                raise AuthError("找不到帳號。", 404)
            db.execute("DELETE FROM sessions WHERE username=?", (name,))
            db.execute("DELETE FROM gateway_tokens WHERE username=?", (name,))

    def disable(self, name, disabled):
        name = username(name)
        if name == ADMIN:
            raise AuthError("不可停用唯一管理員。")
        with self.connect() as db:
            cur = db.execute("UPDATE users SET disabled=? WHERE username=?", (int(disabled), name))
            if not cur.rowcount:
                raise AuthError("找不到帳號。", 404)
            db.execute("DELETE FROM sessions WHERE username=?", (name,))
            db.execute("DELETE FROM gateway_tokens WHERE username=?", (name,))

    def grant_gateway_token(self, token, name, ttl):
        with self.connect() as db:
            db.execute("DELETE FROM gateway_tokens WHERE expires<?", (time.time(),))
            db.execute("INSERT OR REPLACE INTO gateway_tokens VALUES (?,?,?)", (token_hash(token), name, time.time() + min(ttl, 600)))

    def owns_gateway_token(self, token, name):
        with self.connect() as db:
            row = db.execute("SELECT username FROM gateway_tokens WHERE digest=? AND expires>?", (token_hash(token), time.time())).fetchone()
        return row is not None and row[0] == name
