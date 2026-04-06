"""Authenticated HTTP session for the Hevy App REST API."""

import os

from dotenv import load_dotenv

from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from fitness_tracker.apis.session import APISession

load_dotenv()


def hevy_session(api_key: str | None = None) -> APISession:
    """Return a session for the Hevy REST API v1.

    Args:
        api_key (str | None, optional): API key. Defaults to the ``HEVY_API_KEY``
            environment variable.

    Returns:
        APISession: Configured client session.
    """
    key = os.environ["HEVY_API_KEY"] if api_key is None else api_key
    return APISession(
        base_url="https://api.hevyapp.com/v1",
        headers={"api-key": key},
        error_class=HevyAppAPIError,
        api_name="hevy",
        error_label="HevyApp API",
    )
