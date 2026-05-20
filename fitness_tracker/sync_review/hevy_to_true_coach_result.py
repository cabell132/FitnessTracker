"""Build read-only Hevy to True Coach result sync review bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import fitness_tracker.sync_review.hevy_to_true_coach_result_decisions as result_decisions
from fitness_tracker.apis.true_coach.exceptions import TrueCoachAPIError
from fitness_tracker.apis.true_coach.types import PutWorkoutItemRequest
from fitness_tracker.database import Store
from fitness_tracker.database.models.hevy_app import HevyAppWorkout
from fitness_tracker.database.models.tracker import Workout as TrackerWorkout
from fitness_tracker.database.models.true_coach import TrueCoachWorkoutItem
from fitness_tracker.sync_review.hevy_to_true_coach_result_planner import (
    HevyToTrueCoachResultSyncPlanner,
)
from fitness_tracker.sync.ports.true_coach_workout_item_writer import TrueCoachWorkoutItemWriter

HevyToTrueCoachResultApplyError = result_decisions.HevyToTrueCoachResultApplyError


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
class HevyToTrueCoachResultApplyResult:
    """Paths, request body, and report data for a True Coach result apply."""

    review_bundle: HevyToTrueCoachResultReviewBundle
    request_path: Path
    request: dict[str, Any]
    action: str
    updated_true_coach_workout_item_ids: list[int] = field(default_factory=list)
    omitted_hevy_workout_item_ids: list[int] = field(default_factory=list)
    unresolved_hevy_workout_item_ids: list[int] = field(default_factory=list)
    completion_status: str = "skipped"


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
        self._planner = HevyToTrueCoachResultSyncPlanner()
        self._decision_builder = result_decisions.HevyToTrueCoachResultDecisionBuilder()

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

            tracker_workout = (
                uow.session.query(TrackerWorkout).filter_by(hevy_app_id=workout.id).one_or_none()
            )
            plan = self._planner.plan(workout, tracker_workout)
            decisions = (
                _load_decisions(decisions_path)
                if decisions_path is not None
                else self._decision_builder.decisions_template(workout.id, plan["items"])
            )
            validation = self._decision_builder.decision_validation(plan, decisions)
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
        self._decision_builder.validate_apply_request(validation, decisions)
        request = self._decision_builder.build_true_coach_update_request(plan, decisions)
        report = self._decision_builder.apply_report(plan, decisions, request)
        request.update(report)
        request_path = bundle.directory / "truecoach-update-request.json"
        _write_json(request_path, request)
        return HevyToTrueCoachResultApplyResult(
            review_bundle=bundle,
            request_path=request_path,
            request=request,
            action="dry_run",
            updated_true_coach_workout_item_ids=report["updated_true_coach_workout_item_ids"],
            omitted_hevy_workout_item_ids=report["omitted_hevy_workout_item_ids"],
            unresolved_hevy_workout_item_ids=report["unresolved_hevy_workout_item_ids"],
            completion_status=report["completion_status"],
        )

    def apply(
        self,
        hevy_workout_id: str,
        *,
        workout_item_writer: TrueCoachWorkoutItemWriter,
        decisions_path: Path | None = None,
    ) -> HevyToTrueCoachResultApplyResult:
        """Apply reviewed True Coach Workout Item updates from the dry-run request.

        Args:
            hevy_workout_id (str): Hevy Workout primary key to apply.
            workout_item_writer (TrueCoachWorkoutItemWriter): True Coach mutation port.
            decisions_path (Path | None): Optional editable decisions JSON to apply.

        Returns:
            HevyToTrueCoachResultApplyResult: Apply artifact details and item-level report.
        """
        result = self.write_apply_request(hevy_workout_id, decisions_path=decisions_path)
        updated_item_ids, unresolved_hevy_item_ids = _apply_update_operations(
            self._store,
            workout_item_writer,
            result,
        )

        should_complete = result.request["mark_workout_completed"] and not unresolved_hevy_item_ids
        if should_complete:
            workout_item_writer.mark_workout_completed(int(result.request["workout_id"]))
        completion_requested = result.completion_status != "skipped"
        completion_status = self._decision_builder.completion_status(
            approve_completion=completion_requested,
            unresolved_hevy_workout_item_ids=unresolved_hevy_item_ids,
            completion_allowed=should_complete,
        )
        applied_request = {
            **result.request,
            "mark_workout_completed": should_complete,
            "completion_status": completion_status,
            "updated_true_coach_workout_item_ids": updated_item_ids,
            "unresolved_hevy_workout_item_ids": unresolved_hevy_item_ids,
        }
        _write_json(result.request_path, applied_request)
        return replace(
            result,
            action="applied",
            request=applied_request,
            updated_true_coach_workout_item_ids=updated_item_ids,
            unresolved_hevy_workout_item_ids=unresolved_hevy_item_ids,
            completion_status=completion_status,
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


def _apply_update_operations(
    store: Store,
    workout_item_writer: TrueCoachWorkoutItemWriter,
    result: HevyToTrueCoachResultApplyResult,
) -> tuple[list[int], list[int]]:
    hevy_item_ids_by_target_id = (
        result_decisions.HevyToTrueCoachResultDecisionBuilder().hevy_item_ids_by_target_id(
            _load_json_file(result.review_bundle.plan_path),
            _load_json_file(result.review_bundle.decisions_path),
        )
    )
    updated_item_ids: list[int] = []
    unresolved_hevy_item_ids = list(result.unresolved_hevy_workout_item_ids)
    for update in result.request["update_workout_items"]:
        item_id = _apply_update_operation(
            store,
            workout_item_writer,
            update,
        )
        if item_id is not None:
            updated_item_ids.append(item_id)
            continue
        hevy_item_id = hevy_item_ids_by_target_id.get(int(update["body"]["workout_item"]["id"]))
        if hevy_item_id is not None and hevy_item_id not in unresolved_hevy_item_ids:
            unresolved_hevy_item_ids.append(hevy_item_id)
    return updated_item_ids, unresolved_hevy_item_ids


def _apply_update_operation(
    store: Store,
    workout_item_writer: TrueCoachWorkoutItemWriter,
    update: dict[str, Any],
) -> int | None:
    body = update["body"]["workout_item"]
    request_body = PutWorkoutItemRequest.model_validate(body)
    try:
        workout_item_writer.update_workout_item(int(body["id"]), request_body)
        _persist_true_coach_workout_item_update(store, request_body)
        return int(body["id"])
    except TrueCoachAPIError as exc:
        if exc.status_code != 404:
            raise
        repaired_request = _repair_stale_workout_item_request(
            store,
            workout_item_writer,
            request_body,
        )
        if repaired_request is None:
            return None
        workout_item_writer.update_workout_item(repaired_request.id, repaired_request)
        _persist_true_coach_workout_item_update(store, repaired_request)
        return repaired_request.id


def _repair_stale_workout_item_request(
    store: Store,
    workout_item_writer: TrueCoachWorkoutItemWriter,
    stale_request: PutWorkoutItemRequest,
) -> PutWorkoutItemRequest | None:
    latest = workout_item_writer.get_recent_workout(stale_request.workout_id)
    if latest is None:
        return None
    workout, workout_items = latest
    with store.unit_of_work() as uow:
        uow.true_coach.add_workout(workout)
        for workout_item in workout_items:
            uow.true_coach.add_workout_item(workout_item)
        uow.cross_domain.insert_tc_tracker_workout_items()
        uow.session.flush()
        refreshed_items = uow.true_coach.get_workout_items(workout_id=stale_request.workout_id)
        target = _matching_refreshed_workout_item(stale_request, refreshed_items)
        if target is None:
            return None
        return _repaired_workout_item_request(stale_request, target)


def _matching_refreshed_workout_item(
    stale_request: PutWorkoutItemRequest,
    refreshed_items: list[TrueCoachWorkoutItem],
) -> TrueCoachWorkoutItem | None:
    candidates = [
        item
        for item in refreshed_items
        if item.id != stale_request.id
        and item.name == stale_request.name
        and item.position == stale_request.position
        and item.exercise_id == stale_request.exercise_id
        and item.assessment_id == stale_request.assessment_id
        and item.is_circuit == stale_request.is_circuit
    ]
    if len(candidates) != 1:
        return None
    return candidates[0]


def _repaired_workout_item_request(
    stale_request: PutWorkoutItemRequest,
    target: TrueCoachWorkoutItem,
) -> PutWorkoutItemRequest:
    return PutWorkoutItemRequest(
        id=cast(int, target.id),
        workout_id=cast(int, target.workout_id),
        name=cast(str, target.name),
        info=str(target.info or ""),
        result=stale_request.result,
        is_circuit=cast(bool, target.is_circuit),
        state="completed",
        state_event="mark_as_completed",
        position=int(target.position or 0),
        assessment_id=cast(int | None, target.assessment_id),
        exercise_id=cast(int | None, target.exercise_id),
    )


def _persist_true_coach_workout_item_update(
    store: Store,
    workout_item: PutWorkoutItemRequest,
) -> None:
    with store.unit_of_work() as uow:
        uow.true_coach.update_workout_item(workout_item)


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
