"""Exceptions for Hevy App API failures."""

from fitness_tracker.apis.exceptions import APIError


class HevyAppAPIError(APIError):
    """Structured error information for failed Hevy HTTP calls."""
