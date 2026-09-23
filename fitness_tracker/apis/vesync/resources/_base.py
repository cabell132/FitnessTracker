"""Base resource class for VeSync API."""

from __future__ import annotations

from typing import Any

from fitness_tracker.apis.vesync.exceptions import VeSyncAPIError
from fitness_tracker.apis.vesync.response import unwrap_response
from fitness_tracker.apis.vesync.session import VeSyncSession


class Base:
    """Base class for VeSync API resources."""

    def __init__(self, session: VeSyncSession) -> None:
        """Initialise with a shared session.

        Args:
            session (VeSyncSession): Authenticated API session.
        """
        self.session = session

    def _post(self, endpoint: str, body: dict[str, Any] | None = None) -> tuple[Any, Any]:
        """Make a POST request and unwrap the response.

        Args:
            endpoint (str): API endpoint path.
            body (dict[str, Any] | None): Endpoint-specific body fields.

        Returns:
            tuple[Any, Any]: ``(result, code)`` from the unwrapped
                response.

        Raises:
            VeSyncAPIError: If VeSync reports a failure.
        """
        resp_body = self.session.make_request(endpoint, body=body)
        result, code = unwrap_response(resp_body)
        if code != 0:
            raise VeSyncAPIError(str(resp_body.get("msg") or "VeSync API request failed"))
        return result, code
