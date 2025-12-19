from typing import Any, Optional

from fitness_tracker.apis.hevy_app.session import HevyAppSession
from fitness_tracker.apis.hevy_app.types import (
    PostRoutinesRequestBody,
    PostRoutinesResponse,
    Workout,
    WorkoutResponse,
)
from fitness_tracker.apis.hevy_app.web_session import HevyAppWebSession


class HevyAppRoutines:
    """True Coach API Routines class"""

    def __init__(self, session: HevyAppSession, web_session: HevyAppWebSession) -> None:
        """Initiate the Routines class with the token"""
        self._session = session
        self._web_session = web_session
        self.endpoint = "/routines"

    def get(self, page: int = 1, per_page: int = 10) -> Optional[WorkoutResponse]:
        """Get a paginated list of routines.

        Args:
            page (int): The page number to retrieve. Defaults to 1. Minimum is 1.
            per_page (int): The number of items per page. Defaults to 10. Maximum is 100.
        """
        query = {"page": page, "pageSize": per_page}

        data = self._session.make_request(method="GET", endpoint=self.endpoint, params=query)
        if data:
            return data

    def get_routine(self, id: str) -> Optional[Workout]:
        """Get a single routine by ID.

        Args:
            id (int): The ID of the exercise template to retrieve.
        """
        endpoint = f"{self.endpoint}/{id}"
        data = self._session.make_request(method="GET", endpoint=endpoint)
        if data:
            return Workout(**data)

    def create(self, routine: PostRoutinesRequestBody) -> Optional[PostRoutinesResponse]:
        """Create a new routine.

        Args:
            routine (PostRoutinesRequestBody): The routine to create.
        """
        data = self._session.make_request(
            method="POST", endpoint=self.endpoint, json=routine.model_dump()
        )
        if data:
            return PostRoutinesResponse(**data)

    def delete(self, id: str) -> Optional[dict[str, Any]]:
        """Delete a routine by ID."""
        endpoint = f"routine/{id}"
        return self._web_session.make_request(method="DELETE", endpoint=endpoint)
