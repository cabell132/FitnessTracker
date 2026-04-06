"""Shared configured HTTP session for REST API clients."""

from typing import Any
from urllib.parse import urlencode

import requests

from logs import WideEvent

from fitness_tracker.apis.exceptions import APIError


class APISession:
    """Configured HTTP session for any REST API.

    Centralizes URL building, logging, transport errors, and response parsing so
    clients only vary by base URL, headers, and error type.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        base_url: str,
        headers: dict[str, str],
        error_class: type[APIError] = APIError,
        api_name: str,
        error_label: str = "API",
        timeout: int = 10,
        delete_returns_none: bool = False,
    ) -> None:
        """Store connection settings and behavior flags.

        Args:
            base_url (str): Origin and path prefix for all requests (no trailing slash
                required).
            headers (dict[str, str]): Headers sent on every request.
            error_class (type[APIError]): Exception type for failures.
            api_name (str): Short name for WideEvent ``api=`` field.
            error_label (str, optional): Label used in transport error messages.
                Defaults to "API".
            timeout (int, optional): Request timeout in seconds. Defaults to 10.
            delete_returns_none (bool, optional): When True, successful ``DELETE``
                responses return ``None`` without parsing JSON. Defaults to False.
        """
        self._base_url = base_url.rstrip("/")
        self._headers = headers
        self._error_class = error_class
        self._api_name = api_name
        self._error_label = error_label
        self._timeout = timeout
        self._delete_returns_none = delete_returns_none

    def make_url(self, endpoint: str, query: dict[str, str] | None = None) -> str:
        """Build an absolute URL from base URL, path, and optional query string.

        Strips a leading ``https://`` from ``endpoint`` if present (same as the
        former ``_endpoint_without_url_scheme`` helper).

        Args:
            endpoint (str): Path (with or without leading ``/``) or scheme-stripped URL.
            query (dict[str, str] | None, optional): Query parameters. Defaults to None.

        Returns:
            str: Fully qualified URL.
        """
        path = endpoint.removeprefix("https://")
        if not path.startswith("/"):
            path = f"/{path}"
        if query:
            return self._base_url + path + "?" + urlencode(query)
        return self._base_url + path

    def _format_response(self, response: requests.Response) -> dict[str, Any]:
        """Parse JSON and annotate successful bodies with ``request_url``.

        Args:
            response (requests.Response): A successful HTTP response.

        Returns:
            dict[str, Any]: Parsed JSON payload, normalized for list bodies on HTTP 200.
        """
        data = response.json()
        if response.status_code == 200:
            if isinstance(data, dict):
                data["request_url"] = response.url
            else:
                data = {"results": data, "request_url": response.url}
        return data

    def make_request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any] | None:
        """Perform an HTTP request and return normalized JSON when present.

        Args:
            method (str): HTTP verb.
            endpoint (str): API path or host-relative URL.
            **kwargs (Any): Extra arguments for ``requests.Session.request``.

        Returns:
            dict[str, Any] | None: Parsed body when present; ``None`` for HTTP 204 or
                configured DELETE behavior.

        Raises:
            APIError: On transport errors or HTTP error responses (concrete type is
                ``self._error_class``).
        """
        url = self.make_url(endpoint)
        with WideEvent(operation="api_request", api=self._api_name, method=method, url=url) as event:
            with requests.Session() as session:
                try:
                    response = session.request(
                        method.upper(),
                        url,
                        headers=self._headers,
                        timeout=self._timeout,
                        verify=False,
                        **kwargs,
                    )
                except Exception as e:
                    msg = f"Error connecting to {self._error_label}: {e}"
                    raise self._error_class(msg, url=url) from e

            event.set(status_code=response.status_code)

            if not response.ok:
                req_url = response.url or ""
                msg = f"Error {response.status_code} for {req_url!r}"
                if response.text:
                    msg = f"{msg} body={response.text!r}"
                raise self._error_class(
                    msg,
                    status_code=response.status_code,
                    url=req_url,
                )

            if response.status_code == 204:
                return None
            if self._delete_returns_none and method.upper() == "DELETE":
                return None
            return self._format_response(response)
