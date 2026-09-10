import json
import logging
from datetime import UTC, datetime

CONTEXT_FIELDS = (
    "chunk_count",
    "citation_count",
    "duration_ms",
    "elapsed_ms",
    "error_type",
    "generation_id",
    "insufficient_context",
    "lexical_candidates",
    "method",
    "path",
    "provider",
    "request_id",
    "selected",
    "status_code",
    "vector_candidates",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def configure_logging(level: str) -> None:
    logger = logging.getLogger("app")
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
