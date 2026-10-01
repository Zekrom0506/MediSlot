import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_config import request_id_context

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"
# Accept ids from upstream (e.g. Nginx) only if they look safe to put in logs.
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Give every request an id, log it when it finishes, and echo the id back in a header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_id = request.headers.get(REQUEST_ID_HEADER, "")
        if SAFE_REQUEST_ID.match(incoming_id):
            request_id = incoming_id
        else:
            request_id = uuid.uuid4().hex
        token = request_id_context.set(request_id)

        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Request crashed", extra={"method": request.method, "path": request.url.path})
            raise
        finally:
            request_id_context.reset(token)

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "Request finished",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
