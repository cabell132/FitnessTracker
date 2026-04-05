"""Exceptions for Hevy App API failures."""

import logs

logger = logs.get_logger(__name__)


class HevyAppAPIError(Exception):
    """Structured error information for failed Hevy HTTP calls."""

    url: str
    status_code: int | None = None

    def __init__(
        self, message: str, url: str, status_code: int | None = None
    ) -> None:
        """Persist context and emit a structured log line.

        Args:
            message (str): Human-readable error summary.
            url (str): Request URL associated with the failure.
            status_code (int | None, optional): HTTP status when applicable. Defaults to None.
        """
        super().__init__(message)
        self.status_code = status_code
        self.url = url

        logger.error(
            "Hevy App API Error: %s (status_code=%s, url=%s)",
            message,
            status_code,
            url,
        )
