"""HTTP session for Hevy web-origin endpoints."""

from pathlib import Path
from typing import Any

from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from fitness_tracker.apis.hevy_app.web_auth import (
    HevyWebAuth,
    HevyWebCredentialStore,
    hevy_web_auth_headers,
)
from fitness_tracker.apis.session import APISession


class HevyWebSession(APISession):
    """APISession that refreshes and rotates Hevy web credentials."""

    def __init__(self, *, auth: HevyWebAuth) -> None:
        """Configure the shared web headers and token manager.

        Args:
            auth (HevyWebAuth): Access-token provider and refresher.
        """
        super().__init__(
            base_url="https://api.hevyapp.com",
            headers={},
            error_class=HevyAppAPIError,
            api_name="hevy_web",
            error_label="HevyApp API",
            delete_returns_none=True,
        )
        self._auth = auth

    def make_request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any] | None:
        """Send a request with a valid token and retry one authentication failure.

        Args:
            method (str): HTTP verb.
            endpoint (str): Hevy web API endpoint.
            **kwargs (Any): Extra request arguments.

        Returns:
            dict[str, Any] | None: Normalized response body.
        """
        self._set_auth_headers(self._auth.access_token())
        try:
            return super().make_request(method, endpoint, **kwargs)
        except HevyAppAPIError as exc:
            if exc.status_code != 401 or not self._auth.has_rotating_credentials:
                raise
            self._set_auth_headers(self._auth.access_token(force_refresh=True))
            return super().make_request(method, endpoint, **kwargs)

    def _set_auth_headers(self, access_token: str) -> None:
        self._headers = hevy_web_auth_headers(
            access_token,
            legacy=not self._auth.has_rotating_credentials,
        )


def hevy_web_session(
    api_key: str,
    *,
    credentials_path: Path | None = None,
) -> APISession:
    """Return a session for Hevy web-style endpoints on ``api.hevyapp.com``.

    Args:
        api_key (str): Legacy web access token retained for migration compatibility.

        credentials_path (Path | None): Rotating credential file, if enabled.

    Returns:
        APISession: Configured refreshing client session.
    """
    legacy_web_access_token = api_key
    store = HevyWebCredentialStore(credentials_path) if credentials_path is not None else None
    return HevyWebSession(
        auth=HevyWebAuth(
            store=store,
            legacy_token=legacy_web_access_token,
        )
    )
