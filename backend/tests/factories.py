"""Small helpers to create test data directly in the database."""

from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models import User
from app.models.enums import UserRole

TEST_PASSWORD = "Password123!"
# Hashed once: bcrypt is deliberately slow and tests create many users.
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


def make_user(
    db: Session,
    role: UserRole = UserRole.PATIENT,
    email: str | None = None,
    full_name: str = "Test User",
) -> User:
    """Create and commit a user with the shared test password."""
    if email is None:
        count = db.query(User).count()
        email = f"{role.value}{count + 1}@example.com"
    user = User(
        full_name=full_name,
        email=email,
        hashed_password=TEST_PASSWORD_HASH,
        role=role.value,
        phone_number="+919876543210",
    )
    db.add(user)
    db.commit()
    return user


def auth_headers(user: User) -> dict[str, str]:
    """Authorization header with a valid access token for the user."""
    token = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}
