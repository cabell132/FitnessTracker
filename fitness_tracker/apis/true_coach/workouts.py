from pprint import pprint
from typing import Any, Literal, Optional

from fitness_tracker.apis.true_coach.session import TrueCoachSession
from fitness_tracker.apis.true_coach.types import (
    PutWorkoutItemRequest,
    PutWorkoutItemResponse,
    WorkoutResponse,
)


class TrueCoachWorkouts:
    """True Coach API Workouts class"""

    def __init__(self, session: TrueCoachSession) -> None:
        """Initiate the Workouts class with the token"""
        self._session = session
        self.endpoint = "clients/2876143/workouts"

    def get(
        self,
        order: Literal["asc", "desc"] = "asc",
        page: int = 1,
        per_page: int = 10,
        states: Literal["pending", "completed", "missed"]
        | list[Literal["pending", "completed", "missed"]] = "pending",
    ) -> Optional[WorkoutResponse]:
        """Get the workouts of the user.

        Args:
            order (Literal["asc", "desc"]): The order of the workouts
            page (int): The page of the workouts
            per_page (int): The number of workouts per page
            states (Literal["pending", "completed", "missed"] | list[Literal["pending", "completed", "missed"]]): The states of the workouts

        Returns:
            WorkoutResponse: The workouts of the user

        """
        if isinstance(states, list):
            states = ",".join(states)  # type: ignore

        params = {"order": order, "page": page, "per_page": per_page, "states": states}

        data = self._session.make_request(method="GET", endpoint=self.endpoint, json=params)
        if data:
            return WorkoutResponse(**data)
        return None

    def update_workout_item(
        self, workout_item_id: int, workout_item: PutWorkoutItemRequest
    ) -> Optional[PutWorkoutItemResponse]:
        """Update the state of a workout item.

        Args:
            workout_item_id (int): The ID of the workout item
            workout_item (PutWorkoutItemRequest): The workout item to update

        Returns:
            PutWorkoutItemResponse: The updated workout item
        """
        endpoint = f"workout_items/{workout_item_id}"
        data = self._session.make_request(
            method="PUT", endpoint=endpoint, json={"workout_item": workout_item.model_dump()}
        )
        if data:
            try:
                return PutWorkoutItemResponse(**data)
            except Exception as e:
                pprint(e)
                raise
        return None

    def update_workout(self, workout_id: int, workout: dict[str, Any]) -> Any:
        endpoint = f"workouts/{workout_id}"
        data = self._session.make_request(method="PUT", endpoint=endpoint, json=workout)
        if data:
            try:
                return data
            except Exception as e:
                pprint(e)
                raise
        return None

    def mark_as_completed(self, workout_id: int) -> Any:
        return self.update_workout(
            workout_id=workout_id,
            workout={"workout": {"state_event": "mark_as_completed"}},
        )

    def mark_as_missed(self, workout_id: int) -> Any:
        return self.update_workout(
            workout_id=workout_id,
            workout={"workout": {"state_event": "mark_as_missed"}},
        )
