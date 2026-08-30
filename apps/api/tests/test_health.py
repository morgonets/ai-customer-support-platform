from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import Database
from app.core.request_context import RequestContextMiddleware
from app.main import app

client = TestClient(app)


def _database_with_mocked_methods() -> tuple[Database, AsyncMock, AsyncMock]:
    database = Database.__new__(Database)
    ping = AsyncMock()
    dispose = AsyncMock()
    database.ping = ping  # type: ignore[method-assign]
    database.dispose = dispose  # type: ignore[method-assign]
    return database, ping, dispose


def test_health_returns_process_status_and_request_id() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "api",
        "environment": "local",
    }
    UUID(response.headers["X-Request-ID"])


def test_request_id_middleware_preserves_valid_uuid() -> None:
    request_id = "0194f2c8-1cf0-7d6b-972c-a71fc21dbbf2"

    response = client.get("/health", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id


def test_request_id_middleware_replaces_invalid_value() -> None:
    response = client.get("/health", headers={"X-Request-ID": "unsafe value"})

    assert response.headers["X-Request-ID"] != "unsafe value"
    UUID(response.headers["X-Request-ID"])


def test_readiness_returns_ok_when_database_is_available() -> None:
    database, ping, _ = _database_with_mocked_methods()
    original_database = app.state.database
    app.state.database = database
    try:
        response = client.get("/ready")
    finally:
        app.state.database = original_database

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    ping.assert_awaited_once()


def test_readiness_hides_database_failure() -> None:
    database, ping, _ = _database_with_mocked_methods()
    ping.side_effect = SQLAlchemyError("private database detail")
    original_database = app.state.database
    app.state.database = database
    try:
        response = client.get("/ready")
    finally:
        app.state.database = original_database

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_unavailable"
    assert "private database detail" not in response.text


def test_app_lifespan_disposes_database() -> None:
    database, _, dispose = _database_with_mocked_methods()
    original_database = app.state.database
    app.state.database = database
    try:
        with TestClient(app) as lifespan_client:
            assert lifespan_client.get("/health").status_code == 200
    finally:
        app.state.database = original_database

    dispose.assert_awaited_once()


def test_request_context_logs_and_reraises_unhandled_failure() -> None:
    failing_app = FastAPI()
    failing_app.add_middleware(RequestContextMiddleware)

    @failing_app.get("/failure")
    def failure() -> None:
        raise RuntimeError("unexpected")

    with (
        patch("app.core.request_context.logger.exception") as log_exception,
        TestClient(failing_app) as failing_client,
        pytest.raises(RuntimeError, match="unexpected"),
    ):
        failing_client.get("/failure")

    log_exception.assert_called_once()
