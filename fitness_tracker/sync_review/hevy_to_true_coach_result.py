"""Build read-only Hevy to True Coach result sync review bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

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

PARTIAL_APPLY_BLOCKER_PREFIXES = (
    "Unsupported Hevy exercise type for True Coach result formatting",
    "Missing Hevy exercise template for performed Hevy item",
    "Missing True Coach Workout Item link for performed Hevy item",
    "Ambiguous True Coach target for unlinked performed Hevy item",
    "Completion approval is unsafe while result mapping blockers remain",
)


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
        self._planner = HevyToTrueCoachResultSyncPlanner()

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
                else _decisions_template(workout.id, plan["items"])
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
        report = _apply_report(plan, decisions, request)
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
        completion_status = _completion_status(
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
    if not blockers:
        return
    if not decisions.get("allow_partial_apply"):
        raise HevyToTrueCoachResultApplyError("; ".join(str(blocker) for blocker in blockers))
    unsafe_blockers = [
        str(blocker) for blocker in blockers if not _is_partial_apply_blocker(str(blocker))
    ]
    if unsafe_blockers:
        raise HevyToTrueCoachResultApplyError("; ".join(unsafe_blockers))


def _is_partial_apply_blocker(blocker: str) -> bool:
    return blocker.startswith(PARTIAL_APPLY_BLOCKER_PREFIXES)


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
        "completion_status": "skipped",
        "update_workout_items": updates,
    }


def _updated_true_coach_item_ids(request: dict[str, Any]) -> list[int]:
    if "updated_true_coach_workout_item_ids" in request:
        return [int(item_id) for item_id in request["updated_true_coach_workout_item_ids"]]
    return [
        int(update["body"]["workout_item"]["id"])
        for update in request.get("update_workout_items", [])
    ]


def _apply_report(
    plan: dict[str, Any],
    decisions: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    unresolved_hevy_workout_item_ids = _unresolved_hevy_item_ids(plan, decisions, request)
    return {
        "updated_true_coach_workout_item_ids": _updated_true_coach_item_ids(request),
        "omitted_hevy_workout_item_ids": _omitted_hevy_item_ids(plan, decisions),
        "unresolved_hevy_workout_item_ids": unresolved_hevy_workout_item_ids,
        "completion_status": _completion_status(
            approve_completion=bool(decisions.get("approve_completion")),
            unresolved_hevy_workout_item_ids=unresolved_hevy_workout_item_ids,
            completion_allowed=bool(request["mark_workout_completed"]),
        ),
    }


def _completion_status(
    *,
    approve_completion: bool,
    unresolved_hevy_workout_item_ids: list[int],
    completion_allowed: bool,
) -> str:
    if not approve_completion:
        return "skipped"
    if unresolved_hevy_workout_item_ids or not completion_allowed:
        return "blocked"
    return "performed"


def _hevy_item_ids_by_target_id(
    plan: dict[str, Any],
    decisions: dict[str, Any],
) -> dict[int, int]:
    decision_items = _decision_items_by_hevy_id(decisions)
    hevy_item_ids_by_target_id = {}
    for item in plan["items"]:
        target_id = _effective_target_id(
            item,
            decision_items.get(item["hevy_workout_item_id"], {}),
        )
        if target_id is not None:
            hevy_item_ids_by_target_id[target_id] = int(item["hevy_workout_item_id"])
    return hevy_item_ids_by_target_id


def _apply_update_operations(
    store: Store,
    workout_item_writer: TrueCoachWorkoutItemWriter,
    result: HevyToTrueCoachResultApplyResult,
) -> tuple[list[int], list[int]]:
    hevy_item_ids_by_target_id = _hevy_item_ids_by_target_id(
        _load_json_file(result.review_bundle.plan_path),
        _load_json_file(result.review_bundle.decisions_path),
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


def _omitted_hevy_item_ids(plan: dict[str, Any], decisions: dict[str, Any]) -> list[int]:
    decision_items = _decision_items_by_hevy_id(decisions)
    return [
        int(item["hevy_workout_item_id"])
        for item in plan["items"]
        if decision_items.get(item["hevy_workout_item_id"], {}).get("action") == "omit"
    ]


def _unresolved_hevy_item_ids(
    plan: dict[str, Any],
    decisions: dict[str, Any],
    request: dict[str, Any],
) -> list[int]:
    decision_items = _decision_items_by_hevy_id(decisions)
    updated_target_ids = set(_updated_true_coach_item_ids(request))
    targets = _target_items_by_id(plan)
    unresolved_ids = []
    for item in plan["items"]:
        if decision_items.get(item["hevy_workout_item_id"], {}).get("action") == "omit":
            continue
        target_id = _effective_target_id(
            item,
            decision_items.get(item["hevy_workout_item_id"], {}),
        )
        if target_id not in targets or target_id not in updated_target_ids:
            unresolved_ids.append(int(item["hevy_workout_item_id"]))
    return unresolved_ids


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
