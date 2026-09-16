from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import ACCESS_TOKEN_TYPE, create_refresh_token, create_token
from app.models import User
from app.models.enums import UserRole
from tests.factories import TEST_PASSWORD, auth_headers, make_user


def register_payload(email: str = "asha@example.com") -> dict[str, str]:
    return {
        "full_name": "Asha Verma",
        "email": email,
        "password": "StrongPass1",
        "phone_number": "+91 98765 43210",
    }


def test_register_creates_patient_and_returns_tokens(client: TestClient, db: Session) -> None:
    response = client.post("/api/auth/register", json=register_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["role"] == "patient"
    assert body["user"]["phone_number"] == "+919876543210"
    assert "hashed_password" not in body["user"]

    stored_user = db.query(User).filter_by(email="asha@example.com").one()
    assert stored_user.hashed_password != "StrongPass1"


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    client.post("/api/auth/register", json=register_payload())
    response = client.post("/api/auth/register", json=register_payload("ASHA@example.com"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_register_validates_email_and_phone(client: TestClient) -> None:
    bad_email = register_payload("not-an-email")
    response = client.post("/api/auth/register", json=bad_email)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["message"].startswith("email")

    bad_phone = register_payload()
    bad_phone["phone_number"] = "12ab"
    response = client.post("/api/auth/register", json=bad_phone)
    assert response.status_code == 422
    assert "phone_number" in response.json()["error"]["message"]


def test_register_rejects_short_password(client: TestClient) -> None:
    payload = register_payload()
    payload["password"] = "short"
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 422


def test_login_success(client: TestClient, db: Session) -> None:
    make_user(db, email="ravi@example.com")
    response = client.post("/api/auth/login", json={"email": "ravi@example.com", "password": TEST_PASSWORD})

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "ravi@example.com"


def test_login_wrong_password_and_unknown_email_look_the_same(client: TestClient, db: Session) -> None:
    make_user(db, email="ravi@example.com")
    wrong_password = client.post("/api/auth/login", json={"email": "ravi@example.com", "password": "nope"})
    unknown_email = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "nope"})

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_login_rejects_deactivated_account(client: TestClient, db: Session) -> None:
    user = make_user(db, email="ravi@example.com")
    user.is_active = False
    db.commit()

    response = client.post("/api/auth/login", json={"email": "ravi@example.com", "password": TEST_PASSWORD})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ACCOUNT_DISABLED"


def test_me_requires_login(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


def test_me_returns_current_user(client: TestClient, db: Session) -> None:
    user = make_user(db, full_name="Ravi Kumar")
    response = client.get("/api/auth/me", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json()["full_name"] == "Ravi Kumar"


def test_expired_token_is_rejected(client: TestClient, db: Session) -> None:
    user = make_user(db)
    expired = create_token(user.id, user.role, ACCESS_TOKEN_TYPE, timedelta(minutes=-1))

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_garbage_token_is_rejected(client: TestClient) -> None:
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_refresh_token_cannot_be_used_as_access_token(client: TestClient, db: Session) -> None:
    user = make_user(db)
    refresh_token = create_refresh_token(user.id, user.role)
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
    assert response.status_code == 401


def test_refresh_returns_new_tokens(client: TestClient, db: Session) -> None:
    user = make_user(db)
    refresh_token = create_refresh_token(user.id, user.role)

    response = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_refresh_rejects_access_token(client: TestClient, db: Session) -> None:
    user = make_user(db)
    access_token = auth_headers(user)["Authorization"].split(" ")[1]

    response = client.post("/api/auth/refresh", json={"refresh_token": access_token})
    assert response.status_code == 401


def test_refresh_rejects_expired_and_invalid_tokens(client: TestClient, db: Session) -> None:
    user = make_user(db, role=UserRole.DOCTOR)
    expired = create_token(user.id, user.role, "refresh", timedelta(seconds=-5))

    expired_response = client.post("/api/auth/refresh", json={"refresh_token": expired})
    assert expired_response.json()["error"]["code"] == "TOKEN_EXPIRED"

    invalid_response = client.post("/api/auth/refresh", json={"refresh_token": "abc"})
    assert invalid_response.json()["error"]["code"] == "INVALID_TOKEN"
