"""True Coach workouts API resource."""

from typing import Any, Literal

from fitness_tracker.apis.base import parse_response
from fitness_tracker.apis.session import APISession
from fitness_tracker.apis.true_coach.types import (
    PutWorkoutItemRequest,
    PutWorkoutItemResponse,
    WorkoutResponse,
)

WorkoutState = Literal["pending", "completed", "missed"]


class TrueCoachWorkouts:
    """Fetches and updates client workouts and workout items."""

    def __init__(self, session: APISession) -> None:
        """Attach this resource to an authenticated session.

        Args:
            session (APISession): Session used for HTTP calls.
        """
        self._session = session
        self.endpoint = "clients/2876143/workouts"

    def get(  # noqa: PLR0913
        self,
        order: Literal["asc", "desc"] = "asc",
        page: int = 1,
        per_page: int = 10,
        states: WorkoutState | list[WorkoutState] = "pending",
    ) -> WorkoutResponse | None:
        """List workouts with simple pagination and state filters.

        Args:
            order (Literal["asc", "desc"]): Sort order for results.
            page (int): Page index.
            per_page (int): Page size.
            states (WorkoutState | list[WorkoutState]): State filter for the listing.

        Returns:
            WorkoutResponse | None: Page of workouts, or ``None`` when the body is empty.
        """
        states_param: str = ",".join(states) if isinstance(states, list) else states

        params = {"order": order, "page": page, "per_page": per_page, "states": states_param}

        data = self._session.make_request(method="GET", endpoint=self.endpoint, json=params)
        return parse_response(data, WorkoutResponse)

    def update_workout_item(
        self, workout_item_id: int, workout_item: PutWorkoutItemRequest
    ) -> PutWorkoutItemResponse | None:
        """Apply a workout item update via PUT.

        Args:
            workout_item_id (int): True Coach workout item id.
            workout_item (PutWorkoutItemRequest): Fields to persist.

        Returns:
            PutWorkoutItemResponse | None: Updated item payload, or ``None`` if empty.
        """
        endpoint = f"workout_items/{workout_item_id}"
        data = self._session.make_request(
            method="PUT", endpoint=endpoint, json={"workout_item": workout_item.model_dump()}
        )
        return parse_response(data, PutWorkoutItemResponse)

    def update_workout(self, workout_id: int, workout: dict[str, Any]) -> Any:
        """Replace workout fields (generic PUT).

        Args:
            workout_id (int): Workout id.
            workout (dict[str, Any]): JSON body.

        Returns:
            Any: Parsed response body when present; otherwise ``None``.
        """
        endpoint = f"workouts/{workout_id}"
        data = self._session.make_request(method="PUT", endpoint=endpoint, json=workout)
        if data:
            return data
        return None

    def mark_as_completed(self, workout_id: int) -> Any:
        """Send the mark-as-completed state transition for a workout.

        Args:
            workout_id (int): Workout id.

        Returns:
            Any: API response body from ``update_workout``.
        """
        return self.update_workout(
            workout_id=workout_id,
            workout={"workout": {"state_event": "mark_as_completed"}},
        )

    def mark_as_missed(self, workout_id: int) -> Any:
        """Send the mark-as-missed state transition for a workout.

        Args:
            workout_id (int): Workout id.

        Returns:
            Any: API response body from ``update_workout``.
        """
        return self.update_workout(
            workout_id=workout_id,
            workout={"workout": {"state_event": "mark_as_missed"}},
        )
