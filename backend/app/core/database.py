from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# pool_pre_ping checks a connection is still alive before handing it out,
# so a database restart does not surface as random errors in requests.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    # Make every connection talk in UTC, whatever the server's own timezone is.
    connect_args={"options": "-c timezone=utc"},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that gives each request its own session and always closes it."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
