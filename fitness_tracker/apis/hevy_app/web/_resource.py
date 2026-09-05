"""Private request and response handling shared by website resources."""

from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import quote

from pydantic import TypeAdapter

from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from fitness_tracker.apis.hevy_app.web.models import WebRecord


class WebSession(Protocol):
    """Request boundary implemented by the existing refreshing HTTP session."""

    def make_request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any] | None:
        """Perform a request and return the shared session's normalized body.

        Args:
            method (str): HTTP method.
            endpoint (str): Host-relative website path.
            **kwargs (Any): Request options forwarded to the authenticated session.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        ...


def segment(value: str | int) -> str:
    """Encode one nonempty URL path component.

    Args:
        value (str | int): Resource identifier or path component.

    Returns:
        str: Result of the requested operation.

    Raises:
        ValueError: If an argument is invalid.
    """
    text = str(value)
    if not text or text in {".", ".."}:
        message = "A nonempty resource identifier is required"
        raise ValueError(message)
    return quote(text, safe="")


class Resource:
    """Normalize session envelopes without silently accepting malformed responses."""

    def __init__(self, session: WebSession) -> None:
        """Use the shared authenticated session.

        Args:
            session (WebSession): Shared refreshing web request boundary.
        """
        self._session = session

    def _get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        data = self._session.make_request(method="GET", endpoint=endpoint, params=params)
        if data is None:
            message = "Hevy returned no JSON for a read request"
            raise HevyAppAPIError(message, url=endpoint)
        return {key: value for key, value in data.items() if key != "request_url"}

    def _list[T: WebRecord](self, endpoint: str, model: type[T], **params: Any) -> list[T]:
        data = self._get(endpoint, **params)
        items = TypeAdapter(list[dict[str, Any]]).validate_python(data.get("results"))
        return [model.model_validate(item) for item in items]

    def _write(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any] | None:
        return self._session.make_request(method=method, endpoint=endpoint, **kwargs)
