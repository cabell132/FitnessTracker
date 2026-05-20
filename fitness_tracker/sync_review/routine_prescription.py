"""Routine prescription planning for True Coach to Hevy review."""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

from fitness_tracker.apis.hevy_app.types import PostRoutinesRequestSet
from fitness_tracker.database.models import HevyAppExercise, TrueCoachExercise
from fitness_tracker.database.models.hevy_app import HevyAppSets, HevyAppWorkout, HevyAppWorkoutItem
from fitness_tracker.database.models.true_coach import TrueCoachWorkoutItem
from fitness_tracker.database.tx import Tx
from fitness_tracker.sync._circuit_block_parser import (
    ParsedCircuitBlock,
    ParsedCircuitMovement,
    parse_circuit_block,
)
from fitness_tracker.sync._true_coach_html import parse_prescribed_sets
from fitness_tracker.sync_review.split_circuit.core import (
    SetRow,
    SplitCircuitExerciseNoteContext,
    SplitCircuitExercisePlan,
    SplitCircuitPrescription,
    SplitCircuitTemplateRef,
    SplitCircuitTemplateRequirement,
    plan_parsed_split_circuit,
    render_split_circuit_exercise_notes,
)

BLOCKING_REQUIRED_TEMPLATE_STATUSES = frozenset({"missing", "ambiguous"})
NO_LINKED_TEMPLATE_WARNING = "No linked Hevy exercise template found."
NO_DETERMINISTIC_SET_PARSER_WARNING = "No deterministic set parser result found."
NO_MATCHING_HISTORY_LOAD_WARNING = "No matching Athlete history load found."
HEVY_PLACEHOLDER_TEMPLATE_NAME = "#####PLACEHOLDER#####"
CIRCUIT_BLOCK_CONTEXT_PATTERN = re.compile(r"\b(?:amrap|circuit|\d+\s*rounds?)\b", re.IGNORECASE)
RequiredTemplateStatus = Literal["existing", "missing", "ambiguous"]
PhaseKind = Literal["isometric_hold", "dynamic_reps"]
PlannedBlockKind = Literal["isometric_hold", "dynamic_reps", "circuit_movement", "amrap_movement"]
WeightProvenance = Literal["athlete_history", "calculated_dropset"]
type SetSignature = tuple[str, str, int]
type SetProvenance = dict[str, WeightProvenance]

DEFAULT_TEMPLATE_OVERRIDE_RULES_PATH = Path(__file__).with_name("template_override_rules.json")
MIXED_PHASE_SPLIT_PATTERN = re.compile(r"\s+(?:then|followed by)\s+|[;,]\s*", re.IGNORECASE)
SET_PRESCRIPTION_MARKER_PATTERN = re.compile(r"\b\d+\s*[xX]\s*")
DURATION_PHASE_PATTERN = re.compile(
    r"(?P<count>\d+)\s*[xX]\s*(?P<seconds>\d+)\s*(?:s|sec|secs|second|seconds)\b",
    re.IGNORECASE,
)
ISO_PHASE_PATTERN = re.compile(r"\b(?:iso|isometric|hold)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ReviewItem:
    """One True Coach Workout Item planned for a Hevy Routine review."""

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
    notes_only: bool
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


class RoutinePrescriptionPlanner:
    """Plan one True Coach Workout Item as Hevy Routine review data."""

    def review_item(
        self,
        uow: Tx,
        item: TrueCoachWorkoutItem,
        superset_id: int | None,
    ) -> ReviewItem:
        """Plan one True Coach Workout Item for Routine creation review.

        Args:
            uow (Tx): Unit of work used for template and history lookups.
            item (TrueCoachWorkoutItem): True Coach Workout Item to plan.
            superset_id (int | None): Hevy superset id for this item, if any.

        Returns:
            ReviewItem: Planned review data for the Workout Item.
        """
        template = self._selected_template(uow, item)
        required_templates = self._required_templates(uow, item, template)
        parsed_circuit_block = parse_circuit_block_context(item)
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
                required_templates_for_blockers(required_templates, planned_blocks)
            )
            + block_blockers(planned_blocks),
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
                    notes_only=False,
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
        def resolve_template(
            movement_name: str,
            source_text: str,
        ) -> tuple[SplitCircuitTemplateRef | None, list[SplitCircuitTemplateRequirement]]:
            movement = ParsedCircuitMovement(
                name=movement_name,
                target="",
                source_text=source_text,
            )
            template, required_templates = self._selected_template_for_circuit_movement(
                uow, item, movement
            )
            return (
                _split_template_ref(template),
                [_split_requirement(required_template) for required_template in required_templates],
            )

        split_plan = plan_parsed_split_circuit(
            parsed_block=parsed_block,
            prescription=SplitCircuitPrescription(
                name=item.name or "",
                text=item.info or "",
                inherit_superset_context=superset_id is not None,
            ),
            resolve_template=resolve_template,
        )

        blocks: list[PlannedBlock] = []
        block_kind = _circuit_block_kind(parsed_block)
        for index, exercise in enumerate(split_plan.exercises, start=1):
            template = _hevy_template_for_split_exercise(uow, exercise)
            required_templates = [
                _required_template_from_split(requirement, source_workout_item_id=item.id)
                for requirement in exercise.template_requirements
            ]
            proposed_sets = [
                _post_routine_set_from_split_row(set_row) for set_row in exercise.set_rows
            ]
            proposed_sets, set_provenance = _enrich_sets_from_history(uow, template, proposed_sets)
            blocks.append(
                PlannedBlock(
                    source_id=item.id,
                    superset_id=superset_id,
                    block_index=index,
                    block_kind=block_kind,
                    source_text=exercise.source_text,
                    original_source_text=item.info or "",
                    notes=render_split_circuit_exercise_notes(
                        SplitCircuitExerciseNoteContext(
                            exercise=exercise,
                            plan=split_plan,
                            original_source_text=item.info or "",
                            include_metadata_lines=True,
                        )
                    ),
                    movement_name=exercise.name,
                    movement_target=exercise.target,
                    selected_hevy_template=template,
                    required_hevy_templates=required_templates,
                    proposed_sets=proposed_sets,
                    set_provenance=set_provenance,
                    notes_only=exercise.notes_only,
                    warnings=list(exercise.warnings),
                    blockers=list(exercise.blockers),
                )
            )
        return blocks

    def _selected_template_for_circuit_movement(
        self,
        uow: Tx,
        item: TrueCoachWorkoutItem,
        movement: ParsedCircuitMovement,
    ) -> tuple[HevyAppExercise | None, list[RequiredHevyTemplate]]:
        base_template = _selected_template_for_movement(uow, movement)
        required_templates = self._required_templates_for_context(
            uow,
            TemplateMatchContext(
                item=item,
                selected_template=base_template,
                text=movement.source_text,
            ),
        )
        return (
            _required_template_override_or_fallback(
                uow,
                fallback_template=base_template,
                required_templates=required_templates,
            ),
            required_templates,
        )

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


def parse_circuit_block_context(item: TrueCoachWorkoutItem) -> ParsedCircuitBlock | None:
    """Parse a True Coach Workout Item as a Circuit block when context supports it.

    Args:
        item (TrueCoachWorkoutItem): True Coach Workout Item to inspect.

    Returns:
        ParsedCircuitBlock | None: Parsed Circuit block, if the item has Circuit context.
    """
    name = item.name or ""
    info = item.info or ""
    if not (bool(item.is_circuit) or CIRCUIT_BLOCK_CONTEXT_PATTERN.search(f"{name}\n{info}")):
        return None
    return parse_circuit_block(name=name, text=info)


def required_templates_for_blockers(
    item_required_templates: list[RequiredHevyTemplate],
    planned_blocks: list[PlannedBlock],
) -> list[RequiredHevyTemplate]:
    """Return required templates that should contribute blocking actions.

    Args:
        item_required_templates (list[RequiredHevyTemplate]): Item-level required templates.
        planned_blocks (list[PlannedBlock]): Planned blocks parsed from the item.

    Returns:
        list[RequiredHevyTemplate]: Required templates that should block review completion.
    """
    if not planned_blocks:
        return item_required_templates
    return [
        required_template
        for block in planned_blocks
        for required_template in block.required_hevy_templates
    ]


def block_blockers(planned_blocks: list[PlannedBlock]) -> list[str]:
    """Flatten blockers carried by planned Routine blocks.

    Args:
        planned_blocks (list[PlannedBlock]): Planned blocks to inspect.

    Returns:
        list[str]: Blocker messages carried by the planned blocks.
    """
    return [blocker for block in planned_blocks for blocker in block.blockers]


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
    return _required_template_override_or_fallback(
        uow,
        fallback_template=None,
        required_templates=selection.required_templates,
    )


def _required_template_override_or_fallback(
    uow: Tx,
    *,
    fallback_template: HevyAppExercise | None,
    required_templates: list[RequiredHevyTemplate],
) -> HevyAppExercise | None:
    if len(required_templates) != 1:
        return fallback_template
    required_template = required_templates[0]
    if required_template.status != "existing" or len(required_template.matching_template_ids) != 1:
        return fallback_template
    return uow.session.get(HevyAppExercise, id=required_template.matching_template_ids[0])


def _selected_template_for_movement(
    uow: Tx,
    movement: ParsedCircuitMovement,
) -> HevyAppExercise | None:
    tracker_exercise = uow.tracker.get_exercise(name=movement.name)
    if (
        tracker_exercise
        and isinstance(tracker_exercise.hevy_app, HevyAppExercise)
        and not _is_placeholder_template(tracker_exercise.hevy_app)
    ):
        return tracker_exercise.hevy_app
    matching_templates = [
        template
        for template in uow.session.get_all(HevyAppExercise)
        if template.name.casefold() == movement.name.casefold()
        and not _is_placeholder_template(template)
    ]
    if len(matching_templates) == 1:
        return matching_templates[0]
    return None


def _split_template_ref(template: HevyAppExercise | None) -> SplitCircuitTemplateRef | None:
    if template is None:
        return None
    return SplitCircuitTemplateRef(
        id=template.id,
        name=template.name,
        type=template.type,
        equipment=template.equipment,
    )


def _split_requirement(
    required_template: RequiredHevyTemplate,
) -> SplitCircuitTemplateRequirement:
    spec = required_template.spec
    return SplitCircuitTemplateRequirement(
        title=spec.title,
        expected_type=spec.expected_type,
        equipment_category=spec.equipment_category,
        muscle_group=spec.muscle_group,
        other_muscles=spec.other_muscles,
        status=required_template.status,
        matching_template_ids=required_template.matching_template_ids,
    )


def _required_template_from_split(
    requirement: SplitCircuitTemplateRequirement,
    *,
    source_workout_item_id: int,
) -> RequiredHevyTemplate:
    return RequiredHevyTemplate(
        spec=RequiredTemplateSpec(
            title=requirement.title,
            expected_type=requirement.expected_type,
            equipment_category=requirement.equipment_category,
            muscle_group=requirement.muscle_group,
            other_muscles=requirement.other_muscles,
        ),
        status=requirement.status,
        source_workout_item_ids=(source_workout_item_id,),
        matching_template_ids=requirement.matching_template_ids,
    )


def _hevy_template_for_split_exercise(
    uow: Tx,
    exercise: SplitCircuitExercisePlan,
) -> HevyAppExercise | None:
    if exercise.selected_template is None:
        return None
    template = uow.session.get(HevyAppExercise, id=exercise.selected_template.id)
    if isinstance(template, HevyAppExercise):
        return template
    return None


def _post_routine_set_from_split_row(row: SetRow) -> PostRoutinesRequestSet:
    return PostRoutinesRequestSet(
        type=row.get("type", "normal"),
        weight_kg=row.get("weight_kg"),
        reps=row.get("reps"),
        distance_meters=row.get("distance_meters"),
        duration_seconds=row.get("duration_seconds"),
    )


def _is_placeholder_template(template: HevyAppExercise) -> bool:
    return template.name == HEVY_PLACEHOLDER_TEMPLATE_NAME


def _circuit_block_kind(parsed_block: ParsedCircuitBlock) -> PlannedBlockKind:
    if parsed_block.kind == "amrap":
        return "amrap_movement"
    return "circuit_movement"


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
