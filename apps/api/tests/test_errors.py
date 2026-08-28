import asyncio
from collections.abc import Awaitable, Callable

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import ApiError, api_error_handler, validation_error_handler

ErrorHandler = Callable[[Request, Exception], Awaitable[JSONResponse]]


def _request(request_id: str | None = "request-id") -> Request:
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    if request_id is not None:
        request.state.request_id = request_id
    return request


def test_api_error_handler_returns_stable_envelope() -> None:
    response = asyncio.run(
        api_error_handler(
            _request(),
            ApiError(status_code=403, code="forbidden", message="Action is not allowed."),
        )
    )

    assert response.status_code == 403
    assert b'"request_id":"request-id"' in response.body


def test_error_handler_uses_fallback_request_id() -> None:
    response = asyncio.run(
        api_error_handler(
            _request(None),
            ApiError(status_code=400, code="bad_request", message="Invalid request."),
        )
    )

    assert b'"request_id":"unavailable"' in response.body


def test_validation_error_handler_sanitizes_details() -> None:
    exception = RequestValidationError(
        [{"loc": ("body", "name"), "msg": "Required", "type": "missing", "input": "secret"}]
    )

    response = asyncio.run(validation_error_handler(_request(), exception))

    assert response.status_code == 422
    assert b'"location":["body","name"]' in response.body
    assert b"secret" not in response.body


@pytest.mark.parametrize("handler", [api_error_handler, validation_error_handler])
def test_error_handlers_reraise_unexpected_exception(handler: ErrorHandler) -> None:
    async def invoke() -> JSONResponse:
        result = await handler(_request(), RuntimeError("unexpected"))
        assert isinstance(result, JSONResponse)
        return result

    with pytest.raises(RuntimeError, match="unexpected"):
        asyncio.run(invoke())
