"""Validate Hevy result sync decisions and build True Coach update requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PARTIAL_APPLY_BLOCKER_PREFIXES = (
    "Unsupported Hevy exercise type for True Coach result formatting",
    "Missing Hevy exercise template for performed Hevy item",
    "Missing True Coach Workout Item link for performed Hevy item",
    "Ambiguous True Coach target for unlinked performed Hevy item",
    "Completion approval is unsafe while result mapping blockers remain",
)


class HevyToTrueCoachResultApplyError(Exception):
    """Raised when reviewed Hevy results cannot be applied safely."""


@dataclass
class DecisionValidationState:
    """Mutable state for one decision validation pass."""

    target_items: dict[int, dict[str, Any]]
    used_hevy_item_ids: dict[int, int]
    used_target_ids: dict[int, int]


class HevyToTrueCoachResultDecisionBuilder:
    """Build and validate review decisions and True Coach update requests."""

    def decisions_template(
        self,
        hevy_workout_id: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Create the editable result decisions template for a review plan.

        Args:
            hevy_workout_id (str): Hevy Workout id for the decisions file.
            items (list[dict[str, Any]]): Planned performed Hevy items.

        Returns:
            dict[str, Any]: JSON-serializable editable decisions template.
        """
        return _decisions_template(hevy_workout_id, items)

    def decision_validation(
        self,
        plan: dict[str, Any],
        decisions: dict[str, Any],
    ) -> dict[str, list[str]]:
        """Validate editable result decisions against a review plan.

        Args:
            plan (dict[str, Any]): Result sync review plan.
            decisions (dict[str, Any]): Editable Agent decisions.

        Returns:
            dict[str, list[str]]: Validation blockers and warnings.
        """
        return _decision_validation(plan, decisions)

    def validate_apply_request(
        self,
        validation: dict[str, Any],
        decisions: dict[str, Any],
    ) -> None:
        """Raise when decisions cannot be safely converted into an apply request.

        Args:
            validation (dict[str, Any]): Decision validation payload.
            decisions (dict[str, Any]): Editable Agent decisions.
        """
        _validate_apply_request(validation, decisions)

    def build_true_coach_update_request(
        self,
        plan: dict[str, Any],
        decisions: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the exact True Coach update request payload for reviewed decisions.

        Args:
            plan (dict[str, Any]): Result sync review plan.
            decisions (dict[str, Any]): Editable Agent decisions.

        Returns:
            dict[str, Any]: JSON-serializable True Coach update request.
        """
        return _build_true_coach_update_request(plan, decisions)

    def apply_report(
        self,
        plan: dict[str, Any],
        decisions: dict[str, Any],
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Calculate item and completion reporting for an apply request.

        Args:
            plan (dict[str, Any]): Result sync review plan.
            decisions (dict[str, Any]): Editable Agent decisions.
            request (dict[str, Any]): True Coach update request.

        Returns:
            dict[str, Any]: Apply report fields for the request artifact.
        """
        return _apply_report(plan, decisions, request)

    def completion_status(
        self,
        *,
        approve_completion: bool,
        unresolved_hevy_workout_item_ids: list[int],
        completion_allowed: bool,
    ) -> str:
        """Calculate the completion outcome for a dry run or real apply.

        Args:
            approve_completion (bool): Whether decisions requested completion.
            unresolved_hevy_workout_item_ids (list[int]): Unresolved Hevy item ids.
            completion_allowed (bool): Whether completion is safe after apply.

        Returns:
            str: Completion status for the request artifact.
        """
        return _completion_status(
            approve_completion=approve_completion,
            unresolved_hevy_workout_item_ids=unresolved_hevy_workout_item_ids,
            completion_allowed=completion_allowed,
        )

    def hevy_item_ids_by_target_id(
        self,
        plan: dict[str, Any],
        decisions: dict[str, Any],
    ) -> dict[int, int]:
        """Map effective True Coach target ids back to performed Hevy item ids.

        Args:
            plan (dict[str, Any]): Result sync review plan.
            decisions (dict[str, Any]): Editable Agent decisions.

        Returns:
            dict[int, int]: Effective True Coach item ids mapped to Hevy item ids.
        """
        return _hevy_item_ids_by_target_id(plan, decisions)


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
        updates.append(_true_coach_update_operation(item, decision, targets))
    return {
        "workout_id": plan["workout"]["true_coach_workout_id"],
        "hevy_workout_id": plan["workout"]["hevy_workout_id"],
        "mark_workout_completed": bool(decisions.get("approve_completion") and not allow_partial),
        "completion_status": "skipped",
        "update_workout_items": updates,
    }


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


def _updated_true_coach_item_ids(request: dict[str, Any]) -> list[int]:
    if "updated_true_coach_workout_item_ids" in request:
        return [int(item_id) for item_id in request["updated_true_coach_workout_item_ids"]]
    return [
        int(update["body"]["workout_item"]["id"])
        for update in request.get("update_workout_items", [])
    ]


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
    return _sync_decision_blockers(item, decision, state)


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
