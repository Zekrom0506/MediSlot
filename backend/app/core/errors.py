import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """An expected error that should be shown to the user in the standard JSON shape."""

    status_code = 400

    def __init__(self, code: str, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.headers = headers


class BusinessRuleError(AppError):
    status_code = 400


class AuthenticationError(AppError):
    status_code = 401


class PermissionDeniedError(AppError):
    status_code = 403


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class RateLimitExceededError(AppError):
    status_code = 429


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    """Build the one error shape every endpoint returns."""
    return {"error": {"code": code, "message": message}}


async def handle_app_error(request: Request, error: AppError) -> JSONResponse:
    """Turn an AppError into a JSON response."""
    return JSONResponse(
        status_code=error.status_code,
        content=error_body(error.code, error.message),
        headers=error.headers,
    )


async def handle_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    """Report the first invalid field in a readable way."""
    first_error = error.errors()[0]
    location_parts = []
    for part in first_error.get("loc", []):
        if part not in ("body", "query", "path", "header"):
            location_parts.append(str(part))
    field_name = ".".join(location_parts)
    message = first_error.get("msg", "Invalid input")
    if field_name:
        message = f"{field_name}: {message}"
    return JSONResponse(status_code=422, content=error_body("VALIDATION_ERROR", message))


async def handle_http_exception(request: Request, error: StarletteHTTPException) -> JSONResponse:
    """Wrap framework errors (unknown route, wrong method) in the standard shape."""
    if error.status_code == 404:
        code = "NOT_FOUND"
    elif error.status_code == 405:
        code = "METHOD_NOT_ALLOWED"
    else:
        code = "HTTP_ERROR"
    return JSONResponse(status_code=error.status_code, content=error_body(code, str(error.detail)))


async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Log the real problem, but never send internal details to the user."""
    logger.exception("Unhandled error while processing %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", "Something went wrong. Please try again later."),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach all error handlers to the app."""
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)
