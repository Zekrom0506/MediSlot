import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging_config import request_id_context

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"
# Accept ids from upstream (e.g. Nginx) only if they look safe to put in logs.
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# Scraped every few seconds by Prometheus and load balancers; logging them is just noise.
QUIET_PATHS = {"/metrics", "/health", "/ready"}


class RequestContextMiddleware:
    """Give every request an id, log it when it finishes, and echo the id back in a header.

    Written as a plain ASGI middleware rather than Starlette's BaseHTTPMiddleware:
    BaseHTTPMiddleware cancels the request when the client disconnects, and a
    cancelled request can leave its database session behind in a worker thread,
    leaking the connection. Here the request always runs to the end.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming_id = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        if SAFE_REQUEST_ID.match(incoming_id):
            request_id = incoming_id
        else:
            request_id = uuid.uuid4().hex
        token = request_id_context.set(request_id)
        started_at = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_context.reset(token)
            if scope["path"] not in QUIET_PATHS:
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                logger.info(
                    "Request finished",
                    extra={
                        "request_id": request_id,
                        "method": scope["method"],
                        "path": scope["path"],
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                    },
                )
