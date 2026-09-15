from datetime import timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.timezones import now_utc

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def hash_password(plain_password: str) -> str:
    """Hash a password with bcrypt. A random salt is generated for every call."""
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a password against a stored bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_token(user_id: int, role: str, token_type: str, lifetime: timedelta) -> str:
    """Create a signed JWT for a user."""
    settings = get_settings()
    issued_at = now_utc()
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": token_type,
        "iat": issued_at,
        "exp": issued_at + lifetime,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, role: str) -> str:
    """Short-lived token sent with every API request."""
    minutes = get_settings().access_token_expire_minutes
    return create_token(user_id, role, ACCESS_TOKEN_TYPE, timedelta(minutes=minutes))


def create_refresh_token(user_id: int, role: str) -> str:
    """Long-lived token used only to get a new access token."""
    days = get_settings().refresh_token_expire_days
    return create_token(user_id, role, REFRESH_TOKEN_TYPE, timedelta(days=days))


def decode_token(token: str) -> dict[str, Any]:
    """Verify the signature and expiry of a token and return its payload.

    Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError on failure.
    """
    settings = get_settings()
    # Passing algorithms explicitly stops "alg: none" style token forgery.
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
