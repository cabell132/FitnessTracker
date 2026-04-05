"""Human-readable log formatter for terminal output."""

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
    "auth_source",
)


class ConsoleFormatter(logging.Formatter):
    """Human-readable summary formatter for terminal output."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a concise console line.

        Args:
            record (logging.LogRecord): Standard Python log record.

        Returns:
            str: Formatted string for terminal display.
        """
        ts = datetime.fromtimestamp(record.created, tz=UTC).strftime("%H:%M:%S")
        level = record.levelname

        if not isinstance(record.msg, dict):
            return f"{ts} {level} {record.getMessage()}"

        event: dict[str, Any] = record.msg
        operation = event.get("operation", "event")
        parts: list[str] = [f"{ts} {level} [{operation}]"]

        outcome = event.get("outcome")
        if outcome:
            parts.append(f"outcome={outcome}")

        duration = event.get("duration_ms")
        if duration is not None:
            parts.append(f"duration={duration}ms")

        parts.extend(f"{key}={event[key]}" for key in _CONSOLE_CONTEXT_KEYS if key in event)

        error = event.get("error")
        if error:
            parts.append(f"error={error}")

        return " ".join(parts)
