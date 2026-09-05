"""Custom exercise management and website exercise statistics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fitness_tracker.apis.hevy_app.web._resource import Resource, segment
from fitness_tracker.apis.hevy_app.web.models import WebExerciseTemplate, WebRecord


class WebExercises(Resource):
    """Exercise metadata and history, separate from rich workout timing reads."""

    def list_custom(self) -> list[WebExerciseTemplate]:
        """Read custom templates including archive state and priority.

        Returns:
            list[WebExerciseTemplate]: Validated response with undocumented fields preserved.
        """
        return self._list("/custom_exercise_templates", WebExerciseTemplate)

    def units(self) -> list[WebRecord]:
        """Read per-exercise unit overrides.

        Returns:
            list[WebRecord]: Validated response with undocumented fields preserved.
        """
        return self._list("/exercise_template_units", WebRecord)

    def create(self, exercise: dict[str, Any]) -> dict[str, Any] | None:
        """Create a custom exercise using a web-format exercise body.

        Args:
            exercise (dict[str, Any]): Website-format custom exercise properties.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("POST", "/custom_exercise_template", json={"exercise": exercise})

    def update(self, exercise: dict[str, Any]) -> dict[str, Any] | None:
        """Update a custom exercise; the body's ID also selects the endpoint.

        Args:
            exercise (dict[str, Any]): Website-format custom exercise properties.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.

        Raises:
            TypeError: If an argument is invalid.
        """
        template_id = exercise.get("id")
        if not isinstance(template_id, str):
            message = "Custom exercise update requires a string id"
            raise TypeError(message)
        return self._write(
            "PUT", f"/custom_exercise_template/{segment(template_id)}", json={"exercise": exercise}
        )

    def delete(self, template_id: str) -> dict[str, Any] | None:
        """Delete a custom exercise; this does not migrate existing references.

        Args:
            template_id (str): Exercise template ID.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("DELETE", f"/custom_exercise_template/{segment(template_id)}")

    def history(self, template_id: str, *, offset: int = 0) -> list[WebRecord]:
        """Read paged exercise history, which does not include completion timestamps.

        Args:
            template_id (str): Exercise template ID.
            offset (int): Number of records to skip.

        Returns:
            list[WebRecord]: Validated response with undocumented fields preserved.

        Raises:
            ValueError: If an argument is invalid.
        """
        if offset < 0:
            message = "History offset must be nonnegative"
            raise ValueError(message)
        return self._list(
            "/user_exercise_history_paged", WebRecord, exerciseTemplateId=template_id, offset=offset
        )

    def sets(self, template_id: str, *, after: datetime) -> list[WebRecord]:
        """Read exercise statistics since an aware datetime, without completion timestamps.

        Args:
            template_id (str): Exercise template ID.
            after (datetime): Inclusive lower time boundary.

        Returns:
            list[WebRecord]: Validated response with undocumented fields preserved.

        Raises:
            ValueError: If an argument is invalid.
        """
        if after.utcoffset() is None:
            message = "Exercise statistics require a timezone-aware start"
            raise ValueError(message)
        return self._list(
            f"/user_exercise_sets/{segment(template_id)}/{segment(after.isoformat())}", WebRecord
        )
