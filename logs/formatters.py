"""Log formatters for JSON file output and human-readable console output."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

_CONSOLE_CONTEXT_KEYS = (
    "api",
    "method",
    "url",
    "status_code",
    "sync_source",
    "sync_target",
    "workout_count",
    "event_count",
    "item_count",
    "token_source",
)


class JsonFileFormatter(logging.Formatter):
    """Serialize log records as single-line JSON for file storage."""

    def format(self, record: logging.LogRecord) -> str:
        """Convert a log record into a JSON string.

        Args:
            record (logging.LogRecord): Standard Python log record.

        Returns:
            str: Single-line JSON string.
        """
        payload: dict[str, Any] = (
            record.msg if isinstance(record.msg, dict) else {"message": record.getMessage()}
        )
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            **payload,
        }
        return json.dumps(entry, default=str)
