"""Shared exercise resolution logic for True Coach → Hevy syncs.

Encapsulates the 6-step resolution chain used by both
:class:`TrueCoachToHevySyncronizer` and :class:`TrackerToHevySyncronizer`
to map a workout item to a Hevy exercise template.
"""

from __future__ import annotations

from fitness_tracker.database.models import HevyAppExercise
from fitness_tracker.database.models.tracker import Exercise as TrackerExercise
from fitness_tracker.database.uow import UnitOfWork


def resolve_hevy_exercise(  # noqa: PLR0913, PLR0915
    uow: UnitOfWork,
    item_name: str | None,
    tc_exercise_hevy_app: HevyAppExercise | None,
    placeholders: list[HevyAppExercise],
    used: list[HevyAppExercise],
) -> tuple[HevyAppExercise, str | None]:
    """Resolve a workout item to a Hevy exercise template.

    Resolution chain:
    1. Use the True Coach exercise's linked Hevy exercise if available.
    2. Look up a tracker exercise by name and use its Hevy link.
    3. Fall back to a placeholder exercise.
    4. Ensure the resolved exercise hasn't already been used in this workout.
    5. Guard against exhausted placeholders.

    Args:
        uow (UnitOfWork): Active unit of work.
        item_name (str | None): Name of the workout item for fallback lookup.
        tc_exercise_hevy_app (HevyAppExercise | None): Direct TC→Hevy link if present.
        placeholders (list[HevyAppExercise]): Available placeholder exercises (mutated).
        used (list[HevyAppExercise]): Already-used exercises in this workout (mutated).

    Returns:
        tuple[HevyAppExercise, str | None]: The resolved Hevy exercise and an optional
            note override. ``note_override`` is non-None when a placeholder was used
            and the item name should appear in the exercise notes.

    Raises:
        IndexError: If placeholders are exhausted.
    """
    note_override: str | None = None
    hevy_app_exercise: HevyAppExercise

    if isinstance(tc_exercise_hevy_app, HevyAppExercise):
        # Step 1: Direct TC exercise → Hevy link
        hevy_app_exercise = tc_exercise_hevy_app
    elif item_name and (exercise_instance := uow.tracker_get_exercise(name=item_name)):
        # Step 2: Lookup by name in tracker
        if hevy_app := exercise_instance.hevy_app:
            if isinstance(hevy_app, HevyAppExercise):
                hevy_app_exercise = hevy_app
            else:
                hevy_app_exercise = placeholders.pop(0)
                note_override = item_name
        else:
            hevy_app_exercise = placeholders.pop(0)
            note_override = item_name
    else:
        # Step 3: No match — insert exercise if named, use placeholder
        if item_name:
            exercise_instance = TrackerExercise(name=item_name)
            uow.insert_ignore(exercise_instance)
        hevy_app_exercise = placeholders.pop(0)
        note_override = item_name

    # Step 4: Dedup — if this exercise was already used, swap to placeholder
    if hevy_app_exercise in used:
        hevy_app_exercise = placeholders.pop(0)
        note_override = item_name

    return hevy_app_exercise, note_override
