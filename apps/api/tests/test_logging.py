import json
import logging
from typing import cast

from app.core.logging import JsonFormatter, configure_logging


def test_json_formatter_emits_safe_structured_context() -> None:
    record = logging.LogRecord(
        name="app.http",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="request.completed",
        args=(),
        exc_info=None,
    )
    record.request_id = "request-id"
    record.method = "GET"
    record.path = "/health"
    record.status_code = 200
    record.duration_ms = 1.25
    record.generation_id = "generation-id"
    record.provider = "deterministic"

    payload = cast(dict[str, object], json.loads(JsonFormatter().format(record)))

    assert payload["message"] == "request.completed"
    assert payload["request_id"] == "request-id"
    assert payload["status_code"] == 200
    assert payload["generation_id"] == "generation-id"
    assert payload["provider"] == "deterministic"
    assert "timestamp" in payload


def test_json_formatter_omits_absent_context() -> None:
    record = logging.LogRecord(
        name="app",
        level=logging.WARNING,
        pathname=__file__,
        lineno=10,
        msg="startup warning",
        args=(),
        exc_info=None,
    )

    payload = cast(dict[str, object], json.loads(JsonFormatter().format(record)))

    assert payload["level"] == "WARNING"
    assert "request_id" not in payload


def test_configure_logging_replaces_handlers_and_defaults_invalid_level() -> None:
    logger = logging.getLogger("app")
    logger.addHandler(logging.NullHandler())

    configure_logging("not-a-level")

    assert logger.level == logging.INFO
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0].formatter, JsonFormatter)
