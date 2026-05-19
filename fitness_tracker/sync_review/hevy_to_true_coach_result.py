"""Build read-only Hevy to True Coach result sync review bundles."""

from __future__ import annotations

import json
import re
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


class HevyToTrueCoachResultApplyError(Exception):
    """Raised when reviewed Hevy results cannot be applied safely."""


@dataclass(frozen=True)
class HevyToTrueCoachResultReviewBundle:
    """Paths written for one Hevy to True Coach result sync review."""

    directory: Path
    report_path: Path
    plan_path: Path
    decisions_path: Path
    decision_validation_path: Path


@dataclass(frozen=True)
class HevyToTrueCoachResultApplyResult:
    """Paths and request body written for a dry-run True Coach result apply."""

    review_bundle: HevyToTrueCoachResultReviewBundle
    request_path: Path
    request: dict[str, Any]
    action: str


@dataclass(frozen=True)
class ResultReviewArtifacts:
    """Rendered artifacts for one Hevy to True Coach result sync review."""

    plan: dict[str, Any]
    decisions: dict[str, Any]
    validation: dict[str, Any]
    report: str


@dataclass
class DecisionValidationState:
    """Mutable state for one decision validation pass."""

    target_items: dict[int, dict[str, Any]]
    used_hevy_item_ids: dict[int, int]
    used_target_ids: dict[int, int]


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

    def write_review(
        self,
        hevy_workout_id: str,
        decisions_path: Path | None = None,
    ) -> HevyToTrueCoachResultReviewBundle:
        """Write read-only result sync review artifacts for one Hevy Workout id.

        Args:
            hevy_workout_id (str): Hevy Workout primary key to review.
            decisions_path (Path | None): Optional editable decisions JSON to validate.

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
            decisions = (
                _load_decisions(decisions_path)
                if decisions_path is not None
                else _decisions_template(workout.id, items)
            )
            validation = _decision_validation(plan, decisions)
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

    def write_apply_request(
        self,
        hevy_workout_id: str,
        decisions_path: Path | None = None,
    ) -> HevyToTrueCoachResultApplyResult:
        """Write the exact True Coach update request for a reviewed dry-run apply.

        Args:
            hevy_workout_id (str): Hevy Workout primary key to apply from review.
            decisions_path (Path | None): Optional editable decisions JSON to apply.

        Returns:
            HevyToTrueCoachResultApplyResult: Dry-run request artifact details.
        """
        bundle = self.write_review(hevy_workout_id, decisions_path=decisions_path)
        plan = _load_json_file(bundle.plan_path)
        decisions = _load_json_file(bundle.decisions_path)
        validation = _load_json_file(bundle.decision_validation_path)
        _validate_apply_request(validation, decisions)
        request = _build_true_coach_update_request(plan, decisions)
        request_path = bundle.directory / "truecoach-update-request.json"
        _write_json(request_path, request)
        return HevyToTrueCoachResultApplyResult(
            review_bundle=bundle,
            request_path=request_path,
            request=request,
            action="dry_run",
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


def _load_decisions(decisions_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(decisions_path.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"Could not read decisions file {decisions_path}: {exc}"
        raise HevyToTrueCoachResultReviewError(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"Could not parse decisions file {decisions_path}: {exc}"
        raise HevyToTrueCoachResultReviewError(msg) from exc
    if not isinstance(data, dict):
        msg = f"Decisions file {decisions_path} must contain a JSON object"
        raise HevyToTrueCoachResultReviewError(msg)
    return data


def _load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    target_inferred_from_sets_reps = (
        target is None and len(candidates) == 1 and _is_repeated_performed_exercise(item)
    )
    blockers = _item_blockers(exercise, formatter_name, true_coach_workout)
    blockers.extend(_target_blockers(target, candidates, target_inferred_from_sets_reps))
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
    disambiguated = _targets_matching_sets_and_reps(item, candidates)
    return disambiguated if len(disambiguated) == 1 else candidates


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
    sets = sorted(item.sets, key=lambda row: row.index)
    if not sets or any(set_.reps is None for set_ in sets):
        return None
    reps = {set_.reps for set_ in sets}
    if len(reps) != 1:
        return None
    return (len(sets), int(next(iter(reps))))


def _prescribed_sets_reps_signature(info: str) -> tuple[int, int] | None:
    match = re.search(r"\b(\d+)\s*x\s*(\d+)\b", info, flags=re.IGNORECASE)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)))


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
        "target_items": _target_items_to_dict(true_coach_workout),
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


def _decision_validation(plan: dict[str, Any], decisions: dict[str, Any]) -> dict[str, list[str]]:
    blockers = _decision_workout_blockers(plan, decisions)
    decision_items = _decision_items_by_hevy_id(decisions)
    state = DecisionValidationState(
        target_items=_target_items_by_id(plan),
        used_hevy_item_ids={},
        used_target_ids={},
    )

    for item in plan["items"]:
        blockers.extend(
            _item_decision_blockers(
                item,
                decision_items.get(item["hevy_workout_item_id"], {}),
                state,
            )
        )

    if decisions.get("approve_completion") and blockers:
        blockers.append("Completion approval is unsafe while result mapping blockers remain")
    return {"blockers": blockers, "warnings": list(plan["warnings"])}


def _validate_apply_request(validation: dict[str, Any], decisions: dict[str, Any]) -> None:
    blockers = validation.get("blockers", [])
    if blockers and not decisions.get("allow_partial_apply"):
        raise HevyToTrueCoachResultApplyError("; ".join(str(blocker) for blocker in blockers))


def _build_true_coach_update_request(
    plan: dict[str, Any],
    decisions: dict[str, Any],
) -> dict[str, Any]:
    decision_items = _decision_items_by_hevy_id(decisions)
    targets = _target_items_by_id(plan)
    allow_partial = bool(decisions.get("allow_partial_apply"))
    updates = []
    for item in plan["items"]:
        decision = decision_items.get(item["hevy_workout_item_id"], {})
        if not _is_sync_item_with_result(item, decision):
            continue
        if allow_partial and not _is_safe_partial_sync_item(item, decision, targets):
            continue
        updates.append(
            _true_coach_update_operation(
                item,
                decision,
                targets,
            )
        )
    return {
        "workout_id": plan["workout"]["true_coach_workout_id"],
        "hevy_workout_id": plan["workout"]["hevy_workout_id"],
        "mark_workout_completed": bool(decisions.get("approve_completion") and not allow_partial),
        "update_workout_items": updates,
    }


def _is_sync_item_with_result(item: dict[str, Any], decision: dict[str, Any]) -> bool:
    return decision.get("action", "sync") == "sync" and item.get("proposed_result_text") is not None


def _is_safe_partial_sync_item(
    item: dict[str, Any],
    decision: dict[str, Any],
    targets: dict[int, dict[str, Any]],
) -> bool:
    target_id = _effective_target_id(item, decision)
    unresolved_item_blockers = [
        blocker for blocker in item["blockers"] if not _is_target_mapping_blocker(blocker)
    ]
    return target_id in targets and not unresolved_item_blockers


def _true_coach_update_operation(
    item: dict[str, Any],
    decision: dict[str, Any],
    targets: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    target_id = _effective_target_id(item, decision)
    if target_id is None:
        msg = f"Hevy item {item['hevy_workout_item_id']} has no True Coach target"
        raise HevyToTrueCoachResultApplyError(msg)
    target = targets[target_id]
    return {
        "method": "PUT",
        "endpoint": f"workout_items/{target_id}",
        "body": {"workout_item": _true_coach_workout_item_payload(target, item, decision)},
    }


def _true_coach_workout_item_payload(
    target: dict[str, Any],
    item: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": target["true_coach_workout_item_id"],
        "workout_id": target["workout_id"],
        "name": target["name"],
        "info": target["info"],
        "result": _result_text(item, decision),
        "is_circuit": target["is_circuit"],
        "state": "completed",
        "state_event": "mark_as_completed",
        "position": target["position"] or 0,
        "assessment_id": target["assessment_id"],
        "exercise_id": target["exercise_id"],
    }


def _result_text(item: dict[str, Any], decision: dict[str, Any]) -> str:
    context_lines = []
    performed_as = str(decision.get("performed_as") or "").strip()
    if performed_as:
        context_lines.append(f"Performed as: {performed_as}")
    order_context = str(decision.get("order_context") or "").strip()
    if order_context:
        context_lines.append(f"Order context: {order_context}")
    context_lines.append(str(item["proposed_result_text"]).strip())
    return "\n".join(context_lines).strip()


def _decision_workout_blockers(
    plan: dict[str, Any],
    decisions: dict[str, Any],
) -> list[str]:
    blockers = _duplicate_decision_mapping_blockers(decisions)
    if decisions.get("hevy_workout_id") not in (None, plan["workout"]["hevy_workout_id"]):
        blockers.append(
            f"Decisions file is for Hevy Workout {decisions.get('hevy_workout_id')}, "
            f"not {plan['workout']['hevy_workout_id']}"
        )
    return blockers


def _target_items_by_id(plan: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {
        item["true_coach_workout_item_id"]: item
        for item in plan.get("target_items", [])
        if item is not None
    }


def _item_decision_blockers(
    item: dict[str, Any],
    decision: dict[str, Any],
    state: DecisionValidationState,
) -> list[str]:
    action = decision.get("action", "sync")
    if action == "omit":
        return _omit_decision_blockers(item, decision)
    if action != "sync":
        return [
            f"Hevy item {item['hevy_workout_item_id']} has unsupported decision action: {action}"
        ]
    return _sync_decision_blockers(
        item,
        decision,
        state,
    )


def _omit_decision_blockers(item: dict[str, Any], decision: dict[str, Any]) -> list[str]:
    if str(decision.get("omit_reason") or "").strip():
        return []
    return [f"Hevy item {item['hevy_workout_item_id']} is omitted without a required reason"]


def _sync_decision_blockers(
    item: dict[str, Any],
    decision: dict[str, Any],
    state: DecisionValidationState,
) -> list[str]:
    item_blockers = item["blockers"]
    blockers = [blocker for blocker in item_blockers if not _is_target_mapping_blocker(blocker)]
    target_mapping_blockers = [
        blocker for blocker in item_blockers if _is_target_mapping_blocker(blocker)
    ]
    target_id = _effective_target_id(item, decision)
    if target_id is None:
        return blockers + target_mapping_blockers
    if target_id not in state.target_items:
        return [
            *blockers,
            f"Hevy item {item['hevy_workout_item_id']} maps to unknown "
            f"True Coach Workout Item {target_id}",
        ]
    blockers.extend(_record_mapping_blockers(item["hevy_workout_item_id"], target_id, state))
    return blockers


def _record_mapping_blockers(
    hevy_item_id: int,
    target_id: int,
    state: DecisionValidationState,
) -> list[str]:
    blockers: list[str] = []
    if hevy_item_id in state.used_hevy_item_ids:
        blockers.append(
            f"Hevy item {hevy_item_id} is mapped more than once to True Coach items "
            f"{state.used_hevy_item_ids[hevy_item_id]} and {target_id}"
        )
    state.used_hevy_item_ids[hevy_item_id] = target_id
    if target_id in state.used_target_ids:
        blockers.append(
            f"True Coach Workout Item {target_id} receives multiple performed Hevy items: "
            f"{state.used_target_ids[target_id]} and {hevy_item_id}"
        )
    state.used_target_ids[target_id] = hevy_item_id
    return blockers


def _decision_items_by_hevy_id(decisions: dict[str, Any]) -> dict[int, dict[str, Any]]:
    indexed_items: dict[int, dict[str, Any]] = {}
    for item in _decision_item_rows(decisions):
        if item.get("hevy_workout_item_id") is not None:
            indexed_items[int(item["hevy_workout_item_id"])] = item
    return indexed_items


def _duplicate_decision_mapping_blockers(decisions: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    seen: dict[int, int | None] = {}
    for item in _decision_item_rows(decisions):
        if item.get("hevy_workout_item_id") is None:
            continue
        hevy_item_id = int(item["hevy_workout_item_id"])
        target_id = item.get("override_true_coach_workout_item_id")
        target_id = int(target_id) if target_id is not None else None
        if hevy_item_id in seen:
            blockers.append(
                f"Hevy item {hevy_item_id} is mapped more than once to True Coach items "
                f"{seen[hevy_item_id]} and {target_id}"
            )
        seen[hevy_item_id] = target_id
    return blockers


def _decision_item_rows(decisions: dict[str, Any]) -> list[dict[str, Any]]:
    items = decisions.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _effective_target_id(item: dict[str, Any], decision: dict[str, Any]) -> int | None:
    override = decision.get("override_true_coach_workout_item_id")
    if override is not None:
        return int(override)
    target = item.get("target")
    if target is not None:
        return int(target["true_coach_workout_item_id"])
    candidates = item.get("candidates", [])
    if item.get("target_inferred_from_sets_reps") and len(candidates) == 1:
        return int(candidates[0]["true_coach_workout_item_id"])
    return None


def _is_target_mapping_blocker(blocker: str) -> bool:
    return blocker.startswith(
        ("Missing True Coach Workout Item link", "Ambiguous True Coach target")
    )


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
    sorted_items = _sort_targets(list(true_coach_workout.workout_items))
    targets: list[dict[str, Any]] = []
    for item in sorted_items:
        target = _target_to_dict(item)
        if target is not None:
            targets.append(target)
    return targets


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
