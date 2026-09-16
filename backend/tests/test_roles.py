import pytest

from app.api.deps import require_roles
from app.core.errors import PermissionDeniedError
from app.models import User
from app.models.enums import UserRole


def build_user(role: UserRole) -> User:
    return User(id=1, full_name="Someone", email="someone@example.com", hashed_password="x", role=role.value)


def test_require_roles_allows_matching_role() -> None:
    check_admin = require_roles(UserRole.ADMIN)
    admin = build_user(UserRole.ADMIN)
    assert check_admin(current_user=admin) is admin


def test_require_roles_accepts_any_of_several_roles() -> None:
    check_staff = require_roles(UserRole.ADMIN, UserRole.DOCTOR)
    doctor = build_user(UserRole.DOCTOR)
    assert check_staff(current_user=doctor) is doctor


def test_require_roles_rejects_other_roles() -> None:
    check_admin = require_roles(UserRole.ADMIN)
    with pytest.raises(PermissionDeniedError):
        check_admin(current_user=build_user(UserRole.PATIENT))
