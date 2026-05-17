"""HTTP session and request helpers for True Coach."""

from fitness_tracker.apis.session import APISession
from fitness_tracker.apis.true_coach.auth import TrueCoachOAuthToken, authorize
from fitness_tracker.apis.true_coach.exceptions import TrueCoachAPIError

_USER_AGENT = "beets/4 +https://beets.io/"


def true_coach_session(
    *,
    email: str,
    password: str,
    token: TrueCoachOAuthToken | None = None,
) -> APISession:
    """Return an authenticated session for the True Coach proxy API.

    Args:
        email (str): True Coach login email.
        password (str): True Coach password.
        token (TrueCoachOAuthToken | None, optional): Cached OAuth token. Defaults to None.

    Returns:
        APISession: Configured client session.
    """
    if token is None:
        token = authorize(email=email, password=password)
    return APISession(
        base_url="https://app.truecoach.co/proxy/api",
        headers={
            "Authorization": f"Bearer {token.access_token}",
            "User-Agent": _USER_AGENT,
            "Role": "Client",
        },
        error_class=TrueCoachAPIError,
        api_name="true_coach",
        error_label="TrueCoach API",
    )
