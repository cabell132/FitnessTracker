"""Build deterministic True Coach Workout backfill review bundles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fitness_tracker.apis.hevy_app.types.workout_request_body import PostWorkoutsRequestBody
from fitness_tracker.apis.hevy_app.types.workout_requests import (
    PostWorkoutsRequestExercise,
    PostWorkoutsRequestSet,
)
from fitness_tracker.database import Store
from fitness_tracker.database.models.hevy_app import HevyAppExercise
from fitness_tracker.database.models.tracker import Sets, Workout as TrackerWorkout
from fitness_tracker.database.models.true_coach import TrueCoachWorkout


class WorkoutBackfillReviewError(Exception):
    """Raised when a Workout backfill review cannot be produced."""


@dataclass(frozen=True)
class WorkoutBackfillReviewBundle:
    """Paths written for one Workout backfill review."""

    directory: Path
    report_path: Path
    plan_path: Path
    request_path: Path


@dataclass(frozen=True)
class WorkoutBackfillReviewArtifacts:
    """Rendered artifacts for one Workout backfill review."""

    plan: dict[str, Any]
    request: PostWorkoutsRequestBody
    report: str


@dataclass(frozen=True)
class BackfillReviewItem:
    """One performed item planned for a Hevy Workout draft."""

    source_id: int | None
    tracker_workout_item_id: int
    position: int
    name: str
    info: str
    comment: str
    selected_hevy_template: HevyAppExercise | None
    sets: list[PostWorkoutsRequestSet]
    notes: str
    warnings: list[str]
    blockers: list[str]


class TrueCoachWorkoutBackfillReviewService:
    """Create a review bundle for one completed True Coach Workout backfill."""

    def __init__(self, store: Store, output_root: Path = Path("reports")) -> None:
        """Create the service.

        Args:
            store (Store): Local database snapshot.
            output_root (Path): Root under which review artifacts are written.
        """
        self._store = store
        self._output_root = output_root

    def write_review(self, workout_id: int) -> WorkoutBackfillReviewBundle:
        """Write deterministic plan, draft Hevy Workout request, and report.

        Args:
            workout_id (int): True Coach Workout id.

        Returns:
            WorkoutBackfillReviewBundle: Paths written by the service.
        """
        artifacts = self._build_artifacts(workout_id)
        bundle_dir, plan_path, request_path, report_path = _bundle_paths(
            self._output_root, workout_id
        )
        plan_path.write_text(
            json.dumps(artifacts.plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        request_path.write_text(
            json.dumps(artifacts.request.model_dump(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report_path.write_text(artifacts.report, encoding="utf-8")
        return WorkoutBackfillReviewBundle(
            directory=bundle_dir,
            report_path=report_path,
            plan_path=plan_path,
            request_path=request_path,
        )

    def _build_artifacts(self, workout_id: int) -> WorkoutBackfillReviewArtifacts:
        with self._store.unit_of_work() as uow:
            workout = uow.true_coach.get_workout(id=workout_id)
            if workout is None:
                msg = f"True Coach workout {workout_id} was not found in the local DB"
                raise WorkoutBackfillReviewError(msg)
            tracker_workout = workout.tracker
            if not isinstance(tracker_workout, TrackerWorkout):
                msg = f"True Coach workout {workout_id} has no local tracker Workout row"
                raise WorkoutBackfillReviewError(msg)

            items = [
                _review_item(item)
                for item in sorted(
                    tracker_workout.workout_items,
                    key=lambda item: (item.position, item.id),
                )
            ]
            plan = _plan(workout, tracker_workout, items)
            return WorkoutBackfillReviewArtifacts(
                plan=plan,
                request=_build_hevy_workout_request(plan),
                report=_report(workout, plan),
            )


def _bundle_paths(
    output_root: Path,
    workout_id: int,
) -> tuple[Path, Path, Path, Path]:
    bundle_dir = output_root / "sync-review" / "truecoach-workout-backfill" / str(workout_id)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    return (
        bundle_dir,
        bundle_dir / "plan.json",
        bundle_dir / "hevy-workout-request.json",
        bundle_dir / "report.md",
    )


def _review_item(item: Any) -> BackfillReviewItem:
    true_coach_item = item.true_coach
    template = item.exercise.hevy_app if item.exercise is not None else None
    sets = [
        _set_to_request_set(set_row) for set_row in sorted(item.sets, key=lambda row: row.index)
    ]
    info = true_coach_item.info or "" if true_coach_item is not None else ""
    comment = true_coach_item.comment or "" if true_coach_item is not None else ""
    name = true_coach_item.name if true_coach_item is not None else item.exercise.name
    if not sets and _is_down_regulate_item(name):
        sets = [PostWorkoutsRequestSet(type="normal", duration_seconds=240)]
    blockers: list[str] = []
    warnings: list[str] = []
    is_placeholder_rest = not sets and _is_placeholder_rest_item(
        name=name,
        info=info,
        comment=comment,
    )
    if template is None and not is_placeholder_rest:
        blockers.append(f"Missing Hevy template mapping for performed item: {item.exercise.name}")
    if not sets:
        if is_placeholder_rest:
            warnings.append(
                "Placeholder rest item has no structured Sets rows; omitted from draft request."
            )
        else:
            warnings.append("No structured tracker Sets rows found; omitted from draft request.")
    return BackfillReviewItem(
        source_id=true_coach_item.id if true_coach_item is not None else None,
        tracker_workout_item_id=item.id,
        position=item.position,
        name=name,
        info=info,
        comment=comment,
        selected_hevy_template=template if isinstance(template, HevyAppExercise) else None,
        sets=sets,
        notes=_notes(
            info=info,
            comment=comment,
            sets=sets,
        ),
        warnings=warnings,
        blockers=blockers,
    )


def _is_down_regulate_item(name: str) -> bool:
    return name.casefold().strip() == "down regulate"


def _is_placeholder_rest_item(*, name: str, info: str, comment: str) -> bool:
    if comment.strip():
        return False
    normalized_name = name.casefold().strip()
    normalized_info = info.casefold().strip()
    return normalized_name == "rest" or normalized_info in {"rest", "placeholder"}


def _set_to_request_set(set_row: Sets) -> PostWorkoutsRequestSet:
    return PostWorkoutsRequestSet(
        type=set_row.type,
        weight_kg=set_row.weight_kg,
        reps=set_row.reps,
        distance_meters=set_row.distance_meters,
        duration_seconds=set_row.duration_seconds,
        rpe=set_row.rpe,
    )


def _notes(*, info: str, comment: str, sets: list[PostWorkoutsRequestSet]) -> str:
    parts = []
    if info and not sets:
        parts.append(f"Coach prescription: {info}")
    if comment and not _comment_duplicates_structured_sets(comment, sets):
        parts.append(f"Athlete comment: {comment}")
    return "\n".join(parts)


def _comment_duplicates_structured_sets(
    comment: str,
    sets: list[PostWorkoutsRequestSet],
) -> bool:
    if not sets:
        return False
    normalized_comment = _normalize_metric_text(comment)
    if not normalized_comment:
        return False
    structured_tokens = [_set_metric_token(set_row) for set_row in sets]
    return bool(structured_tokens) and normalized_comment == _normalize_metric_text(
        ", ".join(token for token in structured_tokens if token)
    )


def _set_metric_token(set_row: PostWorkoutsRequestSet) -> str:
    parts = []
    if set_row.weight_kg is not None:
        parts.append(f"{set_row.weight_kg:g}kg")
    if set_row.reps is not None:
        parts.append(f"x {set_row.reps:g}")
    if set_row.distance_meters is not None:
        parts.append(f"{set_row.distance_meters:g}m")
    if set_row.duration_seconds is not None:
        parts.append(f"{set_row.duration_seconds:g}s")
    if set_row.rpe is not None:
        parts.append(f"rpe {set_row.rpe:g}")
    return " ".join(parts)


def _normalize_metric_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace(" x ", " x ")).strip()


def _plan(
    workout: TrueCoachWorkout,
    tracker_workout: TrackerWorkout,
    items: list[BackfillReviewItem],
) -> dict[str, Any]:
    item_plans = [_plan_item(item) for item in items]
    return {
        "blockers": [blocker for item in item_plans for blocker in item["blockers"]],
        "warnings": [warning for item in item_plans for warning in item["warnings"]],
        "workout": {
            "id": workout.id,
            "title": workout.title,
            "due": workout.due.isoformat() if workout.due else None,
            "state": workout.state,
            "tracker_workout_id": tracker_workout.id,
            "tracker_hevy_app_id": tracker_workout.hevy_app_id,
        },
        "items": item_plans,
    }


def _plan_item(item: BackfillReviewItem) -> dict[str, Any]:
    return {
        "source_id": item.source_id,
        "tracker_workout_item_id": item.tracker_workout_item_id,
        "position": item.position,
        "name": item.name,
        "info": item.info,
        "comment": item.comment,
        "selected_hevy_template": _template_to_dict(item.selected_hevy_template),
        "sets": [_set_to_dict(set_row) for set_row in item.sets],
        "notes": item.notes,
        "warnings": item.warnings,
        "blockers": item.blockers,
    }


def _template_to_dict(template: HevyAppExercise | None) -> dict[str, str] | None:
    if template is None:
        return None
    return {
        "id": template.id,
        "name": template.name,
        "type": template.type,
        "equipment": template.equipment,
    }


def _set_to_dict(set_row: PostWorkoutsRequestSet) -> dict[str, int | float | str]:
    return set_row.model_dump(exclude_none=True)


def _build_hevy_workout_request(plan: dict[str, Any]) -> PostWorkoutsRequestBody:
    workout = plan["workout"]
    due = workout.get("due")
    due_date = due[:10] if isinstance(due, str) and len(due) >= 10 else "undated"
    return PostWorkoutsRequestBody.build(
        title=f"{due_date} {workout.get('title') or 'Untitled'}",
        description=f"Backfill from True Coach Workout {workout['id']}",
        start_time=None,
        end_time=None,
        exercises=[
            _request_exercise(item)
            for item in plan["items"]
            if item["selected_hevy_template"] is not None and item["sets"]
        ],
    )


def _request_exercise(item: dict[str, Any]) -> PostWorkoutsRequestExercise:
    return PostWorkoutsRequestExercise(
        exercise_template_id=item["selected_hevy_template"]["id"],
        notes=item["notes"] or None,
        sets=[PostWorkoutsRequestSet(**set_row) for set_row in item["sets"]],
    )


def _report(workout: TrueCoachWorkout, plan: dict[str, Any]) -> str:
    lines = [
        f"# True Coach Workout Backfill Review: {workout.id}",
        "",
        f"Workout: {workout.title or 'Untitled'}",
        f"Due: {workout.due.isoformat() if workout.due else 'unknown'}",
        "Draft Hevy Workout request: hevy-workout-request.json",
        "",
    ]
    if plan["blockers"]:
        lines.append("Blockers:")
        lines.extend(f"- {blocker}" for blocker in plan["blockers"])
    else:
        lines.append("Blockers: none")
    if plan["warnings"]:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in plan["warnings"])
    lines.append("")
    for index, item in enumerate(plan["items"], start=1):
        lines.extend(_report_item(index, item))
    return "\n".join(lines).rstrip() + "\n"


def _report_item(index: int, item: dict[str, Any]) -> list[str]:
    template = item["selected_hevy_template"]
    lines = [
        f"## {index}. {item['name']}",
        "",
        f"True Coach Workout Item: {item['source_id'] or 'none'}",
        f"Tracker WorkoutItem: {item['tracker_workout_item_id']}",
        f"Coach prescription: {item['info'] or 'none'}",
        f"Athlete comment: {item['comment'] or 'none'}",
        (
            f"Selected Hevy template: {template['name']} ({template['id']})"
            if template is not None
            else "Selected Hevy template: missing"
        ),
        "Structured sets:",
    ]
    if item["sets"]:
        lines.extend(f"- {_format_set(set_row)}" for set_row in item["sets"])
    else:
        lines.append("- none")
    if item["notes"]:
        lines.append(f"Draft notes: {item['notes']}")
    lines.extend(f"WARNING: {warning}" for warning in item["warnings"])
    lines.extend(f"BLOCKER: {blocker}" for blocker in item["blockers"])
    lines.append("")
    return lines


def _format_set(set_row: dict[str, Any]) -> str:
    return "; ".join(f"{key}: {value}" for key, value in set_row.items())
