"""Migrate logged Hevy workout items from one exercise template to another."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from fitness_tracker.apis.hevy_app.types import Workout
from fitness_tracker.database import Store
from fitness_tracker.database.models import Exercise
from fitness_tracker.database.models.hevy_app import (
    HevyAppExercise,
    HevyAppWorkout,
    HevyAppWorkoutItem,
)
from fitness_tracker.database.tx import Tx


class HevyWorkoutClient(Protocol):
    """Subset of the Hevy workout client needed by this migration."""

    def get_workout(self, workout_id: str) -> Workout | None:
        """Fetch a workout by ID.

        Args:
            workout_id (str): Hevy workout ID.

        Returns:
            Workout | None: Matching workout if found.
        """

    def update_workout(self, workout_id: str, workout: Workout) -> Workout | None:
        """Replace a workout by ID.

        Args:
            workout_id (str): Hevy workout ID.
            workout (Workout): Replacement workout payload.

        Returns:
            Workout | None: Updated workout if returned by the API.
        """


class MigrationError(RuntimeError):
    """Raised when a migration cannot be planned or applied safely."""


@dataclass(frozen=True)
class ExerciseTemplateSummary:
    """Small printable summary of a Hevy exercise template."""

    id: str
    name: str
    type: str
    equipment: str
    is_default: bool


@dataclass(frozen=True)
class WorkoutConflict:
    """A workout that already contains both source and target templates."""

    workout_id: str
    title: str
    start_time: str
    source_items: int
    target_items: int


@dataclass(frozen=True)
class MigrationPlan:
    """Read-only plan for a Hevy exercise template migration."""

    source: ExerciseTemplateSummary
    target: ExerciseTemplateSummary
    affected_items: int
    affected_workouts: int
    target_existing_items: int
    target_existing_workouts: int
    first_start_time: str | None
    last_start_time: str | None
    conflicts: list[WorkoutConflict]
    workout_ids: list[str]


@dataclass(frozen=True)
class WorkoutMigrationResult:
    """Result for one Hevy API workout update."""

    workout_id: str
    replaced_exercises: int


@dataclass(frozen=True)
class MigrationResult:
    """Result of an applied migration."""

    plan: MigrationPlan
    api_updates: list[WorkoutMigrationResult]
    db_workout_items_updated: int
    tracker_exercise_id: int | None


class HevyExerciseTemplateMigrationService:
    """Plan and apply a Hevy exercise template migration."""

    def __init__(self, store: Store, hevy_workouts: HevyWorkoutClient | None = None) -> None:
        """Create the service.

        Args:
            store (Store): Database access.
            hevy_workouts (HevyWorkoutClient | None): Hevy workouts client. Required
                only when applying API updates.
        """
        self._store = store
        self._hevy_workouts = hevy_workouts

    def plan(  # noqa: PLR0915
        self, source_id: str, target_id: str, *, force: bool = False
    ) -> MigrationPlan:
        """Build and validate a migration plan without mutating anything.

        Args:
            source_id (str): Hevy exercise template ID to replace.
            target_id (str): Hevy exercise template ID to use instead.
            force (bool): Allow mismatched source and target type/equipment.

        Returns:
            MigrationPlan: Validated migration plan.

        Raises:
            MigrationError: If source/target templates are invalid or unsafe.
        """
        with self._store.unit_of_work() as uow:
            source = uow.session.get(HevyAppExercise, id=source_id)
            target = uow.session.get(HevyAppExercise, id=target_id)
            if source is None:
                msg = f"Source Hevy exercise template does not exist: {source_id}"
                raise MigrationError(msg)
            if target is None:
                msg = f"Target Hevy exercise template does not exist: {target_id}"
                raise MigrationError(msg)
            if source.id == target.id:
                msg = "Source and target exercise template IDs are the same"
                raise MigrationError(msg)
            if not force and (source.type != target.type or source.equipment != target.equipment):
                msg = (
                    "Source and target type/equipment differ; rerun with --force "
                    f"if this is intentional ({source.type}/{source.equipment} -> "
                    f"{target.type}/{target.equipment})"
                )
                raise MigrationError(msg)

            affected_items = (
                uow.session.query(HevyAppWorkoutItem).filter_by(exercise_id=source_id).count()
            )
            workout_ids = [
                row[0]
                for row in (
                    uow.session.query(HevyAppWorkoutItem.workout_id)
                    .filter_by(exercise_id=source_id)
                    .distinct()
                    .order_by(HevyAppWorkoutItem.workout_id)
                    .all()
                )
            ]
            target_existing_items = (
                uow.session.query(HevyAppWorkoutItem).filter_by(exercise_id=target_id).count()
            )
            target_existing_workouts = (
                uow.session.query(HevyAppWorkoutItem.workout_id)
                .filter_by(exercise_id=target_id)
                .distinct()
                .count()
            )
            date_row = (
                uow.session.query(
                    func.min(HevyAppWorkout.start_time),
                    func.max(HevyAppWorkout.start_time),
                )
                .join(HevyAppWorkoutItem)
                .filter(HevyAppWorkoutItem.exercise_id == source_id)
                .first()
            )
            conflicts = self._find_conflicts(uow, source_id, target_id)

            return MigrationPlan(
                source=_summary(source),
                target=_summary(target),
                affected_items=affected_items,
                affected_workouts=len(workout_ids),
                target_existing_items=target_existing_items,
                target_existing_workouts=target_existing_workouts,
                first_start_time=_stringify_dt(date_row[0] if date_row else None),
                last_start_time=_stringify_dt(date_row[1] if date_row else None),
                conflicts=conflicts,
                workout_ids=workout_ids,
            )

    def apply(  # noqa: PLR0913, PLR0915
        self,
        source_id: str,
        target_id: str,
        *,
        force: bool = False,
        limit: int | None = None,
        backup_path: Path | None = None,
        report_path: Path | None = None,
    ) -> MigrationResult:
        """Apply a migration to Hevy first, then update local database rows.

        Args:
            source_id (str): Hevy exercise template ID to replace.
            target_id (str): Hevy exercise template ID to use instead.
            force (bool): Allow mismatched source and target type/equipment.
            limit (int | None): Maximum number of affected workouts to update.
            backup_path (Path | None): Optional SQLite backup destination.
            report_path (Path | None): Optional JSON migration report destination.

        Returns:
            MigrationResult: API and database update summary.

        Raises:
            MigrationError: If the migration cannot be planned or applied.
        """
        if self._hevy_workouts is None:
            msg = "A Hevy workout client is required when applying a migration"
            raise MigrationError(msg)

        plan = self.plan(source_id, target_id, force=force)
        selected_workout_ids = plan.workout_ids[:limit] if limit is not None else plan.workout_ids
        api_updates = self._apply_hevy_updates(
            self._hevy_workouts,
            selected_workout_ids,
            source_id,
            target_id,
        )

        if backup_path is not None:
            _backup_sqlite_db(self._store, backup_path)

        target_name = plan.target.name
        with self._store.unit_of_work() as uow:
            db_updated = (
                uow.session.query(HevyAppWorkoutItem)
                .filter(
                    HevyAppWorkoutItem.workout_id.in_(selected_workout_ids),
                    HevyAppWorkoutItem.exercise_id == source_id,
                )
                .update(
                    {
                        HevyAppWorkoutItem.exercise_id: target_id,
                        HevyAppWorkoutItem.name: target_name,
                    },
                    synchronize_session=False,
                )
            )
            tracker_row = uow.session.get(Exercise, hevy_app_id=source_id)
            tracker_id = None
            if tracker_row is not None:
                tracker_id = tracker_row.id
                tracker_row.hevy_app_id = target_id
                tracker_row.name = target_name
                uow.session.merge(tracker_row)

        result = MigrationResult(
            plan=plan,
            api_updates=api_updates,
            db_workout_items_updated=db_updated,
            tracker_exercise_id=tracker_id,
        )
        if report_path is not None:
            _write_report(report_path, result)
        return result

    def _apply_hevy_updates(  # noqa: PLR0913
        self,
        client: HevyWorkoutClient,
        workout_ids: list[str],
        source_id: str,
        target_id: str,
    ) -> list[WorkoutMigrationResult]:
        results = []
        for workout_id in workout_ids:
            workout = client.get_workout(workout_id)
            if workout is None:
                msg = f"Hevy workout not found: {workout_id}"
                raise MigrationError(msg)
            replaced = 0
            for exercise in workout.exercises:
                if exercise.exercise_template_id == source_id:
                    exercise.exercise_template_id = target_id
                    replaced += 1
            if replaced == 0:
                if any(
                    exercise.exercise_template_id == target_id for exercise in workout.exercises
                ):
                    results.append(
                        WorkoutMigrationResult(workout_id=workout_id, replaced_exercises=0)
                    )
                    continue
                msg = f"Hevy workout contains neither source nor target template: {workout_id}"
                raise MigrationError(msg)
            client.update_workout(workout_id, workout)
            results.append(
                WorkoutMigrationResult(workout_id=workout_id, replaced_exercises=replaced)
            )
        return results

    def _find_conflicts(
        self,
        uow: Tx,
        source_id: str,
        target_id: str,
    ) -> list[WorkoutConflict]:
        rows = (
            uow.session.query(HevyAppWorkout)
            .options(joinedload(HevyAppWorkout.workout_items))
            .join(HevyAppWorkoutItem)
            .filter(HevyAppWorkoutItem.exercise_id.in_([source_id, target_id]))
            .all()
        )
        conflicts = []
        for workout in rows:
            source_items = sum(1 for item in workout.workout_items if item.exercise_id == source_id)
            target_items = sum(1 for item in workout.workout_items if item.exercise_id == target_id)
            if source_items and target_items:
                conflicts.append(
                    WorkoutConflict(
                        workout_id=workout.id,
                        title=workout.title,
                        start_time=_stringify_dt(workout.start_time) or "",
                        source_items=source_items,
                        target_items=target_items,
                    )
                )
        return sorted(conflicts, key=lambda item: item.start_time, reverse=True)


def _summary(exercise: HevyAppExercise) -> ExerciseTemplateSummary:
    return ExerciseTemplateSummary(
        id=exercise.id,
        name=exercise.name,
        type=exercise.type,
        equipment=exercise.equipment,
        is_default=bool(exercise.default),
    )


def _stringify_dt(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _backup_sqlite_db(store: Store, backup_path: Path) -> None:
    url = str(store._engine.url)  # noqa: SLF001
    if not url.startswith("sqlite:///"):
        msg = "Automatic backups are only supported for sqlite:/// database URLs"
        raise MigrationError(msg)
    source = Path(url.removeprefix("sqlite:///"))
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, backup_path)


def _write_report(report_path: Path, result: MigrationResult) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    payload["created_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
