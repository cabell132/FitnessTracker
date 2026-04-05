"""Exceptions for Hevy App API failures."""


class HevyAppAPIError(Exception):
    """Structured error information for failed Hevy HTTP calls."""

    url: str
    status_code: int | None = None

    def __init__(self, message: str, url: str, status_code: int | None = None) -> None:
        """Persist HTTP context on the exception instance.

        Args:
            message (str): Human-readable error summary.
            url (str): Request URL associated with the failure.
            status_code (int | None, optional): HTTP status when applicable. Defaults to None.
        """
        super().__init__(message)
        self.status_code = status_code
        self.url = url
