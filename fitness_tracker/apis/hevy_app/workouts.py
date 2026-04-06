"""Hevy App workout endpoints."""

from datetime import UTC, datetime

from fitness_tracker.apis.session import APISession
from fitness_tracker.apis.hevy_app.types import (
    PaginatedWorkoutEvents,
    PostWorkoutsRequestBody,
    PostWorkoutsResponse,
    Workout,
    WorkoutResponse,
)


class HevyAppWorkouts:
    """Workout listing, events, and mutation helpers."""

    def __init__(self, session: APISession) -> None:
        """Attach the REST session used for all workout calls.

        Args:
            session (APISession): Authenticated API session.
        """
        self._session = session
        self.endpoint = "/workouts"

    def get(self, page: int = 1, per_page: int = 10) -> WorkoutResponse | None:
        """List workouts with pagination.

        Args:
            page (int): Page index (1-based).
            per_page (int): Page size.

        Returns:
            WorkoutResponse | None: Parsed list payload, or ``None`` when empty.
        """
        query = {"page": page, "pageSize": per_page}
        data = self._session.make_request(method="GET", endpoint=self.endpoint, params=query)
        if data:
            return WorkoutResponse(**data)
        return None

    def get_workout(self, workout_id: str) -> Workout | None:
        """Fetch one workout by id.

        Args:
            workout_id (str): Workout id.

        Returns:
            Workout | None: Parsed workout, or ``None`` when empty.
        """
        endpoint = f"{self.endpoint}/{workout_id}"
        data = self._session.make_request(method="GET", endpoint=endpoint)
        if data:
            return Workout(**data)
        return None

    def get_workout_count(self) -> int:
        """Return total workouts reported by the count endpoint.

        Returns:
            int: Count, or ``0`` when the response is missing.
        """
        endpoint = f"{self.endpoint}/count"
        data = self._session.make_request(method="GET", endpoint=endpoint)
        return int(data["workout_count"]) if data and "workout_count" in data else 0

    def get_workout_events(
        self,
        page: int = 1,
        per_page: int = 10,
        since: datetime = datetime(1970, 1, 1, tzinfo=UTC),
    ) -> PaginatedWorkoutEvents | None:
        """Page workout create/update/delete events after a timestamp.

        Args:
            page (int): Page index (1-based).
            per_page (int): Page size.
            since (datetime): Lower bound; serialized with ``isoformat``.

        Returns:
            PaginatedWorkoutEvents | None: Event page, or ``None`` when empty.
        """
        query = {"page": page, "pageSize": per_page, "since": since.isoformat()}
        endpoint = f"{self.endpoint}/events"
        data = self._session.make_request(method="GET", endpoint=endpoint, params=query)
        if data:
            return PaginatedWorkoutEvents(**data)
        return None

    def update_workout(self, workout_id: str, workout: Workout) -> Workout | None:
        """Replace workout fields with a full ``Workout`` model.

        Args:
            workout_id (str): Workout id.
            workout (Workout): Replacement payload.

        Returns:
            Workout | None: Parsed workout, or ``None`` when empty.
        """
        endpoint = f"{self.endpoint}/{workout_id}"
        data = self._session.make_request(
            method="PUT", endpoint=endpoint, json=workout.model_dump()
        )
        if data:
            return Workout(**data)
        return None

    def create(self, workout: PostWorkoutsRequestBody) -> PostWorkoutsResponse | None:
        """Create a workout from the POST DTO.

        Args:
            workout (PostWorkoutsRequestBody): Body wrapper accepted by the API.

        Returns:
            PostWorkoutsResponse | None: Parsed response, or ``None`` when empty.
        """
        data = self._session.make_request(
            method="POST", endpoint=self.endpoint, json=workout.model_dump()
        )
        if data:
            return PostWorkoutsResponse(**data)
        return None
