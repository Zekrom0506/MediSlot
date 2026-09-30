import os
import socket
import threading
import time

# Point the app at the test database *before* anything from `app` is imported,
# because settings and the engine are created at import time.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/medislot_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("ENVIRONMENT", "test")

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
import uvicorn  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.redis_client import get_redis  # noqa: E402
from app.main import app  # noqa: E402
from app.services import notification_service  # noqa: E402

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
    """Empty every table and the test Redis database after each test."""
    get_redis().flushdb()
    yield
    with engine.begin() as connection:
        table_list = ", ".join(TABLES_TO_CLEAN)
        connection.execute(text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def queued_notifications(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Capture notification ids instead of sending them to a real Celery broker."""
    queued_ids: list[int] = []
    monkeypatch.setattr(notification_service, "enqueue_notification", queued_ids.append)
    return queued_ids


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


@pytest.fixture
def live_server_url() -> Iterator[str]:
    """Run the real app in uvicorn on a free port, for tests that need true parallel requests."""
    listening_socket = socket.socket()
    listening_socket.bind(("127.0.0.1", 0))
    port = listening_socket.getsockname()[1]
    listening_socket.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    waited_seconds = 0.0
    while not server.started:
        time.sleep(0.05)
        waited_seconds += 0.05
        if waited_seconds > 10:
            raise RuntimeError("Test server did not start")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    server_thread.join(timeout=10)
