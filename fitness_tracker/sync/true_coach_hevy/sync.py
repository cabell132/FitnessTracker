"""Deprecated legacy True Coach to Hevy Routine creation entry point."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fitness_tracker.apis import HevyAppClient, TrueCoachClient
    from fitness_tracker.database import Store
    from fitness_tracker.llm.fitness_llm import FitnessLLM


LEGACY_DIRECT_ROUTINE_CREATION_ERROR = (
    "Legacy direct True Coach to Hevy Routine creation is retired. "
    "Use TrueCoachToHevyReviewService.apply or RoutineReplacementBatchWorkflow.sync "
    "so Routine creation goes through the strict-safe review/apply workflow."
)


class TrueCoachToHevySyncronizer:
    """Deprecated compatibility shim for the retired direct Routine creator."""

    def __init__(  # noqa: PLR0913
        self,
        store: Store,
        source: TrueCoachClient,
        target: HevyAppClient,
        llm: FitnessLLM,
    ) -> None:
        """Initiate the syncronizer with the clients.

        Args:
            store (Store): Persistence layer.
            source (TrueCoachClient): True Coach API client.
            target (HevyAppClient): Hevy API client for routine creation.
            llm (FitnessLLM): Parser for set prescriptions.
        """
        self._store = store
        self._source = source
        self._target = target
        self._llm = llm

    def sync_workout(self, workout_id: int) -> None:
        """Reject legacy direct Routine creation.

        Args:
            workout_id (int): The workout id to syncronize.

        Raises:
            RuntimeError: Always, because this path bypasses strict-safe review.
        """
        raise RuntimeError(LEGACY_DIRECT_ROUTINE_CREATION_ERROR)
