from fastapi import FastAPI

from app.api import admin, auth, bookings, doctor_portal, doctors, health
from app.core.config import get_settings
from app.core.errors import register_error_handlers

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")
register_error_handlers(app)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(doctors.router)
app.include_router(doctor_portal.router)
app.include_router(bookings.router)
app.include_router(admin.router)


@app.get("/")
def root() -> dict[str, str]:
    """Simple welcome message so the root URL is not a 404."""
    return {"message": "Welcome to the MediSlot API"}
