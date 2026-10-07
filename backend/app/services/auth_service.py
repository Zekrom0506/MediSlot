import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, ConflictError
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.models.enums import UserRole
from app.schemas.auth import RegisterRequest, TokenResponse
from app.schemas.user import UserResponse

# Used when the email does not exist, so a failed login takes the same time
# either way and does not reveal which emails are registered.
DUMMY_PASSWORD_HASH = hash_password("not-a-real-password")


def find_user_by_email(db: Session, email: str) -> User | None:
    """Look up a user by email (emails are stored lowercase)."""
    return db.scalar(select(User).where(User.email == email.lower()))


def register_patient(db: Session, request: RegisterRequest) -> User:
    """Create a new patient account. Doctors and admins are created by admins only."""
    # Hash first, so no database connection is held during the slow bcrypt call.
    hashed_password = hash_password(request.password)
    if find_user_by_email(db, request.email) is not None:
        raise ConflictError("EMAIL_ALREADY_REGISTERED", "An account with this email already exists.")

    user = User(
        full_name=request.full_name.strip(),
        email=request.email.lower(),
        hashed_password=hashed_password,
        role=UserRole.PATIENT.value,
        phone_number=request.phone_number,
    )
    db.add(user)
    db.commit()
    return user


def issue_tokens(user: User) -> TokenResponse:
    """Create a fresh access and refresh token pair for a user."""
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id, user.role),
        user=UserResponse.model_validate(user),
    )


def login(db: Session, email: str, password: str) -> TokenResponse:
    """Check credentials and return tokens."""
    user = find_user_by_email(db, email)
    # Give the database connection back before the slow bcrypt check (~0.25s of CPU).
    # Holding it would let a burst of logins use up the whole connection pool.
    db.commit()
    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)
        raise AuthenticationError("INVALID_CREDENTIALS", "Incorrect email or password.")
    if not verify_password(password, user.hashed_password):
        raise AuthenticationError("INVALID_CREDENTIALS", "Incorrect email or password.")
    if not user.is_active:
        raise AuthenticationError("ACCOUNT_DISABLED", "This account has been deactivated.")
    return issue_tokens(user)


def refresh_tokens(db: Session, refresh_token: str) -> TokenResponse:
    """Exchange a valid refresh token for a new token pair."""
    try:
        payload = decode_token(refresh_token)
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("TOKEN_EXPIRED", "Your session has expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise AuthenticationError("INVALID_TOKEN", "Invalid refresh token.")

    # An access token must not be usable as a refresh token, and vice versa.
    if payload.get("type") != REFRESH_TOKEN_TYPE:
        raise AuthenticationError("INVALID_TOKEN", "Invalid refresh token.")

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("INVALID_TOKEN", "Invalid refresh token.")
    return issue_tokens(user)
