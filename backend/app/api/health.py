import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DbSession
from app.core.errors import error_body
from app.core.redis_client import get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check: answers as long as the process is running."""
    return {"status": "ok"}


@router.get("/ready", response_model=None)
def ready(db: DbSession) -> dict[str, str] | JSONResponse:
    """Readiness check: can we actually reach Postgres and Redis?"""
    checks = {"database": "ok", "redis": "ok"}
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        checks["database"] = "unavailable"
    try:
        get_redis().ping()
    except redis.RedisError:
        checks["redis"] = "unavailable"

    for status in checks.values():
        if status != "ok":
            body = error_body("NOT_READY", "A required service is unavailable.")
            body["checks"] = checks
            return JSONResponse(status_code=503, content=body)
    return {"status": "ready", **checks}
