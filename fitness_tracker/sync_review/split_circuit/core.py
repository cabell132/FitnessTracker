"""Plain-data Split Circuit prescription planning."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from fitness_tracker.sync._circuit_block_parser import (
    ParsedCircuitBlock,
    ParsedCircuitMovement,
    parse_circuit_block,
)

SplitCircuitKind = Literal["circuit", "amrap"]
TemplateRequirementStatus = Literal["existing", "missing", "ambiguous"]
SetRow = dict[str, int | float | str]


@dataclass(frozen=True)
class SplitCircuitTemplateRef:
    """Concrete template selected by the planner without workflow request coupling."""

    id: str
    name: str
    type: str
    equipment: str | None


@dataclass(frozen=True)
class SplitCircuitTemplateRequirement:
    """Template resolution evidence carried by a Split Circuit plan."""

    title: str
    expected_type: str
    equipment_category: str
    muscle_group: str
    other_muscles: tuple[str, ...]
    status: TemplateRequirementStatus
    matching_template_ids: tuple[str, ...]


@dataclass(frozen=True)
class SplitCircuitRest:
    """Rest metadata preserved from Coach-authored Circuit text."""

    source_text: str
    durations_seconds: list[int]


@dataclass(frozen=True)
class SplitCircuitGroupingIntent:
    """Circuit grouping intent before numeric Hevy superset allocation."""

    inherit_superset_context: bool
    numeric_superset_id: None = None


@dataclass(frozen=True)
class SplitCircuitExercisePlan:
    """One generated exercise in a Split Circuit plan."""

    name: str
    target: str
    source_text: str
    selected_template: SplitCircuitTemplateRef | None
    template_requirements: tuple[SplitCircuitTemplateRequirement, ...]
    set_rows: list[SetRow]
    notes_only: bool
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class SplitCircuitPlan:
    """Deterministic Split Circuit plan independent of Hevy request models."""

    kind: SplitCircuitKind
    round_count: int | None
    amrap_time_cap_seconds: int | None
    exercises: tuple[SplitCircuitExercisePlan, ...]
    rests: tuple[SplitCircuitRest, ...]
    metadata_lines: tuple[str, ...]
    grouping_intent: SplitCircuitGroupingIntent
    requires_agent_decision: bool
    agent_decision_reason: str | None
    original_source_text: str


@dataclass(frozen=True)
class SplitCircuitPrescription:
    """True Coach prescription text to attempt as a Split Circuit."""

    name: str
    text: str
    inherit_superset_context: bool = False


@dataclass(frozen=True)
class _BlockerContext:
    selected_template: SplitCircuitTemplateRef | None
    requirements: list[SplitCircuitTemplateRequirement]
    movement_name: str
    agent_decision_reason: str | None
    target: str
    set_rows: list[SetRow]


TemplateResolver = Callable[
    [str, str],
    tuple[SplitCircuitTemplateRef | None, list[SplitCircuitTemplateRequirement]],
]


def plan_prescription_split_circuit(
    *,
    prescription: SplitCircuitPrescription,
    resolve_template: TemplateResolver,
) -> SplitCircuitPlan | None:
    """Generate a prescription-side Split Circuit plan when the split is deterministic.

    Args:
        prescription (SplitCircuitPrescription): Coach-authored block text to split.
        resolve_template (TemplateResolver): Callback that resolves each generated
            exercise name to plain template evidence.

    Returns:
        SplitCircuitPlan | None: Split plan for deterministic multi-exercise blocks,
            otherwise ``None``.
    """
    parsed_block = parse_circuit_block(name=prescription.name, text=prescription.text)
    if parsed_block is None:
        return None

    return plan_parsed_split_circuit(
        parsed_block=parsed_block,
        prescription=prescription,
        resolve_template=resolve_template,
    )


def plan_parsed_split_circuit(
    *,
    parsed_block: ParsedCircuitBlock,
    prescription: SplitCircuitPrescription,
    resolve_template: TemplateResolver,
) -> SplitCircuitPlan:
    """Generate a Split Circuit plan from an already parsed block.

    Args:
        parsed_block (ParsedCircuitBlock): Structured Circuit or AMRAP parse result.
        prescription (SplitCircuitPrescription): Original prescription metadata.
        resolve_template (TemplateResolver): Callback that resolves each generated
            exercise name to plain template evidence.

    Returns:
        SplitCircuitPlan: Split plan for the parsed multi-exercise block.
    """
    exercises = tuple(
        _exercise_plan(
            parsed_block=parsed_block,
            movement=movement,
            resolve_template=resolve_template,
        )
        for movement in parsed_block.movements
    )
    return SplitCircuitPlan(
        kind=parsed_block.kind,
        round_count=parsed_block.round_count,
        amrap_time_cap_seconds=parsed_block.amrap_time_cap_seconds,
        exercises=exercises,
        rests=tuple(
            SplitCircuitRest(
                source_text=rest.source_text,
                durations_seconds=list(rest.durations_seconds),
            )
            for rest in parsed_block.rests
        ),
        metadata_lines=tuple(line.source_text for line in parsed_block.metadata_lines),
        grouping_intent=SplitCircuitGroupingIntent(
            inherit_superset_context=prescription.inherit_superset_context,
        ),
        requires_agent_decision=parsed_block.requires_agent_decision,
        agent_decision_reason=parsed_block.agent_decision_reason,
        original_source_text=prescription.text,
    )


def _exercise_plan(
    *,
    parsed_block: ParsedCircuitBlock,
    movement: ParsedCircuitMovement,
    resolve_template: TemplateResolver,
) -> SplitCircuitExercisePlan:
    movement_name = movement.name
    movement_target = movement.target
    movement_source_text = movement.source_text
    selected_template, requirements = resolve_template(movement_name, movement_source_text)
    set_rows = _set_rows_for_target(movement_target)
    notes_only = _is_notes_only(target=movement_target, set_rows=set_rows)
    return SplitCircuitExercisePlan(
        name=movement_name,
        target=movement_target,
        source_text=movement_source_text,
        selected_template=selected_template,
        template_requirements=tuple(requirements),
        set_rows=set_rows,
        notes_only=notes_only,
        warnings=_warnings(
            selected_template=selected_template,
            target=movement_target,
            set_rows=set_rows,
        ),
        blockers=_blockers(
            _BlockerContext(
                selected_template=selected_template,
                requirements=requirements,
                movement_name=movement_name,
                agent_decision_reason=(
                    parsed_block.agent_decision_reason
                    if parsed_block.requires_agent_decision
                    else None
                ),
                target=movement_target,
                set_rows=set_rows,
            ),
        ),
    )


def _is_notes_only(*, target: str, set_rows: list[SetRow]) -> bool:
    return bool(target.strip()) and not set_rows


def _warnings(
    *,
    selected_template: SplitCircuitTemplateRef | None,
    target: str,
    set_rows: list[SetRow],
) -> tuple[str, ...]:
    warnings: list[str] = []
    if selected_template is None:
        warnings.append("No linked Hevy exercise template found.")
    if target and not set_rows:
        warnings.append("No deterministic set parser result found.")
    return tuple(warnings)


def _blockers(context: _BlockerContext) -> tuple[str, ...]:
    blockers: list[str] = []
    if context.selected_template is None:
        blockers.append(f"Missing required Hevy exercise mapping: {context.movement_name}")
    blockers.extend(
        f"{requirement.status.title()} required Hevy template: {requirement.title}"
        for requirement in context.requirements
        if requirement.status in {"missing", "ambiguous"}
    )
    if context.agent_decision_reason is not None:
        blockers.append(
            "Circuit block requires Agent decision: "
            f"{context.agent_decision_reason or 'unspecified'}"
        )
    if (
        context.agent_decision_reason is None
        and not context.target.strip()
        and not context.set_rows
    ):
        blockers.append(
            "Generated Circuit exercise has no deterministic sets or target details: "
            f"{context.movement_name}"
        )
    return tuple(blockers)


def _set_rows_for_target(target: str) -> list[SetRow]:
    stripped = target.strip()
    if not stripped:
        return []
    if match := re.fullmatch(r"(?P<reps>\d+)(?:\s+(?:each side|es))?", stripped, re.IGNORECASE):
        return [{"type": "normal", "reps": int(match.group("reps"))}]
    if match := re.fullmatch(r"(?P<distance>\d+)\s*(?:m|meters?)", stripped, re.IGNORECASE):
        return [{"type": "normal", "distance_meters": int(match.group("distance"))}]
    if match := re.fullmatch(
        r"(?P<seconds>\d+)\s*(?:s|sec|secs|second|seconds)",
        stripped,
        re.IGNORECASE,
    ):
        return [{"type": "normal", "duration_seconds": int(match.group("seconds"))}]
    if match := re.fullmatch(
        r"(?P<minutes>\d+)\s*(?:min|mins|minute|minutes)(?:\s+\w+)?",
        stripped,
        re.IGNORECASE,
    ):
        return [{"type": "normal", "duration_seconds": int(match.group("minutes")) * 60}]
    return []
