"""Port for proposing Hevy <-> True Coach workout item pairings."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fitness_tracker.llm.prompt_models import WorkoutItemLinkList


@runtime_checkable
class WorkoutItemLinker(Protocol):
    """Propose Hevy <-> True Coach workout item pairings using fuzzy matching."""

    def link_workout_items(
        self,
        hevy_items: list[dict[str, str | int]],
        true_coach_items: list[dict[str, str | int]],
    ) -> WorkoutItemLinkList:
        """Propose id pairings between Hevy and True Coach workout items.

        Args:
            hevy_items (list[dict[str, str | int]]): Hevy-side exercise blocks with id, name, order.
            true_coach_items (list[dict[str, str | int]]): True Coach blocks with id, name, order.

        Returns:
            WorkoutItemLinkList: Suggested links including optional nulls for unmatched items.
        """
        ...
