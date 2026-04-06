"""Hevy App exercise history endpoint."""

from __future__ import annotations

from datetime import datetime

from fitness_tracker.apis.hevy_app.session import HevyAppSession
from fitness_tracker.apis.hevy_app.types import ExerciseHistoryResponse


class HevyAppExerciseHistory:
    """Retrieve set-level history for a specific exercise template."""

    def __init__(self, session: HevyAppSession) -> None:
        """Attach the REST session used for exercise history calls.

        Args:
            session (HevyAppSession): Authenticated API session.
        """
        self._session = session
        self.endpoint = "/exercise_history"

    def get(
        self,
        exercise_template_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> ExerciseHistoryResponse | None:
        """Fetch history for an exercise template with optional date filtering.

        Args:
            exercise_template_id (str): The exercise template id.
            start_date (datetime | None): Optional lower-bound filter (ISO 8601).
            end_date (datetime | None): Optional upper-bound filter (ISO 8601).

        Returns:
            ExerciseHistoryResponse | None: History entries, or ``None`` when empty.
        """
        endpoint = f"{self.endpoint}/{exercise_template_id}"
        query: dict[str, str] = {}
        if start_date is not None:
            query["start_date"] = start_date.isoformat()
        if end_date is not None:
            query["end_date"] = end_date.isoformat()
        data = self._session.make_request(method="GET", endpoint=endpoint, params=query or None)
        if data:
            return ExerciseHistoryResponse(**data)
        return None
