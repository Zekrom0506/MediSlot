import os

# Point the app at the test database *before* anything from `app` is imported,
# because settings and the engine are created at import time.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/medislot_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("ENVIRONMENT", "test")

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

BACKEND_DIRECTORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TABLES_TO_CLEAN = [
    "notifications",
    "idempotency_keys",
    "bookings",
    "slots",
    "weekly_schedules",
    "doctors",
    "clinics",
    "users",
]


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    """Build the schema from scratch with the real Alembic migrations, once per test run."""
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))

    alembic_config = Config(os.path.join(BACKEND_DIRECTORY, "alembic.ini"))
    alembic_config.set_main_option("script_location", os.path.join(BACKEND_DIRECTORY, "alembic"))
    alembic_config.attributes["configure_logger"] = False
    command.upgrade(alembic_config, "head")
    yield


@pytest.fixture(autouse=True)
def clean_database() -> Iterator[None]:
    """Empty every table after each test so tests cannot affect each other."""
    yield
    with engine.begin() as connection:
        table_list = ", ".join(TABLES_TO_CLEAN)
        connection.execute(text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db() -> Iterator[Session]:
    """A database session for setting up and checking test data."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """HTTP client that calls the app in-process."""
    with TestClient(app) as test_client:
        yield test_client
