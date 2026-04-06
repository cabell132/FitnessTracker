"""Adapter wrapping :class:`HevyAppClient` behind :class:`HevyExerciseTemplateLookup`."""

from __future__ import annotations

from fitness_tracker.apis.hevy_app.client import HevyAppClient
from fitness_tracker.apis.hevy_app.types import ExerciseTemplate


class HevyExerciseTemplateLookupAdapter:
    """Delegates exercise template lookups to the Hevy REST client."""

    def __init__(self, client: HevyAppClient) -> None:
        """Wrap a Hevy client for template lookups.

        Args:
            client (HevyAppClient): Hevy API client.
        """
        self._client = client

    def get_exercise_template(self, template_id: str) -> ExerciseTemplate | None:
        """Fetch a single exercise template by its id.

        Args:
            template_id (str): Hevy exercise template id.

        Returns:
            ExerciseTemplate | None: Template metadata or ``None``.
        """
        return self._client.exercises.get_template(template_id)
