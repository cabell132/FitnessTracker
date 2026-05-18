"""Build read-only True Coach to Hevy sync review bundles."""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any, Literal

from fitness_tracker.apis.hevy_app.types import (
    PostRoutinesRequestBody,
    PostRoutinesRequestExercise,
    PostRoutinesRequestSet,
)
from fitness_tracker.database import Store
from fitness_tracker.database.models import HevyAppExercise, TrueCoachExercise
from fitness_tracker.database.models.hevy_app import HevyAppSets, HevyAppWorkout, HevyAppWorkoutItem
from fitness_tracker.database.models.true_coach import TrueCoachWorkout, TrueCoachWorkoutItem
from fitness_tracker.database.tx import Tx
from fitness_tracker.sync._circuit_block_parser import (
    ParsedCircuitMovement,
    ParsedCircuitBlock,
    parse_circuit_block,
)
from fitness_tracker.sync._true_coach_html import (
    build_superset_index,
    parse_prescribed_sets,
    parse_workout_order,
)
from fitness_tracker.sync.ports import HevyRoutineWriter

SET_DISPLAY_KEYS = ("type", "weight_kg", "reps", "distance_meters", "duration_seconds")
BLOCKING_REQUIRED_TEMPLATE_STATUSES = frozenset({"missing", "ambiguous"})
NO_LINKED_TEMPLATE_WARNING = "No linked Hevy exercise template found."
NO_DETERMINISTIC_SET_PARSER_WARNING = "No deterministic set parser result found."
NO_MATCHING_HISTORY_LOAD_WARNING = "No matching Athlete history load found."
CIRCUIT_BLOCK_CONTEXT_PATTERN = re.compile(r"\b(?:amrap|circuit|\d+\s*rounds?)\b", re.IGNORECASE)
RequiredTemplateStatus = Literal["existing", "missing", "ambiguous"]
PhaseKind = Literal["isometric_hold", "dynamic_reps"]
PlannedBlockKind = Literal["isometric_hold", "dynamic_reps", "circuit_movement", "amrap_movement"]
WeightProvenance = Literal["athlete_history", "calculated_dropset"]
type SetSignature = tuple[str, str, int]
type SetProvenance = dict[str, WeightProvenance]


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


@dataclass(frozen=True)
class ReviewItem:
    """One True Coach workout item review row."""

    source_id: int
    superset_id: int | None
    name: str
    info: str
    comment: str
    selected_hevy_template: HevyAppExercise | None
    required_hevy_templates: list[RequiredHevyTemplate]
    proposed_sets: list[PostRoutinesRequestSet]
    set_provenance: list[SetProvenance]
    planned_blocks: list[PlannedBlock]
    parsed_circuit_block: ParsedCircuitBlock | None
    warnings: list[str]
    blockers: list[str]


@dataclass(frozen=True)
class RequiredTemplateSpec:
    """Configured Hevy exercise template required by an override rule."""

    title: str
    expected_type: str
    equipment_category: str
    muscle_group: str
    other_muscles: tuple[str, ...]


@dataclass(frozen=True)
class TemplateOverrideRule:
    """Config-driven deterministic item-level template override rule."""

    source_template_names: tuple[str, ...]
    item_patterns: tuple[re.Pattern[str], ...]
    required_template: RequiredTemplateSpec


@dataclass(frozen=True)
class TemplateMatchContext:
    """Candidate item text used to match template override rules."""

    item: TrueCoachWorkoutItem
    selected_template: HevyAppExercise | None
    text: str


@dataclass(frozen=True)
class RequiredHevyTemplate:
    """Required Hevy exercise template and local catalog resolution status."""

    spec: RequiredTemplateSpec
    status: RequiredTemplateStatus
    source_workout_item_ids: tuple[int, ...]
    matching_template_ids: tuple[str, ...]


@dataclass(frozen=True)
class PlannedBlock:
    """One Hevy Routine exercise block planned from part of a True Coach Workout Item."""

    source_id: int
    superset_id: int | None
    block_index: int
    block_kind: PlannedBlockKind
    source_text: str
    original_source_text: str
    notes: str
    movement_name: str | None
    movement_target: str | None
    selected_hevy_template: HevyAppExercise | None
    required_hevy_templates: list[RequiredHevyTemplate]
    proposed_sets: list[PostRoutinesRequestSet]
    set_provenance: list[SetProvenance]
    warnings: list[str]
    blockers: list[str]


@dataclass(frozen=True)
class ParsedPhase:
    """Deterministic phase parsed from a mixed-mode Coach prescription."""

    kind: PhaseKind
    source_text: str
    proposed_sets: list[PostRoutinesRequestSet]


@dataclass(frozen=True)
class PhaseTemplateSelection:
    """Inputs for choosing a phase-specific Hevy template."""

    phase_kind: PhaseKind
    selected_template: HevyAppExercise | None
    required_templates: list[RequiredHevyTemplate]


@dataclass(frozen=True)
class HistoricalLoad:
    """A usable Athlete-history load for one planned Routine set."""

    weight_kg: float


DEFAULT_TEMPLATE_OVERRIDE_RULES_PATH = Path(__file__).with_name("template_override_rules.json")
MIXED_PHASE_SPLIT_PATTERN = re.compile(r"\s+(?:then|followed by)\s+|[;,]\s*", re.IGNORECASE)
SET_PRESCRIPTION_MARKER_PATTERN = re.compile(r"\b\d+\s*[xX]\s*")
DURATION_PHASE_PATTERN = re.compile(
    r"(?P<count>\d+)\s*[xX]\s*(?P<seconds>\d+)\s*(?:s|sec|secs|second|seconds)\b",
    re.IGNORECASE,
)
ISO_PHASE_PATTERN = re.compile(r"\b(?:iso|isometric|hold)\b", re.IGNORECASE)


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
                self._review_item(uow, item, superset_ids.get(item.position or index))
                for index, item in enumerate(sorted_items, start=1)
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

    def write_apply_request(self, workout_id: int) -> ApplyResult:
        """Validate a review plan and write the Hevy Routine request body.

        Args:
            workout_id (int): True Coach workout id.

        Returns:
            ApplyResult: Review bundle and dry-run request path.
        """
        bundle = self.write_review(workout_id)
        plan = json.loads(bundle.plan_path.read_text(encoding="utf-8"))
        request_body = _build_hevy_routine_request(plan)
        request_path = bundle.directory / "hevy-request.json"
        request_path.write_text(
            json.dumps(request_body.model_dump(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
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

    def _review_item(
        self,
        uow: Tx,
        item: TrueCoachWorkoutItem,
        superset_id: int | None,
    ) -> ReviewItem:
        template = self._selected_template(uow, item)
        required_templates = self._required_templates(uow, item, template)
        parsed_circuit_block = _parse_circuit_block_context(item)
        planned_blocks = self._planned_blocks(
            uow, item, template, superset_id, parsed_circuit_block
        )
        if planned_blocks:
            proposed_sets: list[PostRoutinesRequestSet] = []
            set_provenance: list[SetProvenance] = []
        else:
            proposed_sets = parse_prescribed_sets(item.info or "")
            proposed_sets, set_provenance = _enrich_sets_from_history(uow, template, proposed_sets)
        warnings: list[str] = []
        if template is None:
            warnings.append(NO_LINKED_TEMPLATE_WARNING)
        if item.info and not proposed_sets and not planned_blocks:
            warnings.append(NO_DETERMINISTIC_SET_PARSER_WARNING)
        if _has_missing_history_load(template, proposed_sets) or any(
            _has_missing_history_load(block.selected_hevy_template, block.proposed_sets)
            for block in planned_blocks
        ):
            warnings.append(NO_MATCHING_HISTORY_LOAD_WARNING)
        return ReviewItem(
            source_id=item.id,
            superset_id=superset_id,
            name=item.name,
            info=item.info or "",
            comment=item.comment or "",
            selected_hevy_template=template,
            required_hevy_templates=required_templates,
            proposed_sets=proposed_sets,
            set_provenance=set_provenance,
            planned_blocks=planned_blocks,
            parsed_circuit_block=parsed_circuit_block,
            warnings=warnings,
            blockers=_required_template_blockers(
                _required_templates_for_blockers(required_templates, planned_blocks)
            )
            + _block_blockers(planned_blocks),
        )

    def _selected_template(
        self,
        uow: Tx,
        item: TrueCoachWorkoutItem,
    ) -> HevyAppExercise | None:
        exercise = item.exercise
        if isinstance(exercise, TrueCoachExercise) and isinstance(
            exercise.hevy_app, HevyAppExercise
        ):
            return exercise.hevy_app
        if item.tracker and isinstance(item.tracker.exercise.hevy_app, HevyAppExercise):
            return item.tracker.exercise.hevy_app
        tracker_exercise = uow.tracker.get_exercise(name=item.name)
        if tracker_exercise and isinstance(tracker_exercise.hevy_app, HevyAppExercise):
            return tracker_exercise.hevy_app
        return None

    def _required_templates(
        self,
        uow: Tx,
        item: TrueCoachWorkoutItem,
        selected_template: HevyAppExercise | None,
    ) -> list[RequiredHevyTemplate]:
        return self._required_templates_for_context(
            uow,
            TemplateMatchContext(
                item=item,
                selected_template=selected_template,
                text=item.info or item.comment or "",
            ),
        )

    def _planned_blocks(  # noqa: PLR0913
        self,
        uow: Tx,
        item: TrueCoachWorkoutItem,
        selected_template: HevyAppExercise | None,
        superset_id: int | None,
        parsed_circuit_block: ParsedCircuitBlock | None,
    ) -> list[PlannedBlock]:
        if parsed_circuit_block is not None:
            return self._planned_circuit_blocks(uow, item, superset_id, parsed_circuit_block)

        phases = _parse_mixed_mode_phases(item.info or "")
        if not phases:
            return []

        blocks: list[PlannedBlock] = []
        for index, phase in enumerate(phases, start=1):
            required_templates = (
                self._required_templates_for_context(
                    uow,
                    TemplateMatchContext(
                        item=item,
                        selected_template=selected_template,
                        text=phase.source_text,
                    ),
                )
                if phase.kind == "isometric_hold"
                else []
            )
            phase_template = _selected_template_for_phase(
                uow,
                PhaseTemplateSelection(
                    phase_kind=phase.kind,
                    selected_template=selected_template,
                    required_templates=required_templates,
                ),
            )
            proposed_sets, set_provenance = _enrich_sets_from_history(
                uow, phase_template, phase.proposed_sets
            )
            blocks.append(
                PlannedBlock(
                    source_id=item.id,
                    superset_id=superset_id,
                    block_index=index,
                    block_kind=phase.kind,
                    source_text=phase.source_text,
                    original_source_text=item.info or "",
                    notes=f"{phase.source_text}\nSource: {item.info or ''}",
                    movement_name=None,
                    movement_target=None,
                    selected_hevy_template=phase_template,
                    required_hevy_templates=required_templates,
                    proposed_sets=proposed_sets,
                    set_provenance=set_provenance,
                    warnings=[],
                    blockers=[],
                )
            )
        return blocks

    def _planned_circuit_blocks(  # noqa: PLR0913
        self,
        uow: Tx,
        item: TrueCoachWorkoutItem,
        superset_id: int | None,
        parsed_block: ParsedCircuitBlock,
    ) -> list[PlannedBlock]:
        blocks: list[PlannedBlock] = []
        block_kind: PlannedBlockKind = (
            "amrap_movement" if parsed_block.kind == "amrap" else "circuit_movement"
        )
        for index, movement in enumerate(parsed_block.movements, start=1):
            template = _selected_template_for_movement(uow, movement)
            proposed_sets = _sets_for_circuit_movement(movement)
            proposed_sets, set_provenance = _enrich_sets_from_history(uow, template, proposed_sets)
            warnings: list[str] = []
            blockers: list[str] = []
            if template is None:
                warnings.append(NO_LINKED_TEMPLATE_WARNING)
                blockers.append(f"Missing required Hevy exercise mapping: {movement.name}")
            if parsed_block.requires_agent_decision:
                blockers.append(
                    "Circuit block requires Agent decision: "
                    f"{parsed_block.agent_decision_reason or 'unspecified'}"
                )
            if movement.target and not proposed_sets:
                warnings.append(NO_DETERMINISTIC_SET_PARSER_WARNING)
            blocks.append(
                PlannedBlock(
                    source_id=item.id,
                    superset_id=superset_id,
                    block_index=index,
                    block_kind=block_kind,
                    source_text=movement.source_text,
                    original_source_text=item.info or "",
                    notes=_circuit_movement_notes(item, movement, parsed_block),
                    movement_name=movement.name,
                    movement_target=movement.target,
                    selected_hevy_template=template,
                    required_hevy_templates=[],
                    proposed_sets=proposed_sets,
                    set_provenance=set_provenance,
                    warnings=warnings,
                    blockers=blockers,
                )
            )
        return blocks

    def _required_templates_for_context(
        self,
        uow: Tx,
        context: TemplateMatchContext,
    ) -> list[RequiredHevyTemplate]:
        rules = _load_template_override_rules(DEFAULT_TEMPLATE_OVERRIDE_RULES_PATH)
        matched_specs = [
            rule.required_template for rule in rules if _rule_matches_text(rule, context)
        ]
        return [
            _resolve_required_template(uow, spec, source_workout_item_id=context.item.id)
            for spec in matched_specs
        ]

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
            "superset_id": item.superset_id,
            "name": item.name,
            "info": item.info,
            "comment": item.comment,
            "selected_hevy_template": _template_to_dict(template),
            "required_hevy_templates": [
                _required_template_to_dict(required_template)
                for required_template in item.required_hevy_templates
            ],
            "proposed_sets": [
                _set_to_dict(proposed_set) | _provenance_to_dict(provenance)
                for proposed_set, provenance in zip(
                    item.proposed_sets, item.set_provenance, strict=True
                )
            ],
            "planned_blocks": [_planned_block_to_dict(block) for block in item.planned_blocks],
            "parsed_circuit_block": _parsed_circuit_block_to_dict(item.parsed_circuit_block),
            "warnings": item.warnings,
            "blockers": item.blockers,
        }

    def _report(self, workout: TrueCoachWorkout, items: list[ReviewItem]) -> str:
        lines = [
            f"# True Coach to Hevy Sync Review: {workout.id}",
            "",
            f"Workout: {workout.title or 'Untitled'}",
            f"Due: {workout.due.isoformat() if workout.due else 'unknown'}",
            "",
        ]
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


def _build_hevy_routine_request(plan: dict[str, Any]) -> PostRoutinesRequestBody:
    blockers = _apply_blockers(plan)
    if blockers:
        raise SyncApplyError("; ".join(blockers))
    workout = plan["workout"]
    return PostRoutinesRequestBody.build(
        title=_routine_title(workout),
        notes="",
        exercises=[
            exercise for item in plan["items"] for exercise in _request_exercises_for_item(item)
        ],
    )


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
        if not block.get("proposed_sets")
    )
    return blockers


def _is_unsplit_required_mixed_mode_item(item: dict[str, Any]) -> bool:
    info = item.get("info") or ""
    return (
        not item.get("planned_blocks")
        and ISO_PHASE_PATTERN.search(info) is not None
        and re.search(r"\b(?:then|followed by)\b", info, re.IGNORECASE) is not None
    )


def _parse_circuit_block_context(item: TrueCoachWorkoutItem) -> ParsedCircuitBlock | None:
    name = item.name or ""
    info = item.info or ""
    if not (bool(item.is_circuit) or CIRCUIT_BLOCK_CONTEXT_PATTERN.search(f"{name}\n{info}")):
        return None
    return parse_circuit_block(name=name, text=info)


def _routine_title(workout: dict[str, Any]) -> str:
    due = workout.get("due")
    due_text = datetime.fromisoformat(due).strftime("%d %b %Y") if due else ""
    return f"{due_text}\n{workout.get('title') or ''}\n{workout['id']}"


def _request_exercises_for_item(item: dict[str, Any]) -> list[PostRoutinesRequestExercise]:
    blocks = item.get("planned_blocks", [])
    if blocks:
        return [_request_exercise_from_block(block) for block in blocks]
    return [
        _request_exercise(
            template_id=item["selected_hevy_template"]["id"],
            superset_id=item.get("superset_id"),
            notes=_item_notes(item),
            sets=item["proposed_sets"],
        )
    ]


def _item_notes(item: dict[str, Any]) -> str:
    return "\n".join(
        part for part in (item.get("info") or item["name"], item.get("comment") or "") if part
    )


def _request_exercise_from_block(block: dict[str, Any]) -> PostRoutinesRequestExercise:
    return _request_exercise(
        template_id=block["selected_hevy_template"]["id"],
        superset_id=block.get("superset_id"),
        notes=block["notes"],
        sets=block["proposed_sets"],
    )


def _request_exercise(  # noqa: PLR0913
    *,
    template_id: str,
    superset_id: int | None,
    notes: str,
    sets: list[dict[str, Any]],
) -> PostRoutinesRequestExercise:
    return PostRoutinesRequestExercise(
        exercise_template_id=template_id,
        superset_id=superset_id,
        notes=notes,
        rest_seconds=_rest_seconds_from_sets(sets),
        sets=[
            PostRoutinesRequestSet(
                **{key: value for key, value in set_row.items() if not key.startswith("_")}
            )
            for set_row in sets
        ],
    )


def _rest_seconds_from_sets(sets: list[dict[str, Any]]) -> int:
    for set_row in sets:
        duration_seconds = set_row.get("duration_seconds")
        if duration_seconds is not None:
            return int(duration_seconds)
    return 0


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


@cache
def _load_template_override_rules(path: Path) -> tuple[TemplateOverrideRule, ...]:
    raw_rules = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        TemplateOverrideRule(
            source_template_names=tuple(rule["source_template_names"]),
            item_patterns=tuple(
                re.compile(pattern, re.IGNORECASE) for pattern in rule["item_patterns"]
            ),
            required_template=RequiredTemplateSpec(
                title=rule["required_template"]["title"],
                expected_type=rule["required_template"]["expected_type"],
                equipment_category=rule["required_template"]["equipment_category"],
                muscle_group=rule["required_template"]["muscle_group"],
                other_muscles=tuple(rule["required_template"].get("other_muscles", [])),
            ),
        )
        for rule in raw_rules["template_selection_overrides"]
    )


def _rule_matches_text(rule: TemplateOverrideRule, context: TemplateMatchContext) -> bool:
    source_names = {name.casefold() for name in rule.source_template_names}
    item = context.item
    candidate_names = {item.name.casefold()}
    if context.selected_template is not None:
        candidate_names.add(context.selected_template.name.casefold())
    if candidate_names.isdisjoint(source_names):
        return False
    item_text = f"{item.name} {context.text} {item.comment or ''}"
    return all(pattern.search(item_text) for pattern in rule.item_patterns)


def _resolve_required_template(
    uow: Tx,
    spec: RequiredTemplateSpec,
    *,
    source_workout_item_id: int,
) -> RequiredHevyTemplate:
    matching_templates = [
        template
        for template in uow.session.get_all(HevyAppExercise)
        if template.name.casefold() == spec.title.casefold()
    ]
    matching_ids = tuple(sorted(template.id for template in matching_templates))
    return RequiredHevyTemplate(
        spec=spec,
        status=_required_template_status(len(matching_templates)),
        source_workout_item_ids=(source_workout_item_id,),
        matching_template_ids=matching_ids,
    )


def _required_template_status(match_count: int) -> RequiredTemplateStatus:
    if match_count == 0:
        return "missing"
    if match_count == 1:
        return "existing"
    return "ambiguous"


def _required_template_blockers(
    required_templates: list[RequiredHevyTemplate],
) -> list[str]:
    return [
        f"{required_template.status.title()} required Hevy template: {required_template.spec.title}"
        for required_template in required_templates
        if required_template.status in BLOCKING_REQUIRED_TEMPLATE_STATUSES
    ]


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


def _blocking_agent_actions(items: list[ReviewItem]) -> list[str]:
    return [
        _format_required_template_action(required_template)
        for item in items
        for required_template in _required_templates_for_blockers(
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


def _required_templates_for_blockers(
    item_required_templates: list[RequiredHevyTemplate],
    planned_blocks: list[PlannedBlock],
) -> list[RequiredHevyTemplate]:
    if not planned_blocks:
        return item_required_templates
    return [
        required_template
        for block in planned_blocks
        for required_template in block.required_hevy_templates
    ]


def _block_blockers(planned_blocks: list[PlannedBlock]) -> list[str]:
    return [blocker for block in planned_blocks for blocker in block.blockers]


def _parse_mixed_mode_phases(description: str) -> list[ParsedPhase]:
    parts = _mixed_mode_phase_parts(description)
    if len(parts) < 2:
        return []

    phases: list[ParsedPhase] = []
    for part in parts:
        phase = _parse_phase(part)
        if phase is None:
            return []
        phases.append(phase)

    phase_kinds = {phase.kind for phase in phases}
    if phase_kinds != {"isometric_hold", "dynamic_reps"}:
        return []
    return phases


def _mixed_mode_phase_parts(description: str) -> list[str]:
    parts: list[str] = []
    for line in description.splitlines():
        for part in MIXED_PHASE_SPLIT_PATTERN.split(line):
            stripped = part.strip()
            if stripped and SET_PRESCRIPTION_MARKER_PATTERN.search(stripped):
                parts.append(stripped)
    return parts


def _parse_phase(text: str) -> ParsedPhase | None:
    if (duration_sets := _parse_duration_sets(text)) and ISO_PHASE_PATTERN.search(text):
        return ParsedPhase(
            kind="isometric_hold",
            source_text=text,
            proposed_sets=duration_sets,
        )
    if reps_sets := parse_prescribed_sets(text):
        return ParsedPhase(kind="dynamic_reps", source_text=text, proposed_sets=reps_sets)
    return None


def _parse_duration_sets(text: str) -> list[PostRoutinesRequestSet]:
    match = DURATION_PHASE_PATTERN.search(text)
    if not match:
        return []
    return [
        PostRoutinesRequestSet(type="normal", duration_seconds=int(match.group("seconds")))
        for _ in range(int(match.group("count")))
    ]


def _selected_template_for_phase(
    uow: Tx,
    selection: PhaseTemplateSelection,
) -> HevyAppExercise | None:
    if selection.phase_kind == "dynamic_reps":
        return selection.selected_template
    if len(selection.required_templates) != 1:
        return None
    required_template = selection.required_templates[0]
    if required_template.status != "existing" or len(required_template.matching_template_ids) != 1:
        return None
    return uow.session.get(HevyAppExercise, id=required_template.matching_template_ids[0])


def _selected_template_for_movement(
    uow: Tx,
    movement: ParsedCircuitMovement,
) -> HevyAppExercise | None:
    tracker_exercise = uow.tracker.get_exercise(name=movement.name)
    if tracker_exercise and isinstance(tracker_exercise.hevy_app, HevyAppExercise):
        return tracker_exercise.hevy_app
    matching_templates = [
        template
        for template in uow.session.get_all(HevyAppExercise)
        if template.name.casefold() == movement.name.casefold()
    ]
    if len(matching_templates) == 1:
        return matching_templates[0]
    return None


def _sets_for_circuit_movement(
    movement: ParsedCircuitMovement,
) -> list[PostRoutinesRequestSet]:
    target = movement.target.strip()
    if not target:
        return []
    if match := re.fullmatch(r"(?P<reps>\d+)(?:\s+(?:each side|es))?", target, re.IGNORECASE):
        return [PostRoutinesRequestSet(type="normal", reps=int(match.group("reps")))]
    if match := re.fullmatch(r"(?P<distance>\d+)\s*(?:m|meters?)", target, re.IGNORECASE):
        return [PostRoutinesRequestSet(type="normal", distance_meters=int(match.group("distance")))]
    if match := re.fullmatch(
        r"(?P<seconds>\d+)\s*(?:s|sec|secs|second|seconds)", target, re.IGNORECASE
    ):
        return [PostRoutinesRequestSet(type="normal", duration_seconds=int(match.group("seconds")))]
    if match := re.fullmatch(
        r"(?P<minutes>\d+)\s*(?:min|mins|minute|minutes)(?:\s+\w+)?",
        target,
        re.IGNORECASE,
    ):
        return [
            PostRoutinesRequestSet(type="normal", duration_seconds=int(match.group("minutes")) * 60)
        ]
    return []


def _circuit_movement_notes(
    item: TrueCoachWorkoutItem,
    movement: ParsedCircuitMovement,
    parsed_block: ParsedCircuitBlock,
) -> str:
    parts = [
        movement.source_text,
        f"Movement: {movement.name}",
        f"Movement target: {movement.target or 'none'}",
    ]
    if parsed_block.round_count is not None:
        parts.append(f"Rounds: {parsed_block.round_count}")
    if parsed_block.amrap_time_cap_seconds is not None:
        parts.append(f"AMRAP time cap seconds: {parsed_block.amrap_time_cap_seconds}")
    if parsed_block.rests:
        parts.append("Rest lines: " + "; ".join(rest.source_text for rest in parsed_block.rests))
    if parsed_block.metadata_lines:
        parts.append(
            "Metadata lines: " + "; ".join(line.source_text for line in parsed_block.metadata_lines)
        )
    parts.append(f"Source: {item.info or ''}")
    return "\n".join(parts)


def _enrich_sets_from_history(
    uow: Tx,
    template: HevyAppExercise | None,
    planned_sets: list[PostRoutinesRequestSet],
) -> tuple[list[PostRoutinesRequestSet], list[SetProvenance]]:
    provenance = [{} for _ in planned_sets]
    if template is None or not _is_weight_capable(template) or not planned_sets:
        return planned_sets, provenance

    enriched_sets = list(planned_sets)
    historical_loads = _historical_loads_by_signature(uow, template.id)
    last_normal_load: float | None = None
    for index, planned_set in enumerate(planned_sets):
        if planned_set.weight_kg is not None:
            last_normal_load = _updated_last_normal_load(
                planned_set, planned_set.weight_kg, last_normal_load
            )
            continue
        signature = _set_history_signature(planned_set)
        if signature is None:
            continue
        historical_load = _next_historical_load(historical_loads, signature)
        if historical_load is not None:
            enriched_sets[index] = _copy_set_with_weight(planned_set, historical_load.weight_kg)
            provenance[index] = _weight_provenance("athlete_history")
            last_normal_load = _updated_last_normal_load(
                planned_set, historical_load.weight_kg, last_normal_load
            )
        elif planned_set.type == "dropset" and last_normal_load is not None:
            enriched_sets[index] = _copy_set_with_weight(
                planned_set, _dropset_load(last_normal_load)
            )
            provenance[index] = _weight_provenance("calculated_dropset")
    return enriched_sets, provenance


def _is_weight_capable(template: HevyAppExercise) -> bool:
    return template.type in {"weight_reps", "weight_duration", "short_distance_weight"}


def _has_missing_history_load(
    template: HevyAppExercise | None,
    planned_sets: list[PostRoutinesRequestSet],
) -> bool:
    if template is None or not _is_weight_capable(template):
        return False
    return any(
        planned_set.weight_kg is None
        and (
            planned_set.reps is not None
            or planned_set.distance_meters is not None
            or planned_set.duration_seconds is not None
        )
        for planned_set in planned_sets
    )


def _historical_loads_by_signature(
    uow: Tx,
    exercise_template_id: str,
) -> dict[SetSignature, deque[HistoricalLoad]]:
    rows = (
        uow.session.query(HevyAppSets)
        .join(HevyAppWorkoutItem, HevyAppSets.workout_item_id == HevyAppWorkoutItem.id)
        .join(HevyAppWorkout, HevyAppWorkoutItem.workout_id == HevyAppWorkout.id)
        .filter(HevyAppWorkoutItem.exercise_id == exercise_template_id)
        .filter(HevyAppSets.weight_kg.isnot(None))
        .order_by(HevyAppWorkout.start_time.desc(), HevyAppWorkoutItem.index, HevyAppSets.index)
        .all()
    )
    historical_loads: dict[SetSignature, deque[HistoricalLoad]] = {}
    for set_row in rows:
        signature = _set_history_signature(set_row)
        if signature is None:
            continue
        historical_loads.setdefault(signature, deque()).append(
            HistoricalLoad(weight_kg=float(set_row.weight_kg))
        )
    return historical_loads


def _set_history_signature(value: Any) -> SetSignature | None:
    set_type = value.type
    if value.reps is not None:
        return (set_type, "reps", int(value.reps))
    if value.distance_meters is not None:
        return (set_type, "distance_meters", int(value.distance_meters))
    if value.duration_seconds is not None:
        return (set_type, "duration_seconds", int(value.duration_seconds))
    return None


def _next_historical_load(
    historical_loads: dict[SetSignature, deque[HistoricalLoad]],
    signature: SetSignature,
) -> HistoricalLoad | None:
    loads = historical_loads.get(signature)
    if not loads:
        return None
    return loads.popleft()


def _updated_last_normal_load(
    planned_set: PostRoutinesRequestSet,
    weight_kg: float,
    current: float | None,
) -> float | None:
    if planned_set.type == "normal":
        return weight_kg
    return current


def _dropset_load(normal_load: float) -> float:
    return round(normal_load * 0.8, 1)


def _weight_provenance(source: WeightProvenance) -> SetProvenance:
    return {"weight_kg": source}


def _copy_set_with_weight(
    planned_set: PostRoutinesRequestSet,
    weight_kg: float,
) -> PostRoutinesRequestSet:
    return PostRoutinesRequestSet(
        type=planned_set.type,
        weight_kg=weight_kg,
        reps=planned_set.reps,
        distance_meters=planned_set.distance_meters,
        duration_seconds=planned_set.duration_seconds,
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
        "proposed_sets": [
            _set_to_dict(proposed_set) | _provenance_to_dict(provenance)
            for proposed_set, provenance in zip(
                block.proposed_sets, block.set_provenance, strict=True
            )
        ],
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


def _provenance_to_dict(provenance: SetProvenance) -> dict[str, SetProvenance]:
    return {"_provenance": provenance} if provenance else {}


def _format_set(value: PostRoutinesRequestSet) -> str:
    data = _set_to_dict(value)
    return "; ".join(f"{key}: {data[key]}" for key in SET_DISPLAY_KEYS if key in data)
