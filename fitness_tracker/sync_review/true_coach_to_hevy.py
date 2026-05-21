"""Build read-only True Coach to Hevy sync review bundles."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict

from fitness_tracker.apis.hevy_app.types import (
    PostRoutinesRequestBody,
    PostRoutinesRequestExercise,
    PostRoutinesRequestSet,
)
from fitness_tracker.database import Store
from fitness_tracker.database.models import HevyAppExercise
from fitness_tracker.database.models.true_coach import TrueCoachWorkout
from fitness_tracker.sync._circuit_block_parser import (
    ParsedCircuitBlock,
)
from fitness_tracker.sync._true_coach_html import (
    build_superset_index,
    parse_workout_order,
)
from fitness_tracker.sync.ports import HevyRoutineWriter
from fitness_tracker.sync_review.routine_prescription import (
    BLOCKING_REQUIRED_TEMPLATE_STATUSES,
    HEVY_PLACEHOLDER_TEMPLATE_NAME,
    ISO_PHASE_PATTERN,
    NO_DETERMINISTIC_SET_PARSER_WARNING,
    NO_LINKED_TEMPLATE_WARNING,
    PlannedBlock,
    PlannedBlockKind,
    RequiredHevyTemplate,
    ReviewItem,
    RoutinePrescriptionPlanner,
    SetProvenance,
    required_templates_for_blockers,
)
from fitness_tracker.sync_review.workflow import (
    read_json_object,
    review_bundle_dir,
    write_json_artifact,
)

SYNC_NAME = "truecoach-to-hevy"
SET_DISPLAY_KEYS = ("type", "weight_kg", "reps", "distance_meters", "duration_seconds")
TRUE_COACH_WORKOUT_ID_MARKER = "TrueCoachWorkoutId"
ROUTINE_BATCH_MARKER = "RoutineBatch"
MISSING_WORKOUT_ID_MARKER_REASON = f"Missing Routine source marker: {TRUE_COACH_WORKOUT_ID_MARKER}"
MISSING_ROUTINE_BATCH_MARKER_REASON = f"Missing Routine source marker: {ROUTINE_BATCH_MARKER}"


class SyncReviewError(Exception):
    """Raised when a requested sync review cannot be produced."""


class SyncApplyError(Exception):
    """Raised when a sync review plan is not safe to apply."""


@dataclass(frozen=True)
class ReviewBundle:
    """Paths written for a sync review."""

    directory: Path
    report_path: Path
    plan_path: Path


@dataclass(frozen=True)
class ApplyResult:
    """Paths and request body produced for a sync apply attempt."""

    review_bundle: ReviewBundle
    request_path: Path
    request_body: PostRoutinesRequestBody


type RoutineReplacementBatchStatus = Literal["applied", "review_required", "no_due_workouts"]


@dataclass(frozen=True)
class RoutineReplacementBatchResult:
    """Outcome of a strict automatic Routine replacement batch."""

    status: RoutineReplacementBatchStatus
    review_bundles: list[ReviewBundle]
    apply_results: list[ApplyResult]
    deleted_routine_count: int = 0
    review_required_workout_ids: list[int] | None = None
    review_required_reasons: dict[int, list[str]] | None = None


class SafetyStatus(TypedDict):
    """Machine-readable Routine creation safety classification."""

    auto_safe: bool
    review_required_reasons: list[str]


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
        self._planner = RoutinePrescriptionPlanner()

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
            workout = uow.true_coach.get_workout(id=workout_id)
            if workout is None:
                msg = f"True Coach workout {workout_id} was not found in the local DB"
                raise SyncReviewError(msg)

            sorted_items = sorted(
                workout.workout_items,
                key=lambda item: (item.position is None, item.position or 0, item.id),
            )
            superset_ids = _superset_ids_by_position(workout)
            items = [
                self._planner.review_item(uow, item, superset_ids.get(item.position or index))
                for index, item in enumerate(sorted_items, start=1)
            ]
            plan = self._plan(workout, items)
            report = self._report(workout, items, plan["safety"])

        bundle_dir = review_bundle_dir(self._output_root, SYNC_NAME, workout_id)
        report_path = bundle_dir / "report.md"
        plan_path = bundle_dir / "plan.json"
        report_path.write_text(report, encoding="utf-8")
        write_json_artifact(plan_path, plan)
        return ReviewBundle(directory=bundle_dir, report_path=report_path, plan_path=plan_path)

    def write_apply_request(self, workout_id: int) -> ApplyResult:
        """Validate a review plan and write the Hevy Routine request body.

        Args:
            workout_id (int): True Coach workout id.

        Returns:
            ApplyResult: Review bundle and dry-run request path.
        """
        bundle = self.write_review(workout_id)
        plan = read_json_object(bundle.plan_path)
        request_body = _build_hevy_routine_request(plan)
        request_path = bundle.directory / "hevy-request.json"
        write_json_artifact(request_path, request_body)
        return ApplyResult(
            review_bundle=bundle,
            request_path=request_path,
            request_body=request_body,
        )

    def apply(self, workout_id: int, *, routine_writer: HevyRoutineWriter) -> ApplyResult:
        """Create a Hevy Routine from a validated sync review plan.

        Args:
            workout_id (int): True Coach workout id.
            routine_writer (HevyRoutineWriter): Routine writer port.

        Returns:
            ApplyResult: Request body and local artifacts from the apply attempt.
        """
        result = self.write_apply_request(workout_id)
        routine_writer.create_routine(result.request_body)
        return result

    def _plan(self, workout: TrueCoachWorkout, items: list[ReviewItem]) -> dict[str, Any]:
        plan: dict[str, Any] = {
            "workout": {
                "id": workout.id,
                "title": workout.title,
                "due": workout.due.isoformat() if workout.due else None,
                "state": workout.state,
            },
            "routine_source_markers": _routine_source_markers(workout),
            "items": [self._plan_item(item) for item in items],
        }
        plan["safety"] = classify_plan_safety(plan)
        return plan

    def _plan_item(self, item: ReviewItem) -> dict[str, Any]:
        template = item.selected_hevy_template
        return {
            "source_id": item.source_id,
            "superset_id": item.superset_id,
            "name": item.name,
            "info": item.info,
            "comment": item.comment,
            "selected_hevy_template": _template_to_dict(template),
            "required_hevy_templates": [
                _required_template_to_dict(required_template)
                for required_template in item.required_hevy_templates
            ],
            "proposed_sets": _sets_with_provenance_to_dict(
                item.proposed_sets,
                item.set_provenance,
            ),
            "planned_blocks": [_planned_block_to_dict(block) for block in item.planned_blocks],
            "parsed_circuit_block": _parsed_circuit_block_to_dict(item.parsed_circuit_block),
            "warnings": item.warnings,
            "blockers": item.blockers,
        }

    def _report(
        self,
        workout: TrueCoachWorkout,
        items: list[ReviewItem],
        safety: SafetyStatus,
    ) -> str:
        lines = [
            f"# True Coach to Hevy Sync Review: {workout.id}",
            "",
            f"Workout: {workout.title or 'Untitled'}",
            f"Due: {workout.due.isoformat() if workout.due else 'unknown'}",
            "",
            _format_safety_status(safety),
            "",
        ]
        lines.extend(_format_review_required_reasons(safety))
        lines.extend(_format_agent_next_actions(items))
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
        if item.planned_blocks:
            lines.append("Planned Hevy blocks:")
            for block in item.planned_blocks:
                lines.extend(_format_planned_block(block))
        if item.required_hevy_templates:
            lines.append("Required Hevy templates:")
            lines.extend(
                f"- {_format_required_template(required_template)}"
                for required_template in item.required_hevy_templates
            )
        if item.warnings:
            lines.extend(f"WARNING: {warning}" for warning in item.warnings)
        if item.blockers:
            lines.extend(f"BLOCKER: {blocker}" for blocker in item.blockers)
        else:
            lines.append("Blockers: none")
        lines.append("")
        return lines


class RoutineReplacementBatchWorkflow:
    """Plan and apply due Routine replacements as one review-gated batch."""

    def __init__(self, store: Store, output_root: Path = Path("reports")) -> None:
        """Create the workflow.

        Args:
            store (Store): Local database snapshot.
            output_root (Path): Root under which review artifacts are written.
        """
        self._review_service = TrueCoachToHevyReviewService(
            store=store,
            output_root=output_root,
        )

    def sync(
        self,
        workouts: list[TrueCoachWorkout],
        *,
        routine_writer: HevyRoutineWriter,
        clear_existing_routines: Callable[[], int],
    ) -> RoutineReplacementBatchResult:
        """Replace Hevy Routine drafts only when every due Workout is automatic-safe.

        Args:
            workouts (list[TrueCoachWorkout]): Due True Coach Workouts to replace as one batch.
            routine_writer (HevyRoutineWriter): Hevy mutation port for safe Routine creation.
            clear_existing_routines (Callable[[], int]): Mutation that deletes existing drafts.

        Returns:
            RoutineReplacementBatchResult: No-due, review-required, or applied batch outcome.
        """
        if not workouts:
            return RoutineReplacementBatchResult(
                status="no_due_workouts",
                review_bundles=[],
                apply_results=[],
            )

        review_bundles = [
            self._review_service.write_review(workout.id) for workout in _workouts_by_due(workouts)
        ]
        plans = [read_json_object(bundle.plan_path) for bundle in review_bundles]
        unsafe_plans = [plan for plan in plans if not plan["safety"]["auto_safe"]]
        if unsafe_plans:
            return RoutineReplacementBatchResult(
                status="review_required",
                review_bundles=review_bundles,
                apply_results=[],
                review_required_workout_ids=[plan["workout"]["id"] for plan in unsafe_plans],
                review_required_reasons={
                    plan["workout"]["id"]: plan["safety"]["review_required_reasons"]
                    for plan in unsafe_plans
                },
            )

        deleted = clear_existing_routines()
        apply_results = [
            self._review_service.apply(plan["workout"]["id"], routine_writer=routine_writer)
            for plan in plans
        ]
        return RoutineReplacementBatchResult(
            status="applied",
            review_bundles=[result.review_bundle for result in apply_results],
            apply_results=apply_results,
            deleted_routine_count=deleted,
        )


def _workouts_by_due(workouts: list[TrueCoachWorkout]) -> list[TrueCoachWorkout]:
    return sorted(workouts, key=lambda workout: (workout.due is None, workout.due, workout.id))


def _build_hevy_routine_request(plan: dict[str, Any]) -> PostRoutinesRequestBody:
    blockers = _apply_blockers(plan)
    if blockers:
        raise SyncApplyError("; ".join(blockers))
    workout = plan["workout"]
    return PostRoutinesRequestBody.build(
        title=_routine_title(workout),
        notes=_routine_notes(workout),
        exercises=_request_exercises_for_plan(plan),
    )


def classify_plan_safety(plan: dict[str, Any]) -> SafetyStatus:
    """Classify whether automatic sync may apply a Routine creation plan.

    Args:
        plan (dict[str, Any]): Routine creation plan artifact payload.

    Returns:
        SafetyStatus: Machine-readable automatic safety status and review reasons.
    """
    reasons = _review_required_reasons(plan)
    return {
        "auto_safe": not reasons,
        "review_required_reasons": reasons,
    }


def _review_required_reasons(plan: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    reasons.extend(_warning_reasons(plan["items"]))
    reasons.extend(_apply_blockers(plan))
    reasons.extend(_placeholder_template_reasons(plan["items"]))
    reasons.extend(_routine_source_marker_reasons(plan))
    return _deduplicate_reasons(reasons)


def _warning_reasons(items: list[dict[str, Any]]) -> list[str]:
    return [
        f"Warning for {source_text}: {warning}"
        for source_text, entry in _review_reason_entries(items)
        for warning in entry.get("warnings", [])
    ]


def _placeholder_template_reasons(items: list[dict[str, Any]]) -> list[str]:
    return [
        f"Placeholder Hevy exercise mapping: {source_text}"
        for source_text, entry in _review_reason_entries(items)
        if _is_placeholder_plan_template(entry.get("selected_hevy_template"))
    ]


def _review_reason_entries(
    items: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    entries: list[tuple[str, dict[str, Any]]] = []
    for item in items:
        entries.append((item["name"], item))
        entries.extend((block["source_text"], block) for block in item.get("planned_blocks", []))
    return entries


def _is_placeholder_plan_template(template: dict[str, Any] | None) -> bool:
    return template is not None and template.get("name") == HEVY_PLACEHOLDER_TEMPLATE_NAME


def _routine_source_marker_reasons(plan: dict[str, Any]) -> list[str]:
    markers = plan.get("routine_source_markers")
    if not isinstance(markers, dict):
        return [MISSING_WORKOUT_ID_MARKER_REASON]
    expected_workout_id = str(plan["workout"]["id"])
    reasons: list[str] = []
    if markers.get(TRUE_COACH_WORKOUT_ID_MARKER) != expected_workout_id:
        reasons.append(MISSING_WORKOUT_ID_MARKER_REASON)
    if markers.get(ROUTINE_BATCH_MARKER) != SYNC_NAME:
        reasons.append(MISSING_ROUTINE_BATCH_MARKER_REASON)
    return reasons


def _deduplicate_reasons(reasons: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for reason in reasons:
        if reason not in seen:
            deduplicated.append(reason)
            seen.add(reason)
    return deduplicated


def _apply_blockers(plan: dict[str, Any]) -> list[str]:
    items = plan["items"]
    blockers = [blocker for item in items for blocker in item.get("blockers", [])]
    blockers.extend(
        f"Missing required Hevy exercise mapping: {item['name']}"
        for item in items
        if not item.get("planned_blocks") and item.get("selected_hevy_template") is None
    )
    blockers.extend(
        f"Missing required Hevy exercise mapping: {block['source_text']}"
        for item in items
        for block in item.get("planned_blocks", [])
        if block.get("selected_hevy_template") is None
    )
    blockers.extend(
        f"Unsplit required mixed-mode item: {item['name']}"
        for item in items
        if _is_unsplit_required_mixed_mode_item(item)
    )
    blockers.extend(
        f"Invalid set payload for {item['name']}: no sets"
        for item in items
        if not item.get("planned_blocks") and not item.get("proposed_sets")
    )
    blockers.extend(
        f"Invalid set payload for {block['source_text']}: no sets"
        for item in items
        for block in item.get("planned_blocks", [])
        if not block.get("proposed_sets") and not block.get("notes_only")
    )
    return blockers


def _is_unsplit_required_mixed_mode_item(item: dict[str, Any]) -> bool:
    info = item.get("info") or ""
    return (
        not item.get("planned_blocks")
        and ISO_PHASE_PATTERN.search(info) is not None
        and re.search(r"\b(?:then|followed by)\b", info, re.IGNORECASE) is not None
    )


def _routine_title(workout: dict[str, Any]) -> str:
    due = workout.get("due")
    due_text = datetime.fromisoformat(due).strftime("%d %b %Y") if due else ""
    return f"{due_text}\n{workout.get('title') or ''}\n{workout['id']}"


def _routine_notes(workout: dict[str, Any]) -> str:
    markers = [f"{key}: {value}" for key, value in _routine_source_markers(workout).items()]
    return "\n".join(markers)


def _routine_source_markers(workout: TrueCoachWorkout | dict[str, Any]) -> dict[str, str]:
    workout_id = workout.id if isinstance(workout, TrueCoachWorkout) else workout["id"]
    return {
        TRUE_COACH_WORKOUT_ID_MARKER: str(workout_id),
        ROUTINE_BATCH_MARKER: SYNC_NAME,
    }


def _request_exercises_for_plan(plan: dict[str, Any]) -> list[PostRoutinesRequestExercise]:
    superset_allocator = _SupersetAllocator(plan["items"])
    return [
        exercise
        for item in plan["items"]
        for exercise in _request_exercises_for_item(item, superset_allocator)
    ]


class _SupersetAllocator:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        superset_ids = (
            item["superset_id"] for item in items if item.get("superset_id") is not None
        )
        self._next_id = max(superset_ids, default=-1) + 1

    def superset_id_for_item(self, item: dict[str, Any]) -> int:
        if item.get("superset_id") is not None:
            return int(item["superset_id"])
        superset_id = self._next_id
        self._next_id += 1
        return superset_id


def _request_exercises_for_item(
    item: dict[str, Any],
    superset_allocator: _SupersetAllocator,
) -> list[PostRoutinesRequestExercise]:
    blocks = item.get("planned_blocks", [])
    if blocks:
        return _request_exercises_from_blocks(item, blocks, superset_allocator)
    return [
        _request_exercise(
            template_id=item["selected_hevy_template"]["id"],
            superset_id=item.get("superset_id"),
            notes=_item_notes(item),
            sets=item["proposed_sets"],
            template=item["selected_hevy_template"],
        )
    ]


def _item_notes(item: dict[str, Any]) -> str:
    return "\n".join(
        part for part in (item.get("info") or item["name"], item.get("comment") or "") if part
    )


def _request_exercises_from_blocks(
    item: dict[str, Any],
    blocks: list[dict[str, Any]],
    superset_allocator: _SupersetAllocator,
) -> list[PostRoutinesRequestExercise]:
    if _is_circuit_request_item(item, blocks):
        superset_id = superset_allocator.superset_id_for_item(item)
        final_block_index = len(blocks) - 1
        set_count = _circuit_request_set_count(item)
        exercises: list[PostRoutinesRequestExercise] = []
        for index, block in enumerate(blocks):
            sets = _repeated_request_sets(block["proposed_sets"], count=set_count)
            rest_seconds = _explicit_circuit_rest_seconds(
                item,
                is_final_block=index == final_block_index,
            )
            if rest_seconds is None:
                rest_seconds = _rest_seconds_from_sets(
                    sets,
                    template=block["selected_hevy_template"],
                )
            exercises.append(
                _request_exercise(
                    template_id=block["selected_hevy_template"]["id"],
                    superset_id=superset_id,
                    notes=block["notes"],
                    sets=sets,
                    rest_seconds=rest_seconds,
                    template=block["selected_hevy_template"],
                )
            )
        return exercises
    return [_request_exercise_from_block(block) for block in blocks]


def _is_circuit_request_item(item: dict[str, Any], blocks: list[dict[str, Any]]) -> bool:
    if item.get("parsed_circuit_block") is None:
        return False
    return all(
        block.get("block_kind") in {"circuit_movement", "amrap_movement"} for block in blocks
    )


def _repeated_request_sets(
    sets: list[dict[str, Any]],
    *,
    count: int,
) -> list[dict[str, Any]]:
    return [set_row for _ in range(count) for set_row in sets]


def _circuit_request_set_count(item: dict[str, Any]) -> int:
    parsed_block = item["parsed_circuit_block"]
    if parsed_block.get("round_count") is not None:
        return int(parsed_block["round_count"])
    time_cap_seconds = parsed_block.get("amrap_time_cap_seconds")
    if time_cap_seconds is not None:
        return max(1, int(time_cap_seconds) // 120)
    return 1


def _explicit_circuit_rest_seconds(
    item: dict[str, Any],
    *,
    is_final_block: bool,
) -> int | None:
    round_rest_seconds = _round_rest_seconds(item)
    if is_final_block and round_rest_seconds > 0:
        return round_rest_seconds
    movement_rest_seconds = _movement_rest_seconds(item)
    if not is_final_block and movement_rest_seconds > 0:
        return movement_rest_seconds
    return None


def _round_rest_seconds(item: dict[str, Any]) -> int:
    rests = item["parsed_circuit_block"].get("rests", [])
    if not rests:
        return 0
    rest = rests[-1]
    durations = rest.get("durations_seconds", [])
    if not durations:
        return 0
    if _is_round_rest_text(rest.get("source_text", "")):
        return int(durations[-1])
    if len(durations) > 1:
        return int(durations[-1])
    return int(durations[0])


def _movement_rest_seconds(item: dict[str, Any]) -> int:
    rests = item["parsed_circuit_block"].get("rests", [])
    if not rests:
        return 0
    rest = rests[-1]
    durations = rest.get("durations_seconds", [])
    if not durations or not _is_movement_rest_text(rest.get("source_text", "")):
        return 0
    return int(durations[0])


def _is_round_rest_text(text: str) -> bool:
    return re.search(r"\b(?:round|rounds)\b", text, re.IGNORECASE) is not None


def _is_movement_rest_text(text: str) -> bool:
    return (
        re.search(
            r"\b(?:exercise|exercises|movement|movements)\b",
            text,
            re.IGNORECASE,
        )
        is not None
    )


def _request_exercise_from_block(
    block: dict[str, Any],
) -> PostRoutinesRequestExercise:
    return _request_exercise(
        template_id=block["selected_hevy_template"]["id"],
        superset_id=block.get("superset_id"),
        notes=block["notes"],
        sets=block["proposed_sets"],
        template=block["selected_hevy_template"],
    )


def _request_exercise(  # noqa: PLR0913
    *,
    template_id: str,
    superset_id: int | None,
    notes: str,
    sets: list[dict[str, Any]],
    rest_seconds: int | None = None,
    template: dict[str, Any] | None = None,
) -> PostRoutinesRequestExercise:
    if rest_seconds is None:
        rest_seconds = _rest_seconds_from_sets(sets, template=template)

    return PostRoutinesRequestExercise(
        exercise_template_id=template_id,
        superset_id=superset_id,
        notes=notes,
        rest_seconds=rest_seconds,
        sets=[
            PostRoutinesRequestSet(
                **{key: value for key, value in set_row.items() if not key.startswith("_")}
            )
            for set_row in sets
        ],
    )


def _rest_seconds_from_sets(
    sets: list[dict[str, Any]],
    *,
    template: dict[str, Any] | None = None,
) -> int:
    if _is_cardio_machine_template(template):
        return 0
    for set_row in sets:
        duration_seconds = set_row.get("duration_seconds")
        if duration_seconds is not None:
            return int(duration_seconds)
    return 0


def _is_cardio_machine_template(template: dict[str, Any] | None) -> bool:
    if template is None:
        return False
    return template.get("equipment") == "machine" and template.get("type") in {
        "duration",
        "distance_duration",
    }


def _superset_ids_by_position(workout: TrueCoachWorkout) -> dict[int, int]:
    try:
        order = parse_workout_order(str(workout.short_description or ""))
    except ValueError:
        return {}
    superset_index = build_superset_index(order)
    if not superset_index:
        return {}
    return {
        position: superset_index[superset_group]
        for position, metadata in order.items()
        if bool(metadata.get("is_superset"))
        and isinstance((superset_group := metadata.get("superset_group")), str)
        and superset_group in superset_index
    }


def _format_agent_next_actions(items: list[ReviewItem]) -> list[str]:
    lines = ["## Agent Next Actions", ""]
    blocking_actions = _blocking_agent_actions(items)
    if blocking_actions:
        lines.append("Blocking actions:")
        lines.extend(f"- {action}" for action in blocking_actions)
    else:
        lines.append("No blocking next actions.")
    warning_actions = _warning_actions(items)
    if warning_actions:
        lines.append("")
        lines.append("Warning actions:")
        lines.extend(f"- {action}" for action in warning_actions)
    lines.append("")
    return lines


def _format_safety_status(safety: SafetyStatus) -> str:
    return "Safety: automatic-safe" if safety["auto_safe"] else "Safety: review-required"


def _format_review_required_reasons(safety: SafetyStatus) -> list[str]:
    reasons = safety["review_required_reasons"]
    if not reasons:
        return []
    return ["Review-required reasons:", *[f"- {reason}" for reason in reasons], ""]


def _blocking_agent_actions(items: list[ReviewItem]) -> list[str]:
    return [
        _format_required_template_action(required_template)
        for item in items
        for required_template in required_templates_for_blockers(
            item.required_hevy_templates,
            item.planned_blocks,
        )
        if required_template.status in BLOCKING_REQUIRED_TEMPLATE_STATUSES
    ]


def _warning_actions(items: list[ReviewItem]) -> list[str]:
    actions: list[str] = []
    for item in items:
        for warning in item.warnings:
            action = _format_warning_action(item, warning)
            if action is not None:
                actions.append(action)
    return actions


def _format_required_template_action(required_template: RequiredHevyTemplate) -> str:
    spec = required_template.spec
    source_ids = ", ".join(
        str(source_id) for source_id in required_template.source_workout_item_ids
    )
    if required_template.status == "ambiguous":
        matching_ids = ", ".join(required_template.matching_template_ids)
        return (
            f'Resolve ambiguous Hevy template "{spec.title}" '
            f"for True Coach Workout Item {source_ids}; "
            f"matching template IDs: {matching_ids}."
        )
    other_muscles = ", ".join(spec.other_muscles) if spec.other_muscles else "none"
    return (
        f'Create required Hevy template "{spec.title}" '
        f"(type: {spec.expected_type}; equipment: {spec.equipment_category}; "
        f"muscle group: {spec.muscle_group}; other muscles: {other_muscles}) "
        f"for True Coach Workout Item {source_ids}."
    )


def _format_warning_action(item: ReviewItem, warning: str) -> str | None:
    source_text = _format_item_source_text(item)
    if warning == NO_LINKED_TEMPLATE_WARNING:
        return f"Add a True Coach to Hevy template mapping for True Coach {source_text}."
    if warning == NO_DETERMINISTIC_SET_PARSER_WARNING:
        return f"Add a deterministic set parser fixture or override for True Coach {source_text}."
    return None


def _format_item_source_text(item: ReviewItem) -> str:
    return (
        f'Workout Item {item.source_id} "{item.name}" with info "{item.info}" '
        f'and comment "{item.comment or "none"}"'
    )


def _template_to_dict(template: HevyAppExercise | None) -> dict[str, str | None] | None:
    if template is None:
        return None
    return {
        "id": template.id,
        "name": template.name,
        "type": template.type,
        "equipment": template.equipment,
    }


def _required_template_to_dict(
    required_template: RequiredHevyTemplate,
) -> dict[str, str | list[int] | list[str]]:
    spec = required_template.spec
    return {
        "title": spec.title,
        "expected_type": spec.expected_type,
        "equipment_category": spec.equipment_category,
        "muscle_group": spec.muscle_group,
        "other_muscles": list(spec.other_muscles),
        "status": required_template.status,
        "source_workout_item_ids": list(required_template.source_workout_item_ids),
        "matching_template_ids": list(required_template.matching_template_ids),
    }


def _planned_block_to_dict(block: PlannedBlock) -> dict[str, Any]:
    return {
        "source_id": block.source_id,
        "superset_id": block.superset_id,
        "block_index": block.block_index,
        "block_kind": block.block_kind,
        "source_text": block.source_text,
        "original_source_text": block.original_source_text,
        "notes": block.notes,
        "movement_name": block.movement_name,
        "movement_target": block.movement_target,
        "selected_hevy_template": _template_to_dict(block.selected_hevy_template),
        "required_hevy_templates": [
            _required_template_to_dict(required_template)
            for required_template in block.required_hevy_templates
        ],
        "proposed_sets": _sets_with_provenance_to_dict(
            block.proposed_sets,
            block.set_provenance,
        ),
        "notes_only": block.notes_only,
        "warnings": block.warnings,
        "blockers": block.blockers,
    }


def _parsed_circuit_block_to_dict(block: ParsedCircuitBlock | None) -> dict[str, Any] | None:
    if block is None:
        return None
    return asdict(block)


def _format_template(template: HevyAppExercise | None) -> str:
    if template is None:
        return "Selected Hevy template: unknown"
    return f"Selected Hevy template: {template.name} ({template.id})"


def _format_required_template(required_template: RequiredHevyTemplate) -> str:
    spec = required_template.spec
    other_muscles = ", ".join(spec.other_muscles) if spec.other_muscles else "none"
    source_ids = ", ".join(
        str(source_id) for source_id in required_template.source_workout_item_ids
    )
    return (
        f"{spec.title} | type: {spec.expected_type} | "
        f"equipment: {spec.equipment_category} | muscle group: {spec.muscle_group} | "
        f"other muscles: {other_muscles} | status: {required_template.status} | "
        f"source IDs: {source_ids}"
    )


def _format_planned_block(block: PlannedBlock) -> list[str]:
    lines = [
        f"- Block {block.block_index}: {_format_block_kind(block.block_kind)}",
        f"  Source ID: {block.source_id}",
        f"  Source text: {block.source_text}",
        f"  Original source text: {block.original_source_text}",
    ]
    if block.movement_name is not None:
        lines.append(f"  Movement: {block.movement_name}")
    if block.movement_target is not None:
        lines.append(f"  Movement target: {block.movement_target}")
    lines.extend(
        [
            f"  Notes: {block.notes}",
            f"  Notes-only: {'yes' if block.notes_only else 'no'}",
            f"  {_format_template(block.selected_hevy_template)}",
            "  Proposed sets:",
        ]
    )
    if block.proposed_sets:
        lines.extend(f"  - {_format_set(proposed_set)}" for proposed_set in block.proposed_sets)
    else:
        lines.append("  - unavailable")
    if block.required_hevy_templates:
        lines.append("  Required Hevy templates:")
        lines.extend(
            f"  - {_format_required_template(required_template)}"
            for required_template in block.required_hevy_templates
        )
    if block.warnings:
        lines.extend(f"  WARNING: {warning}" for warning in block.warnings)
    if block.blockers:
        lines.extend(f"  BLOCKER: {blocker}" for blocker in block.blockers)
    return lines


def _format_block_kind(block_kind: PlannedBlockKind) -> str:
    if block_kind == "isometric_hold":
        return "Isometric hold"
    if block_kind == "dynamic_reps":
        return "Dynamic reps"
    if block_kind == "amrap_movement":
        return "AMRAP movement"
    return "Circuit movement"


def _set_to_dict(value: PostRoutinesRequestSet) -> dict[str, int | float | str]:
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    return value.dict(exclude_none=True)


def _sets_with_provenance_to_dict(
    sets: list[PostRoutinesRequestSet],
    set_provenance: list[SetProvenance],
) -> list[dict[str, Any]]:
    return [
        _set_to_dict(proposed_set) | _provenance_to_dict(provenance)
        for proposed_set, provenance in zip(sets, set_provenance, strict=True)
    ]


def _provenance_to_dict(provenance: SetProvenance) -> dict[str, SetProvenance]:
    return {"_provenance": provenance} if provenance else {}


def _format_set(value: PostRoutinesRequestSet) -> str:
    data = _set_to_dict(value)
    return "; ".join(f"{key}: {data[key]}" for key in SET_DISPLAY_KEYS if key in data)
