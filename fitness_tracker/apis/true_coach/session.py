"""HTTP session and request helpers for True Coach."""

from typing import Any

import requests

from logs import WideEvent

from fitness_tracker.apis.true_coach.auth import TrueCoachOAuthToken, authorize, make_url
from fitness_tracker.apis.true_coach.exceptions import TrueCoachAPIError

USER_AGENT = "beets/4 +https://beets.io/"


class TrueCoachSession:
    """Authenticated ``requests`` wrapper with response normalization."""

    def __init__(self, token: TrueCoachOAuthToken | None = None) -> None:
        """Create a session, loading ``authorize()`` output when no token is passed.

        Args:
            token (TrueCoachOAuthToken | None, optional): Cached OAuth token. Defaults to None.
        """
        self.token = token
        if self.token is None:
            self.token = authorize()

    def _get_request_headers(self) -> dict[str, str]:
        """Build default Authorization and User-Agent headers.

        Returns:
            dict[str, str]: Headers for API calls.
        """
        assert self.token is not None
        return {
            "Authorization": f"Bearer {self.token.access_token}",
            "User-Agent": USER_AGENT,
            "Role": "Client",
        }

    def format_response(self, _endpoint: str, response: requests.Response) -> dict[str, Any]:
        """Parse JSON and annotate successful dict payloads with ``request_url``.

        Args:
            _endpoint (str): Relative path (unused; kept for stable call signatures).
            response (requests.Response): Completed HTTP response.

        Returns:
            dict[str, Any]: Parsed JSON object or wrapped list payload.

        Raises:
            TrueCoachAPIError: If the server returned a non-success status.
        """
        if not response.ok:
            req_url = response.url or ""
            msg = f"Error {response.status_code} for {req_url!r}"
            raise TrueCoachAPIError(
                msg,
                status_code=response.status_code,
                url=req_url,
            )
        data = response.json()
        if response.status_code == 200:
            if isinstance(data, dict):
                data["request_url"] = response.url
            else:
                data = {"results": data, "request_url": response.url}
        return data

    def make_request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any] | None:
        """Send an HTTP request and return normalized JSON when present.

        Args:
            method (str): HTTP verb (for example ``GET`` or ``POST``).
            endpoint (str): API path or absolute URL fragment.
            **kwargs (Any): Extra arguments forwarded to ``requests.Session.request``.

        Returns:
            dict[str, Any] | None: Parsed body for non-204 responses; ``None`` for 204.

        Raises:
            TrueCoachAPIError: On transport errors or HTTP error responses.
        """
        headers = self._get_request_headers()
        norm_endpoint = endpoint
        if norm_endpoint.startswith("https://"):
            norm_endpoint = norm_endpoint.replace("https://", "")
        url = make_url(norm_endpoint)

        with WideEvent(operation="api_request", api="true_coach", method=method, url=url) as event:
            with requests.Session() as session:
                try:
                    response = session.request(
                        method.upper(),
                        url,
                        headers=headers,
                        timeout=10,
                        verify=False,
                        **kwargs,
                    )
                except Exception as e:
                    msg = f"Error connecting to TrueCoach API: {e}"
                    raise TrueCoachAPIError(msg, url=url) from e

            event.set(status_code=response.status_code)

            if not response.ok:
                req_url = response.url or ""
                msg = f"Error {response.status_code} for {req_url!r}"
                raise TrueCoachAPIError(
                    msg,
                    status_code=response.status_code,
                    url=req_url,
                )
            if response.status_code == 204:
                return None
            return self.format_response(endpoint, response)
