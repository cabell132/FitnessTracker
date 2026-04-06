"""Hevy App routines endpoints."""

from typing import Any

from fitness_tracker.apis.hevy_app.session import HevyAppSession
from fitness_tracker.apis.hevy_app.types import (
    PostRoutinesRequestBody,
    PostRoutinesResponse,
    Routine,
    RoutineResponse,
)
from fitness_tracker.apis.hevy_app.web_session import HevyAppWebSession


class HevyAppRoutines:
    """CRUD helpers for saved routines (REST + web delete)."""

    def __init__(self, session: HevyAppSession, web_session: HevyAppWebSession) -> None:
        """Attach REST and web sessions.

        Args:
            session (HevyAppSession): Primary JSON API session.
            web_session (HevyAppWebSession): Session used for DELETE on web routes.
        """
        self._session = session
        self._web_session = web_session
        self.endpoint = "/routines"

    def get(self, page: int = 1, per_page: int = 10) -> RoutineResponse | None:
        """List routines with pagination.

        Args:
            page (int): Page index (1-based).
            per_page (int): Page size.

        Returns:
            RoutineResponse | None: Parsed list payload, or ``None`` when empty.
        """
        query = {"page": page, "pageSize": per_page}
        data = self._session.make_request(method="GET", endpoint=self.endpoint, params=query)
        if data:
            return RoutineResponse(**data)
        return None

    def get_routine(self, routine_id: str) -> Routine | None:
        """Fetch a single routine by id.

        Args:
            routine_id (str): Routine id.

        Returns:
            Routine | None: Parsed routine, or ``None`` when empty.
        """
        endpoint = f"{self.endpoint}/{routine_id}"
        data = self._session.make_request(method="GET", endpoint=endpoint)
        if data:
            return Routine(**data)
        return None

    def create(self, routine: PostRoutinesRequestBody) -> PostRoutinesResponse | None:
        """Create a routine from a typed request body.

        Args:
            routine (PostRoutinesRequestBody): Wrapper accepted by the API.

        Returns:
            PostRoutinesResponse | None: Parsed response, or ``None`` when empty.
        """
        data = self._session.make_request(
            method="POST", endpoint=self.endpoint, json=routine.model_dump()
        )
        if data:
            return PostRoutinesResponse(**data)
        return None

    def delete(self, routine_id: str) -> dict[str, Any] | None:
        """Delete a routine via the web session.

        Args:
            routine_id (str): Routine id to remove.

        Returns:
            dict[str, Any] | None: Parsed JSON if returned; otherwise ``None``.
        """
        endpoint = f"routine/{routine_id}"
        return self._web_session.make_request(method="DELETE", endpoint=endpoint)
