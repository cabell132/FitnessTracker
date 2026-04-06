"""HTTP session for Hevy web-origin endpoints (auth-token header flow)."""

import os

from dotenv import load_dotenv

from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from fitness_tracker.apis.session import APISession

load_dotenv()


def hevy_web_session(api_key: str | None = None) -> APISession:
    """Return a session for Hevy web-style endpoints on ``api.hevyapp.com``.

    Args:
        api_key (str | None, optional): Web auth token. Defaults to the
            ``HEVY_WEB_API_KEY`` environment variable.

    Returns:
        APISession: Configured client session. Successful ``DELETE`` calls return ``None``.
    """
    key = os.environ["HEVY_WEB_API_KEY"] if api_key is None else api_key
    return APISession(
        base_url="https://api.hevyapp.com",
        headers={"auth-token": key, "x-api-key": "shelobs_hevy_web"},
        error_class=HevyAppAPIError,
        api_name="hevy_web",
        error_label="HevyApp API",
        delete_returns_none=True,
    )
