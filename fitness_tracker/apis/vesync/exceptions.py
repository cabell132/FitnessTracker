"""Errors raised by the VeSync client."""

from __future__ import annotations

from typing import Any, Self

from rnet import DecodingError


class VeSyncBaseError(Exception):
    """Base error for VeSync requests."""


class VeSyncAPIError(VeSyncBaseError):
    """An HTTP or VeSync API error."""

    def __init__(self, message: str, http_status: int | None = None) -> None:
        """Store a safe error message and optional HTTP status.

        Args:
            message (str): Human-readable failure reason.
            http_status (int | None): HTTP status, if available.
        """
        super().__init__(message)
        self.http_status = http_status

    @classmethod
    def from_response(cls, response: Any) -> Self:
        """Build an error from an HTTP response.

        Args:
            response (Any): Raw HTTP response.

        Returns:
            Self: VeSync error with the response status.
        """
        status = response.status_code.as_int()
        try:
            body = response.json()
        except (ValueError, TypeError, DecodingError):
            body = None
        message = (body.get("msg") or body.get("message")) if isinstance(body, dict) else None
        return cls(str(message or f"VeSync request failed (HTTP {status})"), status)


class VeSyncAuthError(VeSyncBaseError):
    """A VeSync authentication failure."""

    def __init__(self, message: str, error: str | None = None) -> None:
        """Store the error message and optional API error code.

        Args:
            message (str): Human-readable failure reason.
            error (str | None): VeSync error code, if available.
        """
        super().__init__(message)
        self.error = error
