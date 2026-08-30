import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_HEADER = "X-Request-ID"
logger = logging.getLogger("app.http")


def _request_id(value: str | None) -> str:
    if value is None:
        return str(uuid4())
    try:
        return str(UUID(value))
    except ValueError:
        return str(uuid4())


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = _request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        started_at = perf_counter()
        context = {
            "method": request.method,
            "path": request.url.path,
            "request_id": request_id,
        }
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request.failed",
                extra={**context, "duration_ms": round((perf_counter() - started_at) * 1000, 2)},
            )
            raise
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request.completed",
            extra={
                **context,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                "status_code": response.status_code,
            },
        )
        return response
