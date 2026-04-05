"""Wide event context manager for structured, timed log emission.

A wide event collects fields throughout an operation and emits one
context-rich log line on exit with automatic duration measurement.
"""

import time
from types import TracebackType
from typing import Any, Self

from logs.log import logger


class WideEvent:
    """Context manager that builds a single context-rich log event.

    Collects fields throughout an operation and emits one structured
    log line on exit with automatic duration measurement.

    Example::

        with WideEvent(operation="sync_workouts", source="hevy") as evt:
            workouts = fetch_workouts()
            evt.set(workout_count=len(workouts))
            process(workouts)
    """

    def __init__(self, **fields: Any) -> None:
        """Initialize the wide event with seed fields.

        Args:
            **fields (Any): Initial key-value pairs for the event.
        """
        self._fields: dict[str, Any] = fields
        self._start: float = 0.0

    def set(self, **kwargs: Any) -> Self:
        """Add or overwrite fields on this event.

        Args:
            **kwargs (Any): Key-value pairs to merge into the event.

        Returns:
            Self: The event instance for chaining.
        """
        self._fields.update(kwargs)
        return self

    def __enter__(self) -> Self:
        """Start the timer and return the event for enrichment.

        Returns:
            Self: This wide event instance.
        """
        self._start = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        """Finalize timing, record outcome, and emit the structured log line.

        Args:
            exc_type (type[BaseException] | None): Exception class if raised.
            exc_val (BaseException | None): Exception instance if raised.
            exc_tb (TracebackType | None): Traceback if an exception was raised.

        Returns:
            bool: Always ``False``; exceptions are never suppressed.
        """
        self._fields["duration_ms"] = round(
            (time.perf_counter() - self._start) * 1000,
            2,
        )

        if exc_type is not None:
            self._fields.setdefault("outcome", "error")
            self._fields["error"] = {
                "type": exc_type.__name__,
                "message": str(exc_val),
            }
            logger.error(self._fields)
        else:
            self._fields.setdefault("outcome", "success")
            logger.info(self._fields)

        return False
