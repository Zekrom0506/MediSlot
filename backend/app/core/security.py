import bcrypt


def hash_password(plain_password: str) -> str:
    """Hash a password with bcrypt. A random salt is generated for every call."""
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a password against a stored bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
