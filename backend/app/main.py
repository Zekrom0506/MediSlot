from fastapi import FastAPI

from app.api import health
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(health.router)


@app.get("/")
def root() -> dict[str, str]:
    """Simple welcome message so the root URL is not a 404."""
    return {"message": "Welcome to the MediSlot API"}
