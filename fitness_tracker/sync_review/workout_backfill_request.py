"""Build and validate Hevy Workout backfill decisions and requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fitness_tracker.apis.hevy_app.types.workout_request_body import PostWorkoutsRequestBody
from fitness_tracker.apis.hevy_app.types.workout_requests import (
    PostWorkoutsRequestExercise,
    PostWorkoutsRequestSet,
)
from fitness_tracker.sync_review.split_circuit.core import AGENT_DECISION_BLOCKER_PREFIX

EMPTY_WORKOUT_BACKFILL_REQUEST_BLOCKER = (
    "No performed exercise blocks are requestable for Workout backfill"
)


@dataclass(frozen=True)
class WorkoutBackfillApplyValidationContext:
    """Inputs for validating a dry-run Hevy Workout apply request."""

    plan: dict[str, Any]
    decision_validation: dict[str, list[str]]
    request_body: PostWorkoutsRequestBody
    decisions: dict[str, Any]


def build_workout_backfill_decision_template(
    workout_id: int,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an editable decision template for one Workout backfill plan.

    Args:
        workout_id (int): Source True Coach Workout id.
        plan (dict[str, Any] | None): Optional rendered backfill plan.

    Returns:
        dict[str, Any]: Editable decisions JSON payload.
    """
    decisions: dict[str, Any] = {
        "version": 1,
        "workout": {
            "id": workout_id,
            "selected_start_time": None,
            "selected_end_time": None,
        },
    }
    choice_items = _choice_decision_templates(plan) if plan is not None else []
    if choice_items:
        decisions["choice_items"] = choice_items
    circuit_items = _circuit_decision_templates(plan) if plan is not None else []
    if circuit_items:
        decisions["circuit_items"] = circuit_items
    return decisions


def validate_workout_backfill_decisions(
    workout_id: int,
    decisions: dict[str, Any],
    plan: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    """Validate editable Workout backfill decisions against a rendered plan.

    Args:
        workout_id (int): Source True Coach Workout id.
        decisions (dict[str, Any]): Editable decisions payload.
        plan (dict[str, Any] | None): Optional rendered backfill plan.

    Returns:
        dict[str, list[str]]: Decision blockers and warnings.
    """
    blockers: list[str] = []
    warnings: list[str] = []
    workout = decisions.get("workout")
    if not isinstance(workout, dict):
        return {
            "blockers": ["Missing required decision section: workout"],
            "warnings": warnings,
        }
    if workout.get("id") != workout_id:
        blockers.append(f"Decision workout id must match True Coach Workout {workout_id}")
    if not workout.get("selected_start_time") or not workout.get("selected_end_time"):
        blockers.append("Missing required decision: selected Workout timestamps")
    blockers.extend(_choice_decision_blockers(decisions, plan))
    blockers.extend(_circuit_decision_blockers(decisions, plan))
    return {"blockers": blockers, "warnings": warnings}


def build_hevy_workout_backfill_request(
    plan: dict[str, Any],
    decisions: dict[str, Any] | None = None,
) -> PostWorkoutsRequestBody:
    """Build the typed Hevy Workout request body for a backfill plan.

    Args:
        plan (dict[str, Any]): Rendered backfill plan.
        decisions (dict[str, Any] | None): Optional editable decisions payload.

    Returns:
        PostWorkoutsRequestBody: Typed Hevy Workout creation request.
    """
    workout = plan["workout"]
    due = workout.get("due")
    due_date = due[:10] if isinstance(due, str) and len(due) >= 10 else "undated"
    workout_decisions = decisions.get("workout", {}) if decisions is not None else {}
    superset_allocator = _WorkoutRequestSupersetAllocator(plan["items"])
    return PostWorkoutsRequestBody.build(
        title=f"{due_date} {workout.get('title') or 'Untitled'}",
        description=f"Backfill from True Coach Workout {workout['id']}",
        start_time=workout_decisions.get("selected_start_time"),
        end_time=workout_decisions.get("selected_end_time"),
        exercises=_request_exercises(plan["items"], decisions, superset_allocator),
    )


def requestable_workout_backfill_items(
    plan: dict[str, Any],
    decisions: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return plan items that can map to Hevy Workout request exercises.

    Args:
        plan (dict[str, Any]): Rendered backfill plan.
        decisions (dict[str, Any]): Editable decisions payload.

    Returns:
        list[dict[str, Any]]: Requestable plan item dictionaries.
    """
    return [
        item
        for item in plan.get("items", [])
        if item.get("sets") and hevy_template_id_for_request_item(item, decisions) is not None
    ]


def workout_backfill_apply_blockers(
    context: WorkoutBackfillApplyValidationContext,
) -> list[str]:
    """Return blockers that make a dry-run backfill request unsafe to apply.

    Args:
        context (WorkoutBackfillApplyValidationContext): Validation inputs.

    Returns:
        list[str]: Apply blockers in report order.
    """
    blockers = [
        blocker
        for item in context.plan.get("items", [])
        for blocker in item.get("blockers", [])
        if hevy_template_id_for_request_item(item, context.decisions) is None
        or blocker.startswith(AGENT_DECISION_BLOCKER_PREFIX)
    ]
    blockers.extend(context.decision_validation.get("blockers", []))
    workout = context.request_body.workout
    if not workout.start_time or not workout.end_time:
        blocker = "Missing required decision: selected Workout timestamps"
        if blocker not in blockers:
            blockers.append(blocker)
    if not workout.exercises:
        blockers.append(EMPTY_WORKOUT_BACKFILL_REQUEST_BLOCKER)
    blockers.extend(
        f"Missing Hevy template mapping for performed item: {item['name']}"
        for item in context.plan.get("items", [])
        if item.get("sets") and hevy_template_id_for_request_item(item, context.decisions) is None
    )
    return blockers


def hevy_template_id_for_request_item(
    item: dict[str, Any],
    decisions: dict[str, Any] | None,
) -> str | None:
    """Resolve the Hevy exercise template id for a requestable plan item.

    Args:
        item (dict[str, Any]): Rendered backfill plan item.
        decisions (dict[str, Any] | None): Optional editable decisions payload.

    Returns:
        str | None: Resolved Hevy template id, if one is available.
    """
    if item["selected_hevy_template"] is not None:
        return item["selected_hevy_template"]["id"]
    if decisions is None:
        return None
    decision = _manual_template_decision_for(item, decisions)
    if decision is None:
        return None
    selected_template_id = decision.get("selected_hevy_template_id")
    return selected_template_id if isinstance(selected_template_id, str) else None


def is_expanded_circuit_movement_item(item: dict[str, Any]) -> bool:
    """Return whether a plan item is an expanded Circuit/AMRAP movement.

    Args:
        item (dict[str, Any]): Rendered backfill plan item.

    Returns:
        bool: True when the item was expanded from a Circuit/AMRAP prescription.
    """
    return (
        "movement_target" in item
        and "original_prescription_text" in item
        and "completed_round_count" in item
    )


def _choice_decision_blockers(
    decisions: dict[str, Any],
    plan: dict[str, Any] | None,
) -> list[str]:
    blockers: list[str] = []
    for required_choice in _choice_decision_templates(plan) if plan is not None else []:
        decision = _choice_decision_for(decisions, required_choice)
        if decision is None or not decision.get("selected_hevy_template_id"):
            blockers.append(
                "Missing required decision: Choice Workout Item "
                f"{required_choice['source_id']} {required_choice['performed_name']} template"
            )
        elif (
            required_choice["candidate_template_ids"]
            and decision["selected_hevy_template_id"]
            not in required_choice["candidate_template_ids"]
        ):
            blockers.append(
                "Choice Workout Item "
                f"{required_choice['source_id']} {required_choice['performed_name']} "
                "decision must use one of the candidate Hevy templates"
            )
    return blockers


def _circuit_decision_blockers(
    decisions: dict[str, Any],
    plan: dict[str, Any] | None,
) -> list[str]:
    blockers: list[str] = []
    for required_circuit in _circuit_decision_templates(plan) if plan is not None else []:
        decision = _circuit_decision_for(decisions, required_circuit)
        if decision is None or not decision.get("selected_hevy_template_id"):
            blockers.append(
                "Missing required decision: Circuit Workout Item "
                f"{required_circuit['source_id']} {required_circuit['movement_name']} template"
            )
        elif (
            required_circuit["candidate_template_ids"]
            and decision["selected_hevy_template_id"]
            not in required_circuit["candidate_template_ids"]
        ):
            blockers.append(
                "Circuit Workout Item "
                f"{required_circuit['source_id']} {required_circuit['movement_name']} "
                "decision must use one of the candidate Hevy templates"
            )
    return blockers


def _choice_decision_templates(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "source_id": item["source_id"],
            "performed_name": item["name"],
            "selected_hevy_template_id": None,
            "candidate_template_ids": item["choice_template_candidates"],
            "reason": item["choice_decision_reason"],
        }
        for item in plan["items"]
        if item.get("choice_decision_reason") is not None
    ]


def _circuit_decision_templates(plan: dict[str, Any]) -> list[dict[str, Any]]:
    templates = []
    for item in plan["items"]:
        if item.get("circuit_decision_reason") is None:
            continue
        decision = {
            "source_id": item["source_id"],
            "movement_name": item["name"],
            "selected_hevy_template_id": None,
            "candidate_template_ids": item["circuit_template_candidates"],
            "reason": item["circuit_decision_reason"],
        }
        for key in ("replacement_for_movement_name", "replacement_source_comment"):
            if key in item:
                decision[key] = item[key]
        templates.append(decision)
    return templates


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


def _request_exercises(
    items: list[dict[str, Any]],
    decisions: dict[str, Any] | None,
    superset_allocator: _WorkoutRequestSupersetAllocator,
) -> list[PostWorkoutsRequestExercise]:
    exercises = []
    for item in items:
        template_id = hevy_template_id_for_request_item(item, decisions)
        if template_id is None or not item["sets"]:
            continue
        exercises.append(
            _request_exercise(
                item,
                template_id=template_id,
                superset_id=superset_allocator.superset_id_for_item(item),
            )
        )
    return exercises


_ExpandedCircuitSupersetKey = tuple[int | None, int]


class _WorkoutRequestSupersetAllocator:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        superset_ids = (
            item["superset_id"] for item in items if item.get("superset_id") is not None
        )
        self._next_id = max(superset_ids, default=-1) + 1
        self._expanded_circuit_superset_ids: dict[_ExpandedCircuitSupersetKey, int] = {}

    def superset_id_for_item(self, item: dict[str, Any]) -> int | None:
        if item.get("superset_id") is not None:
            return int(item["superset_id"])
        if not is_expanded_circuit_movement_item(item):
            return None
        key = (item.get("source_id"), int(item["tracker_workout_item_id"]))
        if key not in self._expanded_circuit_superset_ids:
            self._expanded_circuit_superset_ids[key] = self._next_id
            self._next_id += 1
        return self._expanded_circuit_superset_ids[key]


def _request_exercise(
    item: dict[str, Any],
    *,
    template_id: str | None,
    superset_id: int | None,
) -> PostWorkoutsRequestExercise:
    if template_id is None:
        msg = f"Missing Hevy template for request exercise: {item['name']}"
        raise ValueError(msg)
    return PostWorkoutsRequestExercise(
        exercise_template_id=template_id,
        superset_id=superset_id,
        notes=item["notes"] or None,
        sets=[PostWorkoutsRequestSet(**set_row) for set_row in item["sets"]],
    )


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
