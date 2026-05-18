"""Ensure required Hevy custom exercise templates from sync review plans."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from fitness_tracker.apis.hevy_app.types import (
    CreateCustomExercise,
    CreateCustomExerciseRequestBody,
    CreateCustomExerciseResponse,
    ExerciseTemplate,
)
from fitness_tracker.database import Store


class TemplateEnsureError(Exception):
    """Raised when required Hevy templates cannot be safely ensured."""


class HevyExerciseCreator(Protocol):
    """Subset of the Hevy exercise API needed by template ensure."""

    def create(
        self,
        exercise: CreateCustomExerciseRequestBody,
    ) -> CreateCustomExerciseResponse | None:
        """Create a custom Hevy exercise template.

        Args:
            exercise (CreateCustomExerciseRequestBody): Template creation request.

        Returns:
            CreateCustomExerciseResponse | None: Created template id when Hevy returns one.
        """


@dataclass(frozen=True)
class RequiredTemplate:
    """Required template entry parsed from a sync review plan."""

    title: str
    expected_type: str
    equipment_category: str
    muscle_group: str
    other_muscles: tuple[str, ...]
    status: str
    source_workout_item_ids: tuple[int, ...]
    matching_template_ids: tuple[str, ...]


@dataclass(frozen=True)
class TemplateEnsureResult:
    """Result of ensuring required templates."""

    created: tuple[RequiredTemplate, ...]
    would_create: tuple[RequiredTemplate, ...]
    existing: tuple[RequiredTemplate, ...]
    ambiguous: tuple[RequiredTemplate, ...]


@dataclass(frozen=True)
class RequiredTemplateGroups:
    """Required templates split by resolution status."""

    existing: tuple[RequiredTemplate, ...]
    ambiguous: tuple[RequiredTemplate, ...]
    missing: tuple[RequiredTemplate, ...]


class HevyTemplateEnsureService:
    """Create missing Hevy templates from a generated sync review plan."""

    def __init__(self, store: Store, hevy_exercises: HevyExerciseCreator | None = None) -> None:
        """Create the service.

        Args:
            store (Store): Local database cache.
            hevy_exercises (HevyExerciseCreator | None): Hevy exercise template API.
        """
        self._store = store
        self._hevy_exercises = hevy_exercises

    def ensure_from_plan(self, plan_path: Path, *, dry_run: bool) -> TemplateEnsureResult:
        """Ensure missing unambiguous templates listed by ``plan_path``.

        Args:
            plan_path (Path): Sync review ``plan.json`` path.
            dry_run (bool): When true, report only and write nothing.

        Returns:
            TemplateEnsureResult: Templates grouped by action.

        Raises:
            TemplateEnsureError: If the plan contains ambiguous templates or creation fails.
        """
        groups = _partition_required_templates(_required_templates_from_plan(plan_path))
        if groups.ambiguous:
            details = "; ".join(
                _format_ambiguous_template(template) for template in groups.ambiguous
            )
            msg = f"Ambiguous required Hevy template(s): {details}"
            raise TemplateEnsureError(msg)
        if dry_run:
            return TemplateEnsureResult(
                created=(),
                would_create=groups.missing,
                existing=groups.existing,
                ambiguous=groups.ambiguous,
            )
        hevy_exercises = self._require_hevy_exercises()

        created = []
        for template in groups.missing:
            created_id = self._create_remote_template(hevy_exercises, template)
            self._persist_created_template(template, created_id)
            created.append(template)
        return TemplateEnsureResult(
            created=tuple(created),
            would_create=(),
            existing=groups.existing,
            ambiguous=groups.ambiguous,
        )

    def _require_hevy_exercises(self) -> HevyExerciseCreator:
        hevy_exercises = self._hevy_exercises
        if hevy_exercises is None:
            msg = "Hevy exercise API is required when --yes is used"
            raise TemplateEnsureError(msg)
        return hevy_exercises

    def _create_remote_template(
        self, hevy_exercises: HevyExerciseCreator, template: RequiredTemplate
    ) -> str:
        payload = _create_request(template)
        response = hevy_exercises.create(payload)
        if response is None:
            msg = f"Hevy did not return an id for created template: {template.title}"
            raise TemplateEnsureError(msg)
        return str(response.id)

    def _persist_created_template(self, template: RequiredTemplate, template_id: str) -> None:
        exercise = ExerciseTemplate(
            id=template_id,
            title=template.title,
            type=cast(Any, template.expected_type),
            primary_muscle_group=cast(Any, template.muscle_group),
            secondary_muscle_groups=cast(Any, list(template.other_muscles)),
            equipment=cast(Any, template.equipment_category),
            is_custom=True,
        )
        with self._store.unit_of_work() as uow:
            uow.hevy.add_exercise(exercise)


def _required_templates_from_plan(plan_path: Path) -> tuple[RequiredTemplate, ...]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    raw_templates = [
        raw_template
        for item in plan.get("items", [])
        for raw_template in item.get("required_hevy_templates", [])
    ]
    by_key: dict[tuple[str, str], RequiredTemplate] = {}
    for raw_template in raw_templates:
        template = _required_template(raw_template)
        key = (template.title.casefold(), template.status)
        by_key[key] = template
    return tuple(by_key.values())


def _partition_required_templates(
    templates: tuple[RequiredTemplate, ...],
) -> RequiredTemplateGroups:
    existing: list[RequiredTemplate] = []
    ambiguous: list[RequiredTemplate] = []
    missing: list[RequiredTemplate] = []

    for template in templates:
        if template.status == "existing":
            existing.append(template)
        elif template.status == "ambiguous":
            ambiguous.append(template)
        elif template.status == "missing":
            missing.append(template)

    return RequiredTemplateGroups(
        existing=tuple(existing),
        ambiguous=tuple(ambiguous),
        missing=tuple(missing),
    )


def _required_template(raw_template: dict[str, Any]) -> RequiredTemplate:
    return RequiredTemplate(
        title=raw_template["title"],
        expected_type=raw_template["expected_type"],
        equipment_category=raw_template["equipment_category"],
        muscle_group=raw_template["muscle_group"],
        other_muscles=tuple(raw_template.get("other_muscles", [])),
        status=raw_template["status"],
        source_workout_item_ids=tuple(raw_template.get("source_workout_item_ids", [])),
        matching_template_ids=tuple(raw_template.get("matching_template_ids", [])),
    )


def _format_ambiguous_template(template: RequiredTemplate) -> str:
    matching_ids = ", ".join(template.matching_template_ids) or "unknown matches"
    return f"{template.title} ({matching_ids})"


def _create_request(template: RequiredTemplate) -> CreateCustomExerciseRequestBody:
    return CreateCustomExerciseRequestBody(
        exercise=CreateCustomExercise(
            title=template.title,
            exercise_type=cast(Any, template.expected_type),
            equipment_category=cast(Any, template.equipment_category),
            muscle_group=cast(Any, template.muscle_group),
            other_muscles=cast(Any, list(template.other_muscles)),
        )
    )
