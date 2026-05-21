"""Mutation side of reviewed True Coach Workout backfill."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from fitness_tracker.apis.hevy_app.types.workout_request_body import PostWorkoutsRequestBody
from fitness_tracker.database import Store
from fitness_tracker.database.models.hevy_app import HevyAppWorkoutItem
from fitness_tracker.database.models.tracker import (
    Exercise as TrackerExercise,
    Sets,
    Workout as TrackerWorkout,
    WorkoutItem as TrackerWorkoutItem,
)
from fitness_tracker.sync.ports import HevyWorkoutWriter
from fitness_tracker.sync_review.workflow import write_json_artifact


class WorkoutBackfillApplyError(Exception):
    """Raised when a Workout backfill request is not safe to apply."""


@dataclass(frozen=True)
class WorkoutBackfillApplyResult:
    """Paths and request body produced for a Workout backfill apply attempt."""

    review_bundle: Any | None
    request_path: Path
    request_body: PostWorkoutsRequestBody
    action: str


@dataclass(frozen=True)
class BackfillLinkContext:
    """Inputs needed to link a remote Hevy Workout to local tracker rows."""

    workout_id: int
    workout: Any
    plan: dict[str, Any]
    decisions: dict[str, Any]


@dataclass(frozen=True)
class CreatedWorkoutItemLinkContext:
    """Inputs needed to link one created Hevy item to a tracker item."""

    tracker_workout: TrackerWorkout
    item: dict[str, Any]
    decisions: dict[str, Any]


class WorkoutBackfillApplyService:
    """Apply reviewed Workout backfill requests and repair local links."""

    def __init__(self, store: Store) -> None:
        """Create the apply service.

        Args:
            store (Store): Local database snapshot.
        """
        self._store = store

    def apply(  # noqa: PLR0913
        self,
        *,
        workout_id: int,
        result: WorkoutBackfillApplyResult,
        workout_writer: HevyWorkoutWriter,
        plan: dict[str, Any],
        decisions: dict[str, Any],
    ) -> WorkoutBackfillApplyResult:
        """Create or repair a remote Hevy Workout for reviewed backfill.

        Args:
            workout_id (int): Source True Coach Workout id.
            result (WorkoutBackfillApplyResult): Validated dry-run request result.
            workout_writer (HevyWorkoutWriter): Hevy Workout mutation port.
            plan (dict[str, Any]): Rendered backfill plan.
            decisions (dict[str, Any]): Editable backfill decisions.

        Returns:
            WorkoutBackfillApplyResult: Apply result with the performed action.
        """
        if self._tracker_workout_is_linked(workout_id):
            return _apply_result_with_action(result, "already_linked")
        existing_remote = _find_remote_backfill(workout_writer, workout_id)
        if existing_remote is not None:
            unlinked = self._sync_and_link_created_workout(
                BackfillLinkContext(
                    workout_id=workout_id,
                    workout=existing_remote,
                    plan=plan,
                    decisions=decisions,
                )
            )
            _raise_for_unlinked_created_rows(result, existing_remote.id, unlinked)
            return _apply_result_with_action(result, "repaired_existing_remote")
        response = workout_writer.create_workout(result.request_body)
        if response and response.workout:
            unlinked = self._sync_and_link_created_workout(
                BackfillLinkContext(
                    workout_id=workout_id,
                    workout=response.workout[0],
                    plan=plan,
                    decisions=decisions,
                )
            )
            _raise_for_unlinked_created_rows(result, response.workout[0].id, unlinked)
        return _apply_result_with_action(result, "created")

    def apply_manual_request(
        self,
        request_path: Path,
        *,
        workout_id: int,
        workout_writer: HevyWorkoutWriter,
    ) -> WorkoutBackfillApplyResult:
        """Create a Hevy Workout from an Agent-edited request artifact.

        Args:
            request_path (Path): Edited Hevy Workout request JSON.
            workout_id (int): Expected source True Coach Workout id marker.
            workout_writer (HevyWorkoutWriter): Hevy Workout mutation port.

        Returns:
            WorkoutBackfillApplyResult: Submitted request body and action.
        """
        request_body = _load_manual_request(request_path)
        _validate_manual_apply_request(request_body, workout_id=workout_id)
        workout_writer.create_workout(request_body)
        return WorkoutBackfillApplyResult(
            review_bundle=None,
            request_path=request_path,
            request_body=request_body,
            action="created",
        )

    def repair_local_links(  # noqa: PLR0913
        self,
        *,
        workout_id: int,
        result: WorkoutBackfillApplyResult,
        workout_writer: HevyWorkoutWriter,
        plan: dict[str, Any],
        decisions: dict[str, Any],
    ) -> WorkoutBackfillApplyResult:
        """Repair local tracker links without creating a remote Hevy Workout.

        Args:
            workout_id (int): Source True Coach Workout id.
            result (WorkoutBackfillApplyResult): Validated dry-run request result.
            workout_writer (HevyWorkoutWriter): Hevy Workout reader port.
            plan (dict[str, Any]): Rendered backfill plan.
            decisions (dict[str, Any]): Editable backfill decisions.

        Returns:
            WorkoutBackfillApplyResult: Repair result with the performed action.

        Raises:
            WorkoutBackfillApplyError: If no linked or marked remote Hevy Workout exists.
        """
        remote = self._linked_remote_workout(workout_id, workout_writer)
        if remote is None:
            remote = _find_remote_backfill(workout_writer, workout_id)
        if remote is None:
            msg = (
                f"No linked or marked remote Hevy Workout found for True Coach Workout {workout_id}"
            )
            raise WorkoutBackfillApplyError(msg)
        unlinked = self._sync_and_link_created_workout(
            BackfillLinkContext(
                workout_id=workout_id,
                workout=remote,
                plan=plan,
                decisions=decisions,
            )
        )
        _raise_for_unlinked_created_rows(result, remote.id, unlinked)
        return _apply_result_with_action(result, "repaired_existing_remote")

    def _tracker_workout_is_linked(self, workout_id: int) -> bool:
        with self._store.unit_of_work() as uow:
            tracker_workout = uow.tracker.get_workout(true_coach_id=workout_id)
            return bool(tracker_workout and tracker_workout.hevy_app_id)

    def _linked_remote_workout(
        self,
        workout_id: int,
        workout_writer: HevyWorkoutWriter,
    ) -> Any | None:
        getter = getattr(workout_writer, "get_workout", None)
        if getter is None:
            return None
        with self._store.unit_of_work() as uow:
            tracker_workout = uow.tracker.get_workout(true_coach_id=workout_id)
            hevy_app_id = tracker_workout.hevy_app_id if tracker_workout is not None else None
        return getter(hevy_app_id) if hevy_app_id else None

    def _sync_and_link_created_workout(self, context: BackfillLinkContext) -> list[int]:  # noqa: PLR0915
        unlinked_tracker_item_ids: list[int] = []
        with self._store.unit_of_work() as uow:
            uow.hevy.add_workout(context.workout)
            tracker_workout = uow.tracker.get_workout(true_coach_id=context.workout_id)
            if tracker_workout is None:
                return [
                    item["tracker_workout_item_id"]
                    for item in _requestable_plan_items(context.plan, context.decisions)
                ]
            tracker_workout.hevy_app_id = context.workout.id
            tracker_workout.start_date = datetime.fromisoformat(context.workout.start_time)
            tracker_workout.end_date = datetime.fromisoformat(context.workout.end_time)
            uow.session.flush()
            for request_index, item in enumerate(
                _requestable_plan_items(context.plan, context.decisions)
            ):
                tracker_item = _tracker_item_for_created_hevy_row(
                    uow.session,
                    CreatedWorkoutItemLinkContext(
                        tracker_workout=tracker_workout,
                        item=item,
                        decisions=context.decisions,
                    ),
                )
                hevy_item = uow.session.execute(
                    select(HevyAppWorkoutItem).where(
                        HevyAppWorkoutItem.workout_id == context.workout.id,
                        HevyAppWorkoutItem.index == request_index,
                    )
                ).scalar_one_or_none()
                if tracker_item is None or hevy_item is None:
                    unlinked_tracker_item_ids.append(item["tracker_workout_item_id"])
                    continue
                tracker_item.hevy_app_id = hevy_item.id
                local_sets = sorted(tracker_item.sets, key=lambda row: row.index)
                hevy_sets = sorted(hevy_item.sets, key=lambda row: row.index)
                if not local_sets and item.get("sets"):
                    local_sets = _create_missing_local_sets(tracker_item, item, hevy_sets)
                    uow.session.flush()
                if len(local_sets) != len(hevy_sets):
                    unlinked_tracker_item_ids.append(item["tracker_workout_item_id"])
                for local_set, hevy_set in zip(
                    local_sets,
                    hevy_sets,
                    strict=False,
                ):
                    local_set.hevy_app_id = hevy_set.id
        return unlinked_tracker_item_ids


def _tracker_item_for_created_hevy_row(
    session: Any,
    context: CreatedWorkoutItemLinkContext,
) -> TrackerWorkoutItem | None:
    item = context.item
    if not _is_expanded_circuit_movement_item(item) and not _is_split_choice_performance_item(item):
        return session.get(TrackerWorkoutItem, id=item["tracker_workout_item_id"])
    template_id = _request_exercise_template_id(item, context.decisions)
    if template_id is None:
        return None
    exercise = _tracker_exercise_for_synthetic_item(
        session=session,
        name=item["name"],
        hevy_app_id=template_id,
    )
    tracker_item = _existing_synthetic_tracker_item(
        session,
        context,
        exercise_id=exercise.id,
    )
    if tracker_item is not None:
        return tracker_item
    tracker_item = TrackerWorkoutItem(
        workout_id=context.tracker_workout.id,
        position=item["position"],
        exercise_id=exercise.id,
        true_coach_id=item["source_id"],
    )
    session.add(tracker_item)
    session.flush()
    return tracker_item


def _tracker_exercise_for_synthetic_item(
    *,
    session: Any,
    name: str,
    hevy_app_id: str,
) -> TrackerExercise:
    linked_exercises = list(
        session.execute(
            select(TrackerExercise)
            .where(TrackerExercise.hevy_app_id == hevy_app_id)
            .order_by(TrackerExercise.id)
        ).scalars()
    )
    if linked_exercises:
        return _preferred_tracker_exercise(linked_exercises, name=name)
    named_exercises = list(
        session.execute(
            select(TrackerExercise).where(TrackerExercise.name == name).order_by(TrackerExercise.id)
        ).scalars()
    )
    if named_exercises:
        exercise = named_exercises[0]
        exercise.hevy_app_id = hevy_app_id
        session.flush()
        return exercise
    exercise = TrackerExercise(name=name, hevy_app_id=hevy_app_id)
    session.add(exercise)
    session.flush()
    return exercise


def _preferred_tracker_exercise(
    exercises: list[TrackerExercise],
    *,
    name: str,
) -> TrackerExercise:
    normalized_name = _normalized_exercise_name(name)
    for exercise in exercises:
        if _normalized_exercise_name(exercise.name) == normalized_name:
            return exercise
    return exercises[0]


def _normalized_exercise_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _existing_synthetic_tracker_item(
    session: Any,
    context: CreatedWorkoutItemLinkContext,
    *,
    exercise_id: int,
) -> TrackerWorkoutItem | None:
    source_id = context.item["source_id"]
    if source_id is None:
        return None
    return session.execute(
        select(TrackerWorkoutItem).where(
            TrackerWorkoutItem.workout_id == context.tracker_workout.id,
            TrackerWorkoutItem.true_coach_id == source_id,
            TrackerWorkoutItem.exercise_id == exercise_id,
        )
    ).scalar_one_or_none()


def _create_missing_local_sets(
    tracker_item: TrackerWorkoutItem,
    item: dict[str, Any],
    hevy_sets: list[Any],
) -> list[Sets]:
    local_sets = []
    for index, set_data in enumerate(item.get("sets", [])):
        hevy_set = hevy_sets[index] if index < len(hevy_sets) else None
        local_set = Sets(
            workout_item_id=tracker_item.id,
            index=index,
            type=set_data["type"],
            weight_kg=set_data.get("weight_kg"),
            reps=set_data.get("reps"),
            distance_meters=set_data.get("distance_meters"),
            duration_seconds=set_data.get("duration_seconds"),
            rpe=set_data.get("rpe"),
            hevy_app_id=hevy_set.id if hevy_set is not None else None,
        )
        tracker_item.sets.append(local_set)
        local_sets.append(local_set)
    return local_sets


def _find_remote_backfill(workout_writer: HevyWorkoutWriter, workout_id: int) -> Any | None:
    finder = getattr(workout_writer, "find_workout_by_true_coach_id", None)
    if finder is None:
        return None
    return finder(workout_id)


def _raise_for_unlinked_created_rows(
    result: WorkoutBackfillApplyResult,
    remote_workout_id: str,
    unlinked_tracker_workout_item_ids: list[int],
) -> None:
    if not unlinked_tracker_workout_item_ids:
        return
    if result.review_bundle is not None:
        recovery_path = result.review_bundle.directory / "backfill-recovery.json"
        write_json_artifact(
            recovery_path,
            {
                "true_coach_workout_id": _source_workout_id(result.request_body),
                "remote_hevy_workout_id": remote_workout_id,
                "request_path": str(result.request_path),
                "plan_path": str(result.review_bundle.plan_path),
                "unlinked_tracker_workout_item_ids": unlinked_tracker_workout_item_ids,
            },
        )
    msg = "Could not link all created Hevy rows; recovery artifact written"
    raise WorkoutBackfillApplyError(msg)


def _apply_result_with_action(
    result: WorkoutBackfillApplyResult,
    action: str,
) -> WorkoutBackfillApplyResult:
    return WorkoutBackfillApplyResult(
        review_bundle=result.review_bundle,
        request_path=result.request_path,
        request_body=result.request_body,
        action=action,
    )


def _source_workout_id(request_body: PostWorkoutsRequestBody) -> int | None:
    marker = re.search(r"True Coach Workout (\d+)", request_body.workout.description or "")
    return int(marker.group(1)) if marker else None


def _requestable_plan_items(
    plan: dict[str, Any],
    decisions: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        item
        for item in plan.get("items", [])
        if item.get("sets") and _request_exercise_template_id(item, decisions) is not None
    ]


def _request_exercise_template_id(
    item: dict[str, Any],
    decisions: dict[str, Any] | None,
) -> str | None:
    if item["selected_hevy_template"] is not None:
        return item["selected_hevy_template"]["id"]
    if decisions is None:
        return None
    decision = _manual_template_decision_for(item, decisions)
    if decision is None:
        return None
    selected_template_id = decision.get("selected_hevy_template_id")
    return selected_template_id if isinstance(selected_template_id, str) else None


def _manual_template_decision_for(
    item: dict[str, Any],
    decisions: dict[str, Any],
) -> dict[str, Any] | None:
    if item.get("choice_decision_reason") is not None:
        return _choice_decision_for(
            decisions,
            {
                "source_id": item["source_id"],
                "performed_name": item["name"],
            },
        )
    if item.get("circuit_decision_reason") is not None:
        return _circuit_decision_for(
            decisions,
            {
                "source_id": item["source_id"],
                "movement_name": item["name"],
            },
        )
    return None


def _choice_decision_for(
    decisions: dict[str, Any],
    required_choice: dict[str, Any],
) -> dict[str, Any] | None:
    return _decision_for(
        decisions=decisions,
        required=required_choice,
        lookup=("choice_items", "performed_name"),
    )


def _circuit_decision_for(
    decisions: dict[str, Any],
    required_circuit: dict[str, Any],
) -> dict[str, Any] | None:
    return _decision_for(
        decisions=decisions,
        required=required_circuit,
        lookup=("circuit_items", "movement_name"),
    )


def _decision_for(
    *,
    decisions: dict[str, Any],
    required: dict[str, Any],
    lookup: tuple[str, str],
) -> dict[str, Any] | None:
    section, name_key = lookup
    decision_items = decisions.get(section)
    if not isinstance(decision_items, list):
        return None
    for decision in decision_items:
        if not isinstance(decision, dict):
            continue
        if (
            decision.get("source_id") == required["source_id"]
            and decision.get(name_key) == required[name_key]
        ):
            return decision
    return None


def _is_expanded_circuit_movement_item(item: dict[str, Any]) -> bool:
    return (
        "movement_target" in item
        and "original_prescription_text" in item
        and "completed_round_count" in item
    )


def _is_split_choice_performance_item(item: dict[str, Any]) -> bool:
    return bool(item.get("split_choice_performance"))


def _load_manual_request(request_path: Path) -> PostWorkoutsRequestBody:
    try:
        data = json.loads(request_path.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"Could not read Hevy Workout request file {request_path}: {exc}"
        raise WorkoutBackfillApplyError(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"Could not parse Hevy Workout request file {request_path}: {exc}"
        raise WorkoutBackfillApplyError(msg) from exc
    try:
        return PostWorkoutsRequestBody(**data)
    except ValueError as exc:
        msg = f"Invalid Hevy Workout request file {request_path}: {exc}"
        raise WorkoutBackfillApplyError(msg) from exc


def _validate_manual_apply_request(
    request_body: PostWorkoutsRequestBody,
    *,
    workout_id: int,
) -> None:
    blockers: list[str] = []
    workout = request_body.workout
    if not workout.start_time or not workout.end_time:
        blockers.append("Missing required Hevy Workout timestamps")
    marker = f"True Coach Workout {workout_id}"
    if marker not in (workout.description or ""):
        blockers.append(f"Missing source True Coach Workout id marker: {workout_id}")
    if not workout.exercises:
        blockers.append("No performed exercise blocks are requestable for Workout backfill")
    for index, exercise in enumerate(workout.exercises, start=1):
        if not exercise.exercise_template_id:
            blockers.append(f"Missing Hevy template mapping for request exercise {index}")
        if not exercise.sets:
            blockers.append(f"Invalid set payload for request exercise {index}: no sets")
    if blockers:
        raise WorkoutBackfillApplyError("; ".join(blockers))
