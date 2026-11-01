"""Pure ASGI middleware: correlation metadata, without transforming response bodies."""
import logging
from contextvars import ContextVar
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from src.emailagent.api.i18n import resolve_locale

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger(__name__)


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_context.get()
        return True


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = str(uuid4())
        state = scope.setdefault("state", {})
        state.update(request_id=request_id, locale=resolve_locale(Headers(scope=scope).get("accept-language", "")))
        token = request_id_context.set(request_id)
        started = perf_counter()
        status = 500

        async def send_with_context(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        finally:
            # Do not log query strings: OAuth callbacks contain authorization codes.
            route = scope.get("route")
            logger.info("HTTP method=%s route=%s status=%s duration_ms=%.1f request_id=%s",
                        scope["method"], getattr(route, "path", "<unmatched>"), status,
                        (perf_counter() - started) * 1000, request_id)
            request_id_context.reset(token)
