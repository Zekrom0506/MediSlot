import asyncio
import weakref

from starlette.types import ASGIApp, Receive, Scope, Send

# Cheap endpoints that never touch the database; they must answer even under overload.
UNLIMITED_PATHS = {"/health", "/metrics"}


class ConcurrencyLimitMiddleware:
    """Let at most `max_requests` requests run at once; the rest wait in line.

    Why: our endpoints are synchronous, so FastAPI runs each request in several
    hops through a shared thread pool (dependencies, the endpoint, the response).
    A request can hold a database connection between hops. Under a big burst,
    every thread could end up waiting for a connection while every connection
    belongs to a request waiting for a thread, and the API freezes (we hit this
    in load testing). With no more requests inside than database connections,
    a request that needs a connection can always get one.

    Waiting here is cheap: it holds no thread and no connection.
    """

    def __init__(self, app: ASGIApp, max_requests: int) -> None:
        self.app = app
        self.max_requests = max_requests
        # One semaphore per event loop (tests start several loops in one process).
        self.semaphores: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

    def semaphore_for_current_loop(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        if loop not in self.semaphores:
            self.semaphores[loop] = asyncio.Semaphore(self.max_requests)
        return self.semaphores[loop]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in UNLIMITED_PATHS:
            await self.app(scope, receive, send)
            return
        async with self.semaphore_for_current_loop():
            await self.app(scope, receive, send)
