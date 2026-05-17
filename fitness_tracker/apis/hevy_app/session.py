"""Authenticated HTTP session for the Hevy App REST API."""

from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from fitness_tracker.apis.session import APISession


def hevy_session(api_key: str) -> APISession:
    """Return a session for the Hevy REST API v1.

    Args:
        api_key (str): API key.

    Returns:
        APISession: Configured client session.
    """
    return APISession(
        base_url="https://api.hevyapp.com/v1",
        headers={"api-key": api_key},
        error_class=HevyAppAPIError,
        api_name="hevy",
        error_label="HevyApp API",
    )
