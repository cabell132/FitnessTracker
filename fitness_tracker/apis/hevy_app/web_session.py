"""HTTP session for Hevy web-origin endpoints (auth-token header flow)."""

import os
from typing import Any
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

import logs

from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError

load_dotenv()

logger = logs.get_logger(__name__)


def _endpoint_without_url_scheme(endpoint: str) -> str:
    """Strip a leading ``https://`` if present so URL joining stays consistent.

    Args:
        endpoint (str): API path or full URL.

    Returns:
        str: Path without the ``https://`` scheme prefix.
    """
    return endpoint.removeprefix("https://")


class HevyAppWebSession:
    """Web-style Hevy calls using ``HEVY_WEB_API_KEY`` plus static web headers."""

    def __init__(self) -> None:
        """Load web API credentials from the environment."""
        self.api_key = os.environ["HEVY_WEB_API_KEY"]

    def make_url(self, endpoint: str, query: dict[str, str] | None = None) -> str:
        """Build an absolute URL on ``api.hevyapp.com``.

        Args:
            endpoint (str): Path starting with or without ``/``.
            query (dict[str, str] | None, optional): Query parameters. Defaults to None.

        Returns:
            str: Fully qualified URL.
        """
        api_base = "https://api.hevyapp.com"
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        if query:
            return api_base + endpoint + "?" + urlencode(query)
        return api_base + endpoint

    def _get_request_headers(self) -> dict[str, str]:
        """Return headers for web-token authenticated calls.

        Returns:
            dict[str, str]: Auth and API-key headers.
        """
        return {"auth-token": self.api_key, "x-api-key": "shelobs_hevy_web"}

    def format_response(self, _endpoint: str, response: requests.Response) -> dict[str, Any]:
        """Parse JSON and decorate successful dict bodies with ``request_url``.

        Args:
            _endpoint (str): Unused placeholder for a stable call signature.
            response (requests.Response): Completed HTTP response.

        Returns:
            dict[str, Any]: Parsed JSON payload.

        Raises:
            HevyAppAPIError: When the HTTP status indicates failure.
        """
        if not response.ok:
            req_url = response.url or ""
            msg = f"Error {response.status_code} for {req_url!r}"
            raise HevyAppAPIError(
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
        """Perform an HTTP request using web session authentication.

        Args:
            method (str): HTTP verb.
            endpoint (str): API path or host-relative URL.
            **kwargs (Any): Extra arguments for ``requests.Session.request``.

        Returns:
            dict[str, Any] | None: Parsed body when present; ``None`` for 204 or DELETE success.

        Raises:
            HevyAppAPIError: On transport errors or HTTP error responses.
        """
        url = self.make_url(_endpoint_without_url_scheme(endpoint))
        headers = self._get_request_headers()

        logger.debug("Making Hevy web request to %s", url)

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
                msg = f"Error connecting to HevyApp API: {e}"
                raise HevyAppAPIError(msg, url=url) from e

        logger.debug(
            "HevyApp API Request: status_code=%s, url=%s",
            response.status_code,
            url,
        )

        if not response.ok:
            req_url = response.url or ""
            msg = f"Error {response.status_code} for {req_url!r}"
            if response.text:
                msg = f"{msg} body={response.text!r}"
            raise HevyAppAPIError(
                msg,
                status_code=response.status_code,
                url=req_url,
            )
        if response.status_code == 204 or method.upper() == "DELETE":
            return None
        return self.format_response(endpoint, response)
