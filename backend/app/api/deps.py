from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.models import User
from app.models.enums import UserRole

# auto_error=False lets us return our own 401 body instead of FastAPI's default 403.
bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """Read the bearer token, verify it and load the logged-in user."""
    if credentials is None:
        raise AuthenticationError("NOT_AUTHENTICATED", "Please log in to continue.")

    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("TOKEN_EXPIRED", "Your session has expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise AuthenticationError("INVALID_TOKEN", "Invalid authentication token.")

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise AuthenticationError("INVALID_TOKEN", "Invalid authentication token.")

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("INVALID_TOKEN", "Invalid authentication token.")
    return user


def require_roles(*allowed_roles: UserRole) -> Callable[..., User]:
    """Build a dependency that only lets users with one of the given roles through.

    Usage:  current_user: User = Depends(require_roles(UserRole.ADMIN))
    """
    allowed_values = set()
    for role in allowed_roles:
        allowed_values.add(role.value)

    def check_role(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in allowed_values:
            raise PermissionDeniedError("FORBIDDEN", "You do not have permission to do this.")
        return current_user

    return check_role


CurrentUser = Annotated[User, Depends(get_current_user)]
PatientUser = Annotated[User, Depends(require_roles(UserRole.PATIENT))]
DoctorUser = Annotated[User, Depends(require_roles(UserRole.DOCTOR))]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
