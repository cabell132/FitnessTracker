"""Exceptions raised by the True Coach API client."""

from fitness_tracker.apis.exceptions import APIError


class TrueCoachAPIError(APIError):
    """Structured error information for failed HTTP calls."""
