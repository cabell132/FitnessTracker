"""Build read-only True Coach to Hevy sync review bundles."""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

from fitness_tracker.apis.hevy_app.types import PostRoutinesRequestSet
from fitness_tracker.database import Store
from fitness_tracker.database.models import HevyAppExercise, TrueCoachExercise
from fitness_tracker.database.models.hevy_app import HevyAppSets, HevyAppWorkout, HevyAppWorkoutItem
from fitness_tracker.database.models.true_coach import TrueCoachWorkout, TrueCoachWorkoutItem
from fitness_tracker.database.uow import UnitOfWork
from fitness_tracker.sync._true_coach_html import parse_prescribed_sets

SET_DISPLAY_KEYS = ("type", "weight_kg", "reps", "distance_meters", "duration_seconds")
BLOCKING_REQUIRED_TEMPLATE_STATUSES = frozenset({"missing", "ambiguous"})
RequiredTemplateStatus = Literal["existing", "missing", "ambiguous"]
WeightProvenance = Literal["athlete_history", "calculated_dropset"]
type SetSignature = tuple[str, str, int]
type SetProvenance = dict[str, WeightProvenance]


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
    set_provenance: list[SetProvenance]
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
class RequiredHevyTemplate:
    """Required Hevy exercise template and local catalog resolution status."""

    spec: RequiredTemplateSpec
    status: RequiredTemplateStatus
    source_workout_item_ids: tuple[int, ...]
    matching_template_ids: tuple[str, ...]


@dataclass(frozen=True)
class HistoricalLoad:
    """A usable Athlete-history load for one planned Routine set."""

    weight_kg: float


DEFAULT_TEMPLATE_OVERRIDE_RULES_PATH = Path(__file__).with_name("template_override_rules.json")


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
        proposed_sets = parse_prescribed_sets(item.info or "")
        proposed_sets, set_provenance = _enrich_sets_from_history(uow, template, proposed_sets)
        warnings = []
        if template is None:
            warnings.append("No linked Hevy exercise template found.")
        if _has_missing_history_load(template, proposed_sets):
            warnings.append("No matching Athlete history load found.")
        return ReviewItem(
            source_id=item.id,
            name=item.name,
            info=item.info or "",
            selected_hevy_template=template,
            required_hevy_templates=required_templates,
            proposed_sets=proposed_sets,
            set_provenance=set_provenance,
            warnings=warnings,
            blockers=_required_template_blockers(required_templates),
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
            "proposed_sets": [
                _set_to_dict(proposed_set) | _provenance_to_dict(provenance)
                for proposed_set, provenance in zip(
                    item.proposed_sets, item.set_provenance, strict=True
                )
            ],
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
    source_names = {name.casefold() for name in rule.source_template_names}
    candidate_names = {item.name.casefold()}
    if selected_template is not None:
        candidate_names.add(selected_template.name.casefold())
    if candidate_names.isdisjoint(source_names):
        return False
    item_text = f"{item.name} {item.info or ''} {item.comment or ''}"
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


def _enrich_sets_from_history(
    uow: UnitOfWork,
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
        and (planned_set.reps is not None or planned_set.duration_seconds is not None)
        for planned_set in planned_sets
    )


def _historical_loads_by_signature(
    uow: UnitOfWork,
    exercise_template_id: str,
) -> dict[SetSignature, deque[HistoricalLoad]]:
    rows = (
        uow.query(HevyAppSets)
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


def _set_to_dict(value: PostRoutinesRequestSet) -> dict[str, int | float | str]:
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    return value.dict(exclude_none=True)


def _provenance_to_dict(provenance: SetProvenance) -> dict[str, SetProvenance]:
    return {"_provenance": provenance} if provenance else {}


def _format_set(value: PostRoutinesRequestSet) -> str:
    data = _set_to_dict(value)
    return "; ".join(f"{key}: {data[key]}" for key in SET_DISPLAY_KEYS if key in data)
