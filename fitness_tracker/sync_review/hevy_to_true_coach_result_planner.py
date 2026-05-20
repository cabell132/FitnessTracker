"""Plan performed Hevy Workout result mappings for True Coach sync review."""

from __future__ import annotations

import re
from typing import Any, cast

from fitness_tracker.apis.hevy_app.types import Set as HevySet
from fitness_tracker.database.models.hevy_app import (
    HevyAppExercise,
    HevyAppSets,
    HevyAppWorkout,
    HevyAppWorkoutItem,
)
from fitness_tracker.database.models.tracker import Workout as TrackerWorkout
from fitness_tracker.database.models.true_coach import TrueCoachWorkout, TrueCoachWorkoutItem
from fitness_tracker.sync_review.hevy_to_true_coach_result_formatters import RESULT_FORMATTERS

PRESCRIBED_SETS_REPS_PATTERN = re.compile(r"\b(\d+)\s*x\s*(\d+)\b", flags=re.IGNORECASE)


class HevyToTrueCoachResultSyncPlanner:
    """Build read-only Hevy to True Coach performed-result mapping plans."""

    def plan(
        self,
        workout: HevyAppWorkout,
        tracker_workout: TrackerWorkout | None = None,
    ) -> dict[str, Any]:
        """Plan how a performed Hevy Workout maps to True Coach Workout Items.

        Args:
            workout (HevyAppWorkout): Performed Hevy Workout to sync from.
            tracker_workout (TrackerWorkout | None): Optional cross-domain tracker workout.

        Returns:
            dict[str, Any]: JSON-serializable result sync review plan.
        """
        true_coach_workout = (
            workout.true_coach if isinstance(workout.true_coach, TrueCoachWorkout) else None
        )
        items = [
            _plan_item(item, true_coach_workout, tracker_workout) for item in _sort_items(workout)
        ]
        return _plan(workout, true_coach_workout, items)


def _plan_item(
    item: HevyAppWorkoutItem,
    true_coach_workout: TrueCoachWorkout | None,
    tracker_workout: TrackerWorkout | None,
) -> dict[str, Any]:
    exercise = item.exercise if isinstance(item.exercise, HevyAppExercise) else None
    exercise_type = _exercise_type(exercise)
    formatter_name = _formatter_name(exercise_type)
    target = item.true_coach if isinstance(item.true_coach, TrueCoachWorkoutItem) else None
    if target is None:
        candidates = _candidate_targets(item, true_coach_workout, tracker_workout)
    else:
        candidates = []
    target_inferred_from_sets_reps = (
        target is None and len(candidates) == 1 and _is_repeated_performed_exercise(item)
    )
    blockers = _item_blockers(exercise, exercise_type, true_coach_workout)
    blockers.extend(_target_blockers(target, candidates, target_inferred_from_sets_reps))
    warnings = _item_warnings(target, candidates)
    return {
        "hevy_workout_item_id": item.id,
        "index": item.index,
        "name": item.name,
        "notes": item.notes,
        "superset_id": item.superset_id,
        "exercise": _hevy_exercise_to_dict(exercise),
        "sets": [_set_to_dict(set_) for set_ in _sort_sets(item)],
        "formatter": formatter_name,
        "proposed_result_text": _proposed_result_text(item, formatter_name),
        "target": _target_to_dict(target) if target is not None else None,
        "candidates": [_target_to_dict(candidate) for candidate in candidates],
        "target_inferred_from_sets_reps": target_inferred_from_sets_reps,
        "warnings": warnings,
        "blockers": blockers,
    }


def _candidate_targets(
    item: HevyAppWorkoutItem,
    true_coach_workout: TrueCoachWorkout | None,
    tracker_workout: TrackerWorkout | None,
) -> list[TrueCoachWorkoutItem]:
    if true_coach_workout is None:
        return []
    exercise = item.exercise if isinstance(item.exercise, HevyAppExercise) else None
    if exercise is None:
        return []

    candidates = _tracker_candidate_targets(tracker_workout, exercise)
    if not candidates:
        candidates = _true_coach_candidate_targets(true_coach_workout, item, exercise)
    candidates = _sort_targets(candidates)
    matching_sets_reps_candidates = _targets_matching_sets_and_reps(item, candidates)
    if len(matching_sets_reps_candidates) == 1:
        return matching_sets_reps_candidates
    return candidates


def _tracker_candidate_targets(
    tracker_workout: TrackerWorkout | None,
    exercise: HevyAppExercise,
) -> list[TrueCoachWorkoutItem]:
    if tracker_workout is None:
        return []
    candidates: list[TrueCoachWorkoutItem] = []
    for tracker_item in tracker_workout.workout_items:
        if tracker_item.hevy_app_id is not None:
            continue
        if tracker_item.exercise.hevy_app_id != exercise.id:
            continue
        if isinstance(tracker_item.true_coach, TrueCoachWorkoutItem):
            candidates.append(tracker_item.true_coach)
    return candidates


def _true_coach_candidate_targets(
    true_coach_workout: TrueCoachWorkout,
    item: HevyAppWorkoutItem,
    exercise: HevyAppExercise,
) -> list[TrueCoachWorkoutItem]:
    return [
        tc_item
        for tc_item in true_coach_workout.workout_items
        if _is_same_hevy_exercise(tc_item, exercise) or tc_item.name == item.name
    ]


def _is_same_hevy_exercise(
    true_coach_item: TrueCoachWorkoutItem,
    exercise: HevyAppExercise,
) -> bool:
    return true_coach_item.exercise is not None and true_coach_item.exercise.hevy_app is exercise


def _sort_targets(candidates: list[TrueCoachWorkoutItem]) -> list[TrueCoachWorkoutItem]:
    return sorted(candidates, key=lambda row: (row.position is None, row.position or 0, row.id))


def _sort_items(workout: HevyAppWorkout) -> list[HevyAppWorkoutItem]:
    return sorted(workout.workout_items, key=lambda row: (row.index, row.id))


def _sort_sets(item: HevyAppWorkoutItem) -> list[HevyAppSets]:
    return sorted(item.sets, key=lambda row: row.index)


def _targets_matching_sets_and_reps(
    item: HevyAppWorkoutItem,
    candidates: list[TrueCoachWorkoutItem],
) -> list[TrueCoachWorkoutItem]:
    if len(candidates) <= 1:
        return candidates
    performed_signature = _performed_sets_reps_signature(item)
    if performed_signature is None:
        return []
    return [
        candidate
        for candidate in candidates
        if _prescribed_sets_reps_signature(candidate.info or "") == performed_signature
    ]


def _is_repeated_performed_exercise(item: HevyAppWorkoutItem) -> bool:
    exercise_id = item.exercise_id
    if exercise_id is None or item.workout is None:
        return False
    return (
        sum(
            1
            for workout_item in item.workout.workout_items
            if workout_item.exercise_id == exercise_id
        )
        > 1
    )


def _performed_sets_reps_signature(item: HevyAppWorkoutItem) -> tuple[int, int] | None:
    sets = _sort_sets(item)
    if not sets or any(set_.reps is None for set_ in sets):
        return None
    reps = {set_.reps for set_ in sets}
    if len(reps) != 1:
        return None
    return (len(sets), int(next(iter(reps))))


def _prescribed_sets_reps_signature(info: str) -> tuple[int, int] | None:
    match = PRESCRIBED_SETS_REPS_PATTERN.search(info)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)))


def _exercise_type(exercise: HevyAppExercise | None) -> str | None:
    if exercise is None:
        return None
    return cast(str, exercise.type)


def _formatter_name(exercise_type: str | None) -> str | None:
    if exercise_type in RESULT_FORMATTERS:
        return exercise_type
    return None


def _item_blockers(
    exercise: HevyAppExercise | None,
    exercise_type: str | None,
    true_coach_workout: TrueCoachWorkout | None,
) -> list[str]:
    blockers: list[str] = []
    if true_coach_workout is None:
        blockers.append("Missing True Coach Workout link for Hevy Workout")
    if exercise is None:
        blockers.append("Missing Hevy exercise template for performed Hevy item")
    elif _formatter_name(exercise_type) is None:
        blockers.append(
            f"Unsupported Hevy exercise type for True Coach result formatting: {exercise_type}"
        )
    return blockers


def _target_blockers(
    target: TrueCoachWorkoutItem | None,
    candidates: list[TrueCoachWorkoutItem],
    target_inferred_from_sets_reps: bool,
) -> list[str]:
    if target is not None:
        return []
    if target_inferred_from_sets_reps:
        return []
    if len(candidates) > 1:
        return [
            f"Ambiguous True Coach target for unlinked performed Hevy item: "
            f"{len(candidates)} candidates"
        ]
    return ["Missing True Coach Workout Item link for performed Hevy item"]


def _item_warnings(
    target: TrueCoachWorkoutItem | None,
    candidates: list[TrueCoachWorkoutItem],
) -> list[str]:
    if target is None and len(candidates) == 1:
        return ["Candidate True Coach target found, but the performed Hevy item is not linked"]
    return []


def _proposed_result_text(item: HevyAppWorkoutItem, formatter_name: str | None) -> str | None:
    if formatter_name is None:
        return None
    formatter = RESULT_FORMATTERS[formatter_name]
    return formatter(cast(list[HevySet], _sort_sets(item))).strip()


def _plan(
    workout: HevyAppWorkout,
    true_coach_workout: TrueCoachWorkout | None,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    blockers = [blocker for item in items for blocker in item["blockers"]]
    warnings = [warning for item in items for warning in item["warnings"]]
    return {
        "workout": {
            "hevy_workout_id": workout.id,
            "title": workout.title,
            "true_coach_workout_id": true_coach_workout.id if true_coach_workout else None,
            "true_coach_title": true_coach_workout.title if true_coach_workout else None,
        },
        "target_items": _target_items_to_dict(true_coach_workout),
        "items": items,
        "blockers": blockers,
        "warnings": warnings,
    }


def _hevy_exercise_to_dict(exercise: HevyAppExercise | None) -> dict[str, Any] | None:
    if exercise is None:
        return None
    return {
        "id": exercise.id,
        "name": exercise.name,
        "type": exercise.type,
        "equipment": exercise.equipment,
    }


def _target_to_dict(item: TrueCoachWorkoutItem) -> dict[str, Any]:
    return {
        "true_coach_workout_item_id": item.id,
        "workout_id": item.workout_id,
        "name": item.name,
        "position": item.position,
        "info": item.info or "",
        "is_circuit": item.is_circuit,
        "state": item.state,
        "assessment_id": item.assessment_id,
        "exercise_id": item.exercise_id,
    }


def _target_items_to_dict(
    true_coach_workout: TrueCoachWorkout | None,
) -> list[dict[str, Any]]:
    if true_coach_workout is None:
        return []
    return [_target_to_dict(item) for item in _sort_targets(list(true_coach_workout.workout_items))]


def _set_to_dict(set_: HevyAppSets) -> dict[str, Any]:
    return {
        "index": set_.index,
        "type": set_.type,
        "weight_kg": set_.weight_kg,
        "reps": set_.reps,
        "distance_meters": set_.distance_meters,
        "duration_seconds": set_.duration_seconds,
        "rpe": set_.rpe,
    }
