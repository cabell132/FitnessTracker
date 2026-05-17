"""Build read-only True Coach to Hevy sync review bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fitness_tracker.apis.hevy_app.types import PostRoutinesRequestSet
from fitness_tracker.database import Store
from fitness_tracker.database.models import HevyAppExercise, TrueCoachExercise
from fitness_tracker.database.models.true_coach import TrueCoachWorkout, TrueCoachWorkoutItem
from fitness_tracker.database.uow import UnitOfWork
from fitness_tracker.sync._true_coach_html import parse_prescribed_sets

SET_DISPLAY_KEYS = ("type", "weight_kg", "reps", "distance_meters", "duration_seconds")


class SyncReviewError(Exception):
    """Raised when a requested sync review cannot be produced."""


@dataclass(frozen=True)
class ReviewBundle:
    """Paths written for a sync review."""

    directory: Path
    report_path: Path
    plan_path: Path


@dataclass(frozen=True)
class ReviewItem:
    """One True Coach workout item review row."""

    source_id: int
    name: str
    info: str
    selected_hevy_template: HevyAppExercise | None
    proposed_sets: list[PostRoutinesRequestSet]
    warnings: list[str]


class TrueCoachToHevyReviewService:
    """Create a review bundle for one True Coach workout without writing to Hevy."""

    def __init__(self, store: Store, output_root: Path = Path("reports")) -> None:
        """Create the service.

        Args:
            store (Store): Local database snapshot.
            output_root (Path): Root under which ``sync-review`` reports are written.
        """
        self._store = store
        self._output_root = output_root

    def write_review(self, workout_id: int) -> ReviewBundle:
        """Write ``report.md`` and ``plan.json`` for one True Coach workout.

        Args:
            workout_id (int): True Coach workout id.

        Returns:
            ReviewBundle: Paths written by the service.

        Raises:
            SyncReviewError: If the workout does not exist in the local snapshot.
        """
        with self._store.unit_of_work() as uow:
            workout = uow.tc_get_workout(id=workout_id)
            if workout is None:
                msg = f"True Coach workout {workout_id} was not found in the local DB"
                raise SyncReviewError(msg)

            items = [
                self._review_item(uow, item)
                for item in sorted(
                    workout.workout_items,
                    key=lambda item: (item.position is None, item.position or 0, item.id),
                )
            ]
            plan = self._plan(workout, items)
            report = self._report(workout, items)

        bundle_dir = self._output_root / "sync-review" / "truecoach-to-hevy" / str(workout_id)
        bundle_dir.mkdir(parents=True, exist_ok=True)
        report_path = bundle_dir / "report.md"
        plan_path = bundle_dir / "plan.json"
        report_path.write_text(report, encoding="utf-8")
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return ReviewBundle(directory=bundle_dir, report_path=report_path, plan_path=plan_path)

    def _review_item(self, uow: UnitOfWork, item: TrueCoachWorkoutItem) -> ReviewItem:
        template = self._selected_template(uow, item)
        warnings = []
        if template is None:
            warnings.append("No linked Hevy exercise template found.")
        return ReviewItem(
            source_id=item.id,
            name=item.name,
            info=item.info or "",
            selected_hevy_template=template,
            proposed_sets=_parse_proposed_sets(item.info or ""),
            warnings=warnings,
        )

    def _selected_template(
        self,
        uow: UnitOfWork,
        item: TrueCoachWorkoutItem,
    ) -> HevyAppExercise | None:
        exercise = item.exercise
        if isinstance(exercise, TrueCoachExercise) and isinstance(
            exercise.hevy_app, HevyAppExercise
        ):
            return exercise.hevy_app
        if item.tracker and isinstance(item.tracker.exercise.hevy_app, HevyAppExercise):
            return item.tracker.exercise.hevy_app
        tracker_exercise = uow.tracker_get_exercise(name=item.name)
        if tracker_exercise and isinstance(tracker_exercise.hevy_app, HevyAppExercise):
            return tracker_exercise.hevy_app
        return None

    def _plan(self, workout: TrueCoachWorkout, items: list[ReviewItem]) -> dict[str, Any]:
        return {
            "workout": {
                "id": workout.id,
                "title": workout.title,
                "due": workout.due.isoformat() if workout.due else None,
                "state": workout.state,
            },
            "items": [self._plan_item(item) for item in items],
        }

    def _plan_item(self, item: ReviewItem) -> dict[str, Any]:
        template = item.selected_hevy_template
        return {
            "source_id": item.source_id,
            "name": item.name,
            "info": item.info,
            "selected_hevy_template": _template_to_dict(template),
            "proposed_sets": [_set_to_dict(proposed_set) for proposed_set in item.proposed_sets],
            "warnings": item.warnings,
            "blockers": [],
        }

    def _report(self, workout: TrueCoachWorkout, items: list[ReviewItem]) -> str:
        lines = [
            f"# True Coach to Hevy Sync Review: {workout.id}",
            "",
            f"Workout: {workout.title or 'Untitled'}",
            f"Due: {workout.due.isoformat() if workout.due else 'unknown'}",
            "",
        ]
        for index, item in enumerate(items, start=1):
            lines.extend(self._report_item(index, item))
        return "\n".join(lines).rstrip() + "\n"

    def _report_item(self, index: int, item: ReviewItem) -> list[str]:
        template = item.selected_hevy_template
        lines = [
            f"## {index}. {item.name}",
            "",
            f"Source ID: {item.source_id}",
            f"Info: {item.info or 'none'}",
            _format_template(template),
            "Proposed sets:",
        ]
        if item.proposed_sets:
            lines.extend(f"- {_format_set(proposed_set)}" for proposed_set in item.proposed_sets)
        else:
            lines.append("- unavailable")
        if item.warnings:
            lines.extend(f"WARNING: {warning}" for warning in item.warnings)
        lines.append("Blockers: none")
        lines.append("")
        return lines


def _parse_proposed_sets(info: str) -> list[PostRoutinesRequestSet]:
    return parse_prescribed_sets(info)


def _template_to_dict(template: HevyAppExercise | None) -> dict[str, str | None] | None:
    if template is None:
        return None
    return {
        "id": template.id,
        "name": template.name,
        "type": template.type,
        "equipment": template.equipment,
    }


def _format_template(template: HevyAppExercise | None) -> str:
    if template is None:
        return "Selected Hevy template: unknown"
    return f"Selected Hevy template: {template.name} ({template.id})"


def _set_to_dict(value: PostRoutinesRequestSet) -> dict[str, int | float | str]:
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    return value.dict(exclude_none=True)


def _format_set(value: PostRoutinesRequestSet) -> str:
    data = _set_to_dict(value)
    return "; ".join(f"{key}: {data[key]}" for key in SET_DISPLAY_KEYS if key in data)
