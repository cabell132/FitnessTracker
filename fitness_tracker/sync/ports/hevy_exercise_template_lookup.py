"""Port for looking up Hevy exercise templates by id."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fitness_tracker.apis.hevy_app.types import ExerciseTemplate


@runtime_checkable
class HevyExerciseTemplateLookup(Protocol):
    """Read-side: fetch a single exercise template from Hevy."""

    def get_exercise_template(self, template_id: str) -> ExerciseTemplate | None:
        """Fetch a single exercise template by its id.

        Args:
            template_id (str): Hevy exercise template id.

        Returns:
            ExerciseTemplate | None: Template metadata, or ``None`` when not found.
        """
        ...
