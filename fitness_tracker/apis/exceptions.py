"""Shared exception types for HTTP API clients."""


class APIError(Exception):
    """Base for all API transport and HTTP error responses."""

    def __init__(self, message: str, url: str, status_code: int | None = None) -> None:
        """Attach message, URL, and optional HTTP status.

        Args:
            message (str): Human-readable error summary.
            url (str): Request URL associated with the failure.
            status_code (int | None, optional): HTTP status when applicable. Defaults to None.
        """
        super().__init__(message)
        self.url = url
        self.status_code = status_code
