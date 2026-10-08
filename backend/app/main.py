from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.api import admin, auth, bookings, doctor_portal, doctors, health
from app.core.concurrency import ConcurrencyLimitMiddleware
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging_config import setup_logging
from app.core.middleware import RequestContextMiddleware

settings = get_settings()
setup_logging(settings.log_level)

app = FastAPI(title=settings.app_name, version="1.0.0")
register_error_handlers(app)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    ConcurrencyLimitMiddleware,
    max_requests=settings.database_pool_size + settings.database_max_overflow,
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(doctors.router)
app.include_router(doctor_portal.router)
app.include_router(bookings.router)
app.include_router(admin.router)

Instrumentator(excluded_handlers=["/metrics", "/health", "/ready"]).instrument(app).expose(
    app, include_in_schema=False
)


@app.get("/")
def root() -> dict[str, str]:
    """Simple welcome message so the root URL is not a 404."""
    return {"message": "Welcome to the MediSlot API"}
