"""Authentication utilities — JWT tokens, password hashing, admin seeding."""

import hashlib
import base64
import os
import secrets
import logging
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

_admin_username: str = ""
_admin_password_hash: str = ""


def init_admin(username: str, password: str | None = None) -> str:
    global _admin_username, _admin_password_hash
    _admin_username = username
    if password:
        _admin_password_hash = hash_password(password)
        return password
    generated = generate_password()
    _admin_password_hash = hash_password(generated)
    return generated


def generate_password(length: int = 24) -> str:
    return secrets.token_urlsafe(length)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
    return "pbkdf2_sha256$" + base64.b64encode(salt + key).decode()


def verify_password(plain: str, hashed: str) -> bool:
    parts = hashed.split("$", 1)
    if len(parts) != 2:
        return False
    data = base64.b64decode(parts[1].encode())
    salt = data[:16]
    key = data[16:]
    new_key = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, 100000)
    return key == new_key


def verify_admin(username: str, password: str) -> bool:
    if username != _admin_username:
        return False
    if not _admin_password_hash:
        return False
    return verify_password(password, _admin_password_hash)


def create_access_token(*, data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload
    except JWTError:
        return None


def get_admin_info() -> dict:
    return {"username": _admin_username, "role": "admin"}
