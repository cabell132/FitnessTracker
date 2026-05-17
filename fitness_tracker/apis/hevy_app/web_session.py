"""HTTP session for Hevy web-origin endpoints (auth-token header flow)."""

from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from fitness_tracker.apis.session import APISession


def hevy_web_session(api_key: str) -> APISession:
    """Return a session for Hevy web-style endpoints on ``api.hevyapp.com``.

    Args:
        api_key (str): Web auth token.

    Returns:
        APISession: Configured client session. Successful ``DELETE`` calls return ``None``.
    """
    return APISession(
        base_url="https://api.hevyapp.com",
        headers={"auth-token": api_key, "x-api-key": "shelobs_hevy_web"},
        error_class=HevyAppAPIError,
        api_name="hevy_web",
        error_label="HevyApp API",
        delete_returns_none=True,
    )
