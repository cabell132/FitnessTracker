from datetime import datetime
from typing import Optional

from fitness_tracker.apis.hevy_app.session import HevyAppSession
from fitness_tracker.apis.hevy_app.types import (
    PaginatedWorkoutEvents,
    PostWorkoutsRequestBody,
    PostWorkoutsResponse,
    Workout,
    WorkoutResponse,
)


class HevyAppWorkouts:
    """True Coach API Workouts class"""

    def __init__(self, session: HevyAppSession) -> None:
        """Initiate the Workouts class with the token"""
        self._session = session
        self.endpoint = "/workouts"

    def get(self, page: int = 1, per_page: int = 10) -> Optional[WorkoutResponse]:
        """Get a paginated list of workouts.

        Args:
            page (int): The page number to retrieve. Defaults to 1. Minimum is 1.
            per_page (int): The number of items per page. Defaults to 10. Maximum is 10.
        """
        query = {"page": page, "pageSize": per_page}

        data = self._session.make_request(method="GET", endpoint=self.endpoint, params=query)
        if data:
            return WorkoutResponse(**data)

    def get_workout(self, id: str) -> Optional[Workout]:
        """Get a single workout's complete details by the workoutId.

        Args:
            id (int): The ID of the workout to retrieve.
        """
        endpoint = f"{self.endpoint}/{id}"
        data = self._session.make_request(method="GET", endpoint=endpoint)
        if data:
            return Workout(**data)

    def get_workout_count(self) -> int:
        """Get the total number of workouts on the account.

        Returns:
            int: The count of workouts available on the account.
        """
        endpoint = f"{self.endpoint}/count"
        data = self._session.make_request(method="GET", endpoint=endpoint)
        return data["workout_count"] if data else 0

    def get_workout_events(
        self, page: int = 1, per_page: int = 10, since: datetime = datetime(1970, 1, 1)
    ) -> Optional[PaginatedWorkoutEvents]:
        """Retrieve a paged list of workout events (updates or deletes) since a given date.

        Events are ordered from newest to oldest. The intention is to allow clients to keep
        their local cache of workouts up to date without having to fetch the entire list of workouts.

        Args:
            page (int): The page number to retrieve. Defaults to 1. Minimum is 1.
            per_page (int): The number of items per page. Defaults to 10. Maximum is 10.
            since (str): The date and time to start retrieving workouts from. Defaults to "1970-01-01T00:00:00Z".

        Returns a paginated array of workout events, indicating updates or deletions.
        """
        query = {"page": page, "pageSize": per_page, "since": since.isoformat()}

        endpoint = f"{self.endpoint}/events"
        data = self._session.make_request(method="GET", endpoint=endpoint, params=query)
        if data:
            return PaginatedWorkoutEvents(**data)

    def update_workout(self, id: str, workout: Workout) -> Optional[Workout]:
        """Update a workout by ID.

        Args:
            id (int): The ID of the workout to update.
            workout (Workout): The updated workout object.
        """
        endpoint = f"{self.endpoint}/{id}"
        data = self._session.make_request(
            method="PUT", endpoint=endpoint, json=workout.model_dump()
        )
        if data:
            return Workout(**data)

    def create(self, workout: PostWorkoutsRequestBody) -> Optional[PostWorkoutsResponse]:
        """Create a new workout.

        Args:
            workout (Workout): The workout object to create.
        """
        data = self._session.make_request(
            method="POST", endpoint=self.endpoint, json=workout.model_dump()
        )
        if data:
            return PostWorkoutsResponse(**data)
