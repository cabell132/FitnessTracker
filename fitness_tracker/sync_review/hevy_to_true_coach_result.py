"""Build read-only Hevy to True Coach result sync review bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from fitness_tracker.apis.hevy_app.types import Set as HevySet
from fitness_tracker.database import Store
from fitness_tracker.database.models.hevy_app import (
    HevyAppExercise,
    HevyAppSets,
    HevyAppWorkout,
    HevyAppWorkoutItem,
)
from fitness_tracker.database.models.tracker import Workout as TrackerWorkout
from fitness_tracker.database.models.true_coach import TrueCoachWorkout, TrueCoachWorkoutItem
from fitness_tracker.sync.hevy_true_coach.utils import mapping as result_formatters


class HevyToTrueCoachResultReviewError(Exception):
    """Raised when a Hevy to True Coach result review cannot be produced."""


@dataclass(frozen=True)
class HevyToTrueCoachResultReviewBundle:
    """Paths written for one Hevy to True Coach result sync review."""

    directory: Path
    report_path: Path
    plan_path: Path
    decisions_path: Path
    decision_validation_path: Path


@dataclass(frozen=True)
class ResultReviewArtifacts:
    """Rendered artifacts for one Hevy to True Coach result sync review."""

    plan: dict[str, Any]
    decisions: dict[str, Any]
    validation: dict[str, Any]
    report: str


class HevyToTrueCoachResultReviewService:
    """Create review artifacts for one performed Hevy Workout."""

    def __init__(self, store: Store, output_root: Path = Path("reports")) -> None:
        """Create the service.

        Args:
            store (Store): Local database snapshot.
            output_root (Path): Root under which result sync review artifacts are written.
        """
        self._store = store
        self._output_root = output_root

    def write_review(self, hevy_workout_id: str) -> HevyToTrueCoachResultReviewBundle:
        """Write read-only result sync review artifacts for one Hevy Workout id.

        Args:
            hevy_workout_id (str): Hevy Workout primary key to review.

        Returns:
            HevyToTrueCoachResultReviewBundle: Paths written by the service.

        Raises:
            HevyToTrueCoachResultReviewError: If the Hevy Workout is missing locally.
        """
        with self._store.unit_of_work() as uow:
            workout = uow.hevy.get_workout(id=hevy_workout_id)
            if not isinstance(workout, HevyAppWorkout):
                msg = f"Hevy Workout {hevy_workout_id} was not found in the local DB"
                raise HevyToTrueCoachResultReviewError(msg)

            true_coach_workout = workout.true_coach
            tracker_workout = (
                uow.session.query(TrackerWorkout).filter_by(hevy_app_id=workout.id).one_or_none()
            )
            items = [
                _plan_item(item, true_coach_workout, tracker_workout)
                for item in sorted(workout.workout_items, key=lambda row: (row.index, row.id))
            ]
            plan = _plan(workout, true_coach_workout, items)
            decisions = _decisions_template(workout.id, items)
            validation = _decision_validation(plan)
            report = _report(plan)

        return _write_bundle(
            self._output_root,
            hevy_workout_id,
            ResultReviewArtifacts(
                plan=plan,
                decisions=decisions,
                validation=validation,
                report=report,
            ),
        )


def _write_bundle(
    output_root: Path,
    hevy_workout_id: str,
    artifacts: ResultReviewArtifacts,
) -> HevyToTrueCoachResultReviewBundle:
    """Write all result sync review files and return their paths.

    Args:
        output_root (Path): Root directory for report artifacts.
        hevy_workout_id (str): Hevy Workout primary key used in the bundle path.
        artifacts (ResultReviewArtifacts): Rendered artifact payloads to persist.

    Returns:
        HevyToTrueCoachResultReviewBundle: Paths written for the review.
    """
    bundle_dir = output_root / "sync-review" / "hevy-to-truecoach-results" / hevy_workout_id
    bundle_dir.mkdir(parents=True, exist_ok=True)
    plan_path = bundle_dir / "plan.json"
    decisions_path = bundle_dir / "result-decisions.json"
    validation_path = bundle_dir / "decision-validation.json"
    report_path = bundle_dir / "report.md"
    _write_json(plan_path, artifacts.plan)
    _write_json(decisions_path, artifacts.decisions)
    _write_json(validation_path, artifacts.validation)
    report_path.write_text(artifacts.report, encoding="utf-8")
    return HevyToTrueCoachResultReviewBundle(
        directory=bundle_dir,
        report_path=report_path,
        plan_path=plan_path,
        decisions_path=decisions_path,
        decision_validation_path=validation_path,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _plan_item(
    item: HevyAppWorkoutItem,
    true_coach_workout: TrueCoachWorkout | None,
    tracker_workout: TrackerWorkout | None,
) -> dict[str, Any]:
    exercise = item.exercise if isinstance(item.exercise, HevyAppExercise) else None
    formatter_name = cast(str | None, exercise.type if exercise is not None else None)
    target = item.true_coach if isinstance(item.true_coach, TrueCoachWorkoutItem) else None
    if target is None:
        candidates = _candidate_targets(item, true_coach_workout, tracker_workout)
    else:
        candidates = []
    blockers = _item_blockers(exercise, formatter_name, true_coach_workout)
    blockers.extend(_target_blockers(target, candidates))
    warnings = _item_warnings(target, candidates)
    return {
        "hevy_workout_item_id": item.id,
        "index": item.index,
        "name": item.name,
        "notes": item.notes,
        "superset_id": item.superset_id,
        "exercise": _hevy_exercise_to_dict(exercise),
        "sets": [_set_to_dict(set_) for set_ in sorted(item.sets, key=lambda row: row.index)],
        "formatter": formatter_name if formatter_name in result_formatters else None,
        "proposed_result_text": _proposed_result_text(item, formatter_name),
        "target": _target_to_dict(target),
        "candidates": [_target_to_dict(candidate) for candidate in candidates],
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
    return _sort_targets(candidates)


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


def _item_blockers(
    exercise: HevyAppExercise | None,
    formatter_name: str | None,
    true_coach_workout: TrueCoachWorkout | None,
) -> list[str]:
    blockers: list[str] = []
    if true_coach_workout is None:
        blockers.append("Missing True Coach Workout link for Hevy Workout")
    if exercise is None:
        blockers.append("Missing Hevy exercise template for performed Hevy item")
    elif formatter_name not in result_formatters:
        blockers.append(
            f"Unsupported Hevy exercise type for True Coach result formatting: {formatter_name}"
        )
    return blockers


def _target_blockers(
    target: TrueCoachWorkoutItem | None,
    candidates: list[TrueCoachWorkoutItem],
) -> list[str]:
    if target is not None:
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
    if formatter_name not in result_formatters:
        return None
    formatter = result_formatters[formatter_name]
    return formatter(cast(list[HevySet], sorted(item.sets, key=lambda row: row.index))).strip()


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
        "items": items,
        "blockers": blockers,
        "warnings": warnings,
    }


def _decisions_template(hevy_workout_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "hevy_workout_id": hevy_workout_id,
        "allow_partial_apply": False,
        "approve_completion": False,
        "items": [
            {
                "hevy_workout_item_id": item["hevy_workout_item_id"],
                "action": "sync",
                "override_true_coach_workout_item_id": None,
                "performed_as": None,
                "order_context": None,
                "omit_reason": None,
            }
            for item in items
        ],
    }


def _decision_validation(plan: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "blockers": list(plan["blockers"]),
        "warnings": list(plan["warnings"]),
    }


def _report(plan: dict[str, Any]) -> str:
    workout = plan["workout"]
    lines = [
        f"# Hevy to True Coach Result Sync Review: {workout['hevy_workout_id']}",
        "",
        f"Hevy Workout: {workout['title']}",
        f"True Coach Workout: {workout['true_coach_workout_id'] or 'missing'}",
        "",
        "Artifacts: plan.json, result-decisions.json, decision-validation.json",
        "",
    ]
    for index, item in enumerate(plan["items"], start=1):
        lines.extend(_report_item(index, item))
    return "\n".join(lines).rstrip() + "\n"


def _report_item(index: int, item: dict[str, Any]) -> list[str]:
    target = item["target"]
    lines = [
        f"## {index}. {item['name']}",
        "",
        f"Hevy Workout Item ID: {item['hevy_workout_item_id']}",
        f"Target: {_format_target(target)}",
        f"Formatter: {item['formatter'] or 'unsupported'}",
        "Sets:",
    ]
    lines.extend(f"- {_format_set(set_)}" for set_ in item["sets"])
    lines.append("Proposed result:")
    lines.append("```")
    lines.append(item["proposed_result_text"] or "")
    lines.append("```")
    if item["candidates"]:
        lines.append("Candidate True Coach targets:")
        lines.extend(f"- {_format_target(candidate)}" for candidate in item["candidates"])
    if item["warnings"]:
        lines.extend(f"WARNING: {warning}" for warning in item["warnings"])
    if item["blockers"]:
        lines.extend(f"BLOCKER: {blocker}" for blocker in item["blockers"])
    else:
        lines.append("Blockers: none")
    lines.append("")
    return lines


def _hevy_exercise_to_dict(exercise: HevyAppExercise | None) -> dict[str, Any] | None:
    if exercise is None:
        return None
    return {
        "id": exercise.id,
        "name": exercise.name,
        "type": exercise.type,
        "equipment": exercise.equipment,
    }


def _target_to_dict(item: TrueCoachWorkoutItem | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "true_coach_workout_item_id": item.id,
        "name": item.name,
        "position": item.position,
        "info": item.info or "",
        "state": item.state,
    }


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


def _format_target(target: dict[str, Any] | None) -> str:
    if target is None:
        return "missing"
    return (
        f"{target['name']} ({target['true_coach_workout_item_id']}) position={target['position']}"
    )


def _format_set(set_: dict[str, Any]) -> str:
    fields = [
        f"{key}: {set_[key]}"
        for key in ("type", "weight_kg", "reps", "distance_meters", "duration_seconds", "rpe")
        if set_[key] is not None
    ]
    return "; ".join(fields)
