"""Build read-only True Coach to Hevy sync review bundles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

from fitness_tracker.apis.hevy_app.types import PostRoutinesRequestSet
from fitness_tracker.database import Store
from fitness_tracker.database.models import HevyAppExercise, TrueCoachExercise
from fitness_tracker.database.models.true_coach import TrueCoachWorkout, TrueCoachWorkoutItem
from fitness_tracker.database.uow import UnitOfWork
from fitness_tracker.sync._true_coach_html import parse_prescribed_sets

SET_DISPLAY_KEYS = ("type", "weight_kg", "reps", "distance_meters", "duration_seconds")
BLOCKING_REQUIRED_TEMPLATE_STATUSES = frozenset({"missing", "ambiguous"})
RequiredTemplateStatus = Literal["existing", "missing", "ambiguous"]
PhaseKind = Literal["isometric_hold", "dynamic_reps"]


class SyncReviewError(Exception):
    """Raised when a requested sync review cannot be produced."""


@dataclass(frozen=True)
class ReviewBundle:
    """Paths written for a sync review."""

    directory: Path
    report_path: Path
    plan_path: Path


@dataclass(frozen=True)
class ReviewItem:
    """One True Coach workout item review row."""

    source_id: int
    name: str
    info: str
    selected_hevy_template: HevyAppExercise | None
    required_hevy_templates: list[RequiredHevyTemplate]
    proposed_sets: list[PostRoutinesRequestSet]
    planned_blocks: list[PlannedBlock]
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
    """One Hevy Routine exercise block planned from a True Coach Workout Item phase."""

    source_id: int
    phase_index: int
    phase_kind: PhaseKind
    source_text: str
    notes: str
    selected_hevy_template: HevyAppExercise | None
    required_hevy_templates: list[RequiredHevyTemplate]
    proposed_sets: list[PostRoutinesRequestSet]


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


DEFAULT_TEMPLATE_OVERRIDE_RULES_PATH = Path(__file__).with_name("template_override_rules.json")
MIXED_PHASE_SPLIT_PATTERN = re.compile(r"\s+(?:then|followed by)\s+|[;,]\s*", re.IGNORECASE)
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
            workout = uow.tc_get_workout(id=workout_id)
            if workout is None:
                msg = f"True Coach workout {workout_id} was not found in the local DB"
                raise SyncReviewError(msg)

            items = [
                self._review_item(uow, item)
                for item in sorted(
                    workout.workout_items,
                    key=lambda item: (item.position is None, item.position or 0, item.id),
                )
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

    def _review_item(self, uow: UnitOfWork, item: TrueCoachWorkoutItem) -> ReviewItem:
        template = self._selected_template(uow, item)
        required_templates = self._required_templates(uow, item, template)
        planned_blocks = self._planned_blocks(uow, item, template)
        warnings = []
        if template is None:
            warnings.append("No linked Hevy exercise template found.")
        return ReviewItem(
            source_id=item.id,
            name=item.name,
            info=item.info or "",
            selected_hevy_template=template,
            required_hevy_templates=required_templates,
            proposed_sets=parse_prescribed_sets(item.info or ""),
            planned_blocks=planned_blocks,
            warnings=warnings,
            blockers=_required_template_blockers(
                _required_templates_for_blockers(required_templates, planned_blocks)
            ),
        )

    def _selected_template(
        self,
        uow: UnitOfWork,
        item: TrueCoachWorkoutItem,
    ) -> HevyAppExercise | None:
        exercise = item.exercise
        if isinstance(exercise, TrueCoachExercise) and isinstance(
            exercise.hevy_app, HevyAppExercise
        ):
            return exercise.hevy_app
        if item.tracker and isinstance(item.tracker.exercise.hevy_app, HevyAppExercise):
            return item.tracker.exercise.hevy_app
        tracker_exercise = uow.tracker_get_exercise(name=item.name)
        if tracker_exercise and isinstance(tracker_exercise.hevy_app, HevyAppExercise):
            return tracker_exercise.hevy_app
        return None

    def _required_templates(
        self,
        uow: UnitOfWork,
        item: TrueCoachWorkoutItem,
        selected_template: HevyAppExercise | None,
    ) -> list[RequiredHevyTemplate]:
        rules = _load_template_override_rules(DEFAULT_TEMPLATE_OVERRIDE_RULES_PATH)
        matched_specs = [
            rule.required_template for rule in rules if _rule_matches(rule, item, selected_template)
        ]
        return [
            _resolve_required_template(uow, spec, source_workout_item_id=item.id)
            for spec in matched_specs
        ]

    def _planned_blocks(
        self,
        uow: UnitOfWork,
        item: TrueCoachWorkoutItem,
        selected_template: HevyAppExercise | None,
    ) -> list[PlannedBlock]:
        phases = _parse_mixed_mode_phases(item.info or "")
        if not phases:
            return []

        blocks: list[PlannedBlock] = []
        for index, phase in enumerate(phases, start=1):
            required_templates = (
                self._required_templates_for_phase(
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
            blocks.append(
                PlannedBlock(
                    source_id=item.id,
                    phase_index=index,
                    phase_kind=phase.kind,
                    source_text=phase.source_text,
                    notes=f"{phase.source_text}\nSource: {item.info or ''}",
                    selected_hevy_template=phase_template,
                    required_hevy_templates=required_templates,
                    proposed_sets=phase.proposed_sets,
                )
            )
        return blocks

    def _required_templates_for_phase(
        self,
        uow: UnitOfWork,
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
            "name": item.name,
            "info": item.info,
            "selected_hevy_template": _template_to_dict(template),
            "required_hevy_templates": [
                _required_template_to_dict(required_template)
                for required_template in item.required_hevy_templates
            ],
            "proposed_sets": [_set_to_dict(proposed_set) for proposed_set in item.proposed_sets],
            "planned_blocks": [_planned_block_to_dict(block) for block in item.planned_blocks],
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


def _rule_matches(
    rule: TemplateOverrideRule,
    item: TrueCoachWorkoutItem,
    selected_template: HevyAppExercise | None,
) -> bool:
    return _rule_matches_text(
        rule,
        TemplateMatchContext(
            item=item,
            selected_template=selected_template,
            text=item.info or item.comment or "",
        ),
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
    uow: UnitOfWork,
    spec: RequiredTemplateSpec,
    *,
    source_workout_item_id: int,
) -> RequiredHevyTemplate:
    matching_templates = [
        template
        for template in uow.get_all(HevyAppExercise)
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


def _parse_mixed_mode_phases(description: str) -> list[ParsedPhase]:
    parts = [
        part.strip()
        for part in MIXED_PHASE_SPLIT_PATTERN.split(description)
        if part and part.strip()
    ]
    if len(parts) < 2:
        return []

    phases = [_parse_phase(part) for part in parts]
    if any(phase is None for phase in phases):
        return []

    parsed = [phase for phase in phases if phase is not None]
    kinds = {phase.kind for phase in parsed}
    if kinds != {"isometric_hold", "dynamic_reps"}:
        return []
    return parsed


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
    uow: UnitOfWork,
    selection: PhaseTemplateSelection,
) -> HevyAppExercise | None:
    if selection.phase_kind == "dynamic_reps":
        return selection.selected_template
    if len(selection.required_templates) != 1:
        return None
    required_template = selection.required_templates[0]
    if required_template.status != "existing" or len(required_template.matching_template_ids) != 1:
        return None
    return uow.get(HevyAppExercise, id=required_template.matching_template_ids[0])


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
        "phase_index": block.phase_index,
        "phase_kind": block.phase_kind,
        "source_text": block.source_text,
        "notes": block.notes,
        "selected_hevy_template": _template_to_dict(block.selected_hevy_template),
        "required_hevy_templates": [
            _required_template_to_dict(required_template)
            for required_template in block.required_hevy_templates
        ],
        "proposed_sets": [_set_to_dict(proposed_set) for proposed_set in block.proposed_sets],
    }


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
        f"- Block {block.phase_index}: {_format_phase_kind(block.phase_kind)}",
        f"  Source ID: {block.source_id}",
        f"  Source text: {block.source_text}",
        f"  Notes: {block.notes}",
        f"  {_format_template(block.selected_hevy_template)}",
        "  Proposed sets:",
    ]
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
    return lines


def _format_phase_kind(phase_kind: PhaseKind) -> str:
    if phase_kind == "isometric_hold":
        return "Isometric hold"
    return "Dynamic reps"


def _set_to_dict(value: PostRoutinesRequestSet) -> dict[str, int | float | str]:
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    return value.dict(exclude_none=True)


def _format_set(value: PostRoutinesRequestSet) -> str:
    data = _set_to_dict(value)
    return "; ".join(f"{key}: {data[key]}" for key in SET_DISPLAY_KEYS if key in data)
