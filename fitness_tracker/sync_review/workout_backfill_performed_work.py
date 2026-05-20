"""Plan performed True Coach Workout Items for Workout backfill review."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fitness_tracker.apis.hevy_app.types.workout_requests import PostWorkoutsRequestSet
from fitness_tracker.database.models.hevy_app import HevyAppExercise
from fitness_tracker.database.models.tracker import Sets
from fitness_tracker.sync._circuit_block_parser import ParsedCircuitBlock, parse_circuit_block
from fitness_tracker.sync_review.split_circuit.core import (
    AGENT_DECISION_BLOCKER_PREFIX,
    SetRow,
    SplitCircuitExerciseNoteContext,
    SplitCircuitExercisePlan,
    SplitCircuitPlan,
    SplitCircuitPrescription,
    SplitCircuitTemplateRef,
    SplitCircuitTemplateRequirement,
    plan_parsed_split_circuit,
    render_split_circuit_exercise_notes,
)

_REPLACEMENT_MOVEMENT_PATTERNS = (
    r"(?:w/o|without|no)\s+(?P<omitted>.+?)\s+"
    r"(?:replaced\s+with|instead\s+of|subbed\s+with|swapped\s+for)\s+"
    r"(?P<replacement>.+)",
    r"(?:w/o|without|no)\s+(?P<omitted>.+?),?\s+(?P<replacement>.+?)\s+instead",
)
_OMITTED_MOVEMENT_PATTERN = re.compile(
    r"(?P<source>(?:w/o|without|no)\s+(?P<name>.+))$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class BackfillReviewItem:
    """One performed item planned for a Hevy Workout draft."""

    source_id: int | None
    tracker_workout_item_id: int
    position: int
    superset_id: int | None
    name: str
    info: str
    comment: str
    selected_hevy_template: HevyAppExercise | None
    sets: list[PostWorkoutsRequestSet]
    notes: str
    warnings: list[str]
    blockers: list[str]
    movement_target: str | None = None
    original_prescription_text: str | None = None
    completed_round_count: int | None = None
    choice_template_candidate_ids: list[str] | None = None
    choice_decision_reason: str | None = None
    circuit_template_candidate_ids: list[str] | None = None
    circuit_decision_reason: str | None = None
    replacement_for_movement_name: str | None = None
    replacement_source_comment: str | None = None


@dataclass(frozen=True)
class ChoicePerformance:
    """One performed modality parsed from a Choice Workout Item comment."""

    name: str
    sets: list[PostWorkoutsRequestSet]
    notes: str


@dataclass(frozen=True)
class DurationPerformance:
    """One duration parsed from a performed item comment."""

    sets: list[PostWorkoutsRequestSet]
    notes: str


@dataclass(frozen=True)
class CircuitReviewContext:
    """Source context for expanding one Circuit or AMRAP Workout Item."""

    item: Any
    source_id: int
    position: int
    superset_id: int | None
    info: str
    comment: str
    templates: list[HevyAppExercise]
    parsed_block: ParsedCircuitBlock


@dataclass(frozen=True)
class ChoiceReviewContext:
    """Source context for expanding one Choice Workout Item."""

    item: Any
    source_id: int | None
    position: int
    superset_id: int | None
    info: str
    comment: str
    templates: list[HevyAppExercise]


@dataclass(frozen=True)
class ReplacementMovement:
    """A named performed replacement from an Athlete backfill comment."""

    omitted_name: str
    name: str
    source_text: str


def plan_performed_work_items(
    tracker_items: list[Any],
    templates: list[HevyAppExercise],
    superset_ids_by_position: dict[int, int],
) -> list[BackfillReviewItem]:
    """Plan performed Workout Items without rendering review artifacts.

    Args:
        tracker_items (list[Any]): Ordered tracker Workout Item rows to plan.
        templates (list[HevyAppExercise]): Available Hevy exercise templates.
        superset_ids_by_position (dict[int, int]): Existing superset IDs keyed by
            tracker item position.

    Returns:
        list[BackfillReviewItem]: Planned performed items for the backfill review.
    """
    items: list[BackfillReviewItem] = []
    expanded_circuit_source_ids = _source_ids_with_unexpanded_circuit_items(tracker_items)
    for item in tracker_items:
        if _is_persisted_synthetic_circuit_tracker_item(item, expanded_circuit_source_ids):
            continue
        items.extend(_review_item(item, templates, superset_ids_by_position))
    return items


def _source_ids_with_unexpanded_circuit_items(tracker_items: list[Any]) -> set[int]:
    return {
        item.true_coach_id
        for item in tracker_items
        if item.true_coach_id is not None
        and item.true_coach is not None
        and bool(item.true_coach.is_circuit)
        and item.exercise is not None
        and item.exercise.hevy_app is None
    }


def _is_persisted_synthetic_circuit_tracker_item(
    item: Any,
    expanded_circuit_source_ids: set[int],
) -> bool:
    true_coach_item = item.true_coach
    if true_coach_item is None or not bool(true_coach_item.is_circuit):
        return False
    if item.exercise is None or item.exercise.hevy_app is None:
        return False
    return item.true_coach_id in expanded_circuit_source_ids


def _review_item(  # noqa: C901, PLR0915
    item: Any,
    templates: list[HevyAppExercise],
    superset_ids_by_position: dict[int, int],
) -> list[BackfillReviewItem]:
    true_coach_item = item.true_coach
    template = item.exercise.hevy_app if item.exercise is not None else None
    sets = [
        _set_to_request_set(set_row) for set_row in sorted(item.sets, key=lambda row: row.index)
    ]
    info = true_coach_item.info or "" if true_coach_item is not None else ""
    comment = true_coach_item.comment or "" if true_coach_item is not None else ""
    name = true_coach_item.name if true_coach_item is not None else item.exercise.name
    if true_coach_item is not None and bool(true_coach_item.is_circuit):
        parsed_block = parse_circuit_block(name=name, text=info)
        if parsed_block is not None:
            if true_coach_item.state == "missed":
                return []
            return _circuit_review_items(
                CircuitReviewContext(
                    item=item,
                    source_id=true_coach_item.id,
                    position=item.position,
                    superset_id=superset_ids_by_position.get(item.position),
                    info=info,
                    comment=comment,
                    templates=templates,
                    parsed_block=parsed_block,
                )
            )
    choice_items = _choice_review_items(
        ChoiceReviewContext(
            item=item,
            source_id=true_coach_item.id if true_coach_item is not None else None,
            position=item.position,
            superset_id=superset_ids_by_position.get(item.position),
            info=info,
            comment=comment,
            templates=templates,
        )
    )
    if choice_items:
        return choice_items
    notes: str | None = None
    if not sets and _is_down_regulate_item(name):
        sets = [PostWorkoutsRequestSet(type="normal", duration_seconds=240)]
    if not sets and isinstance(template, HevyAppExercise):
        duration_performance = _duration_performance(comment, template)
        if duration_performance is not None:
            sets = duration_performance.sets
            notes = duration_performance.notes
    blockers: list[str] = []
    warnings: list[str] = []
    is_placeholder_rest = not sets and _is_placeholder_rest_item(
        name=name,
        info=info,
        comment=comment,
    )
    if template is None and not is_placeholder_rest:
        blockers.append(f"Missing Hevy template mapping for performed item: {item.exercise.name}")
    if not sets:
        if is_placeholder_rest:
            warnings.append(
                "Placeholder rest item has no structured Sets rows; omitted from draft request."
            )
        else:
            warnings.append("No structured tracker Sets rows found; omitted from draft request.")
    return [
        BackfillReviewItem(
            source_id=true_coach_item.id if true_coach_item is not None else None,
            tracker_workout_item_id=item.id,
            position=item.position,
            superset_id=superset_ids_by_position.get(item.position),
            name=name,
            info=info,
            comment=comment,
            selected_hevy_template=template if isinstance(template, HevyAppExercise) else None,
            sets=sets,
            notes=notes if notes is not None else _notes(info=info, comment=comment, sets=sets),
            warnings=warnings,
            blockers=blockers,
        )
    ]


def _circuit_review_items(context: CircuitReviewContext) -> list[BackfillReviewItem]:  # noqa: PLR0915
    split_plan = _split_circuit_plan(context)
    completed_round_count = _completed_round_count(context.comment, context.parsed_block)
    round_time_lines = _round_time_lines(context.comment)
    omitted_movements = _omitted_movement_names(context.comment)
    replacement_movements = _replacement_movements_from_comment(context.comment)
    review_items: list[BackfillReviewItem] = []
    for offset, exercise in enumerate(split_plan.exercises):
        replacement = _matching_replacement(exercise.name, replacement_movements)
        review_name = exercise.name
        template = _hevy_template_for_split_exercise(context.templates, exercise)
        replacement_for_movement_name: str | None = None
        replacement_source_comment: str | None = None
        if replacement is not None:
            review_name = replacement.name
            template = None
            replacement_for_movement_name = exercise.name
            replacement_source_comment = replacement.source_text
        matches = _matching_choice_templates(review_name, context.templates)
        omission_comment = _matching_omission_comment(exercise.name, omitted_movements)
        base_sets = [_workout_set_from_split_row(set_row) for set_row in exercise.set_rows]
        sets = _repeat_sets(base_sets, count=completed_round_count or 1)
        if omission_comment is not None and replacement is None:
            sets = []
        warnings: list[str] = []
        blockers: list[str] = []
        circuit_decision_reason: str | None = None
        if replacement is not None:
            blockers.append(
                f"Circuit Workout Item {context.source_id} {exercise.name} "
                f"replacement requires Agent decision: {replacement.name}"
            )
            circuit_decision_reason = "replacement_exercise"
        elif omission_comment is not None:
            warnings.append(f"Athlete comment omits Circuit movement: {omission_comment}")
        elif not matches:
            blockers.append(
                f"Missing Hevy template mapping for Circuit Workout Item "
                f"{context.source_id}: {exercise.name}"
            )
            circuit_decision_reason = "missing_template"
        elif len(matches) > 1:
            ids = ", ".join(template.id for template in matches)
            blockers.append(
                f"Ambiguous Hevy template mapping for Circuit Workout Item "
                f"{context.source_id}: {exercise.name} ({ids})"
            )
            circuit_decision_reason = "ambiguous_template"
        blockers.extend(_agent_decision_blockers(exercise))
        if exercise.target and not base_sets and omission_comment is None:
            warnings.append("No deterministic set parser for Circuit movement target.")
        review_items.append(
            BackfillReviewItem(
                source_id=context.source_id,
                tracker_workout_item_id=context.item.id,
                position=context.position + offset,
                superset_id=context.superset_id,
                name=review_name,
                info=context.info,
                comment=context.comment,
                selected_hevy_template=template,
                sets=sets,
                notes=render_split_circuit_exercise_notes(
                    SplitCircuitExerciseNoteContext(
                        exercise=exercise,
                        plan=split_plan,
                        original_source_text=context.info,
                        round_count_label="Prescribed rounds",
                        extra_lines=_circuit_note_extra_lines(
                            round_time_lines=round_time_lines,
                            comment=context.comment,
                        ),
                    )
                ),
                warnings=warnings,
                blockers=blockers,
                movement_target=exercise.target,
                original_prescription_text=exercise.source_text,
                completed_round_count=completed_round_count,
                circuit_template_candidate_ids=[template.id for template in matches],
                circuit_decision_reason=circuit_decision_reason,
                replacement_for_movement_name=replacement_for_movement_name,
                replacement_source_comment=replacement_source_comment,
            )
        )
    return review_items


def _split_circuit_plan(context: CircuitReviewContext) -> SplitCircuitPlan:
    def resolve_template(
        movement_name: str,
        _source_text: str,
    ) -> tuple[SplitCircuitTemplateRef | None, list[SplitCircuitTemplateRequirement]]:
        matches = _matching_choice_templates(movement_name, context.templates)
        template = matches[0] if len(matches) == 1 else None
        return _split_template_ref(template), []

    return plan_parsed_split_circuit(
        parsed_block=context.parsed_block,
        prescription=SplitCircuitPrescription(
            name=context.item.true_coach.name or "",
            text=context.info,
            inherit_superset_context=context.superset_id is not None,
        ),
        resolve_template=resolve_template,
    )


def _split_template_ref(template: HevyAppExercise | None) -> SplitCircuitTemplateRef | None:
    if template is None:
        return None
    return SplitCircuitTemplateRef(
        id=template.id,
        name=template.name,
        type=template.type,
        equipment=template.equipment,
    )


def _hevy_template_for_split_exercise(
    templates: list[HevyAppExercise],
    exercise: SplitCircuitExercisePlan,
) -> HevyAppExercise | None:
    if exercise.selected_template is None:
        return None
    for template in templates:
        if template.id == exercise.selected_template.id:
            return template
    return None


def _agent_decision_blockers(exercise: SplitCircuitExercisePlan) -> list[str]:
    return [
        blocker
        for blocker in exercise.blockers
        if blocker.startswith(AGENT_DECISION_BLOCKER_PREFIX)
    ]


def _completed_round_count(comment: str, parsed_block: ParsedCircuitBlock) -> int | None:
    explicit_rounds = _explicit_round_count(comment)
    if explicit_rounds is not None:
        return explicit_rounds
    round_times = _round_time_lines(comment)
    if round_times:
        return len(round_times)
    return parsed_block.round_count


def _explicit_round_count(comment: str) -> int | None:
    for segment in _comment_segments(comment):
        match = re.fullmatch(r"(?P<count>\d+)\s*rounds?", segment, flags=re.IGNORECASE)
        if match is not None:
            return int(match.group("count"))
    return None


def _round_time_lines(comment: str) -> list[str]:
    return [
        segment
        for segment in _comment_segments(comment)
        if _round_time_seconds(segment) is not None
    ]


def _round_time_seconds(segment: str) -> int | None:
    matches = list(
        re.finditer(
            r"(?P<value>\d+)\s*(?P<unit>min|mins|minute|minutes|s|sec|secs|second|seconds)\b",
            segment,
            flags=re.IGNORECASE,
        )
    )
    if not matches:
        return None
    normalized = re.sub(
        r"\d+\s*(?:min|mins|minute|minutes|s|sec|secs|second|seconds)\b",
        "",
        segment,
        flags=re.IGNORECASE,
    ).strip(" ,-/")
    if normalized:
        return None
    total = 0
    for match in matches:
        value = int(match.group("value"))
        unit = match.group("unit").lower()
        total += value * 60 if unit.startswith("min") else value
    return total


def _omitted_movement_names(comment: str) -> dict[str, str]:
    omitted: dict[str, str] = {}
    for segment in _comment_segments(comment):
        match = _OMITTED_MOVEMENT_PATTERN.search(segment)
        if match is None:
            continue
        name = match.group("name").strip()
        omitted[_normalize_choice_text(name)] = match.group("source").strip()
    return omitted


def _replacement_movements_from_comment(comment: str) -> list[ReplacementMovement]:
    replacements: list[ReplacementMovement] = []
    for segment in _replacement_comment_segments(comment):
        replacement = _replacement_movement_from_segment(segment)
        if replacement is not None:
            replacements.append(replacement)
    return replacements


def _replacement_comment_segments(comment: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"\n|;", comment) if segment.strip()]


def _replacement_movement_from_segment(segment: str) -> ReplacementMovement | None:
    for pattern in _REPLACEMENT_MOVEMENT_PATTERNS:
        match = re.fullmatch(pattern, segment.strip(), flags=re.IGNORECASE)
        if match is None:
            continue
        omitted_name = _clean_replacement_name(match.group("omitted"))
        replacement_name = _clean_replacement_name(match.group("replacement"))
        if omitted_name and replacement_name:
            return ReplacementMovement(
                omitted_name=omitted_name,
                name=replacement_name,
                source_text=segment,
            )
    return None


def _clean_replacement_name(value: str) -> str:
    return re.sub(r"^(?:a|an|the)\s+", "", value.strip(" .,-/"), flags=re.IGNORECASE)


def _matching_replacement(
    movement_name: str,
    replacement_movements: list[ReplacementMovement],
) -> ReplacementMovement | None:
    normalized_name = _normalize_choice_text(movement_name)
    for replacement in replacement_movements:
        omitted_name = _normalize_choice_text(replacement.omitted_name)
        if (
            omitted_name == normalized_name
            or omitted_name in normalized_name
            or normalized_name in omitted_name
        ):
            return replacement
    return None


def _matching_omission_comment(
    movement_name: str,
    omitted_movements: dict[str, str],
) -> str | None:
    normalized_name = _normalize_choice_text(movement_name)
    for omitted_name, source_text in omitted_movements.items():
        if (
            omitted_name == normalized_name
            or omitted_name in normalized_name
            or normalized_name in omitted_name
        ):
            return source_text
    return None


def _workout_set_from_split_row(row: SetRow) -> PostWorkoutsRequestSet:
    return PostWorkoutsRequestSet(
        type=row.get("type", "normal"),
        weight_kg=row.get("weight_kg"),
        reps=row.get("reps"),
        distance_meters=row.get("distance_meters"),
        duration_seconds=row.get("duration_seconds"),
    )


def _repeat_sets(
    sets: list[PostWorkoutsRequestSet],
    *,
    count: int,
) -> list[PostWorkoutsRequestSet]:
    return [set_row for _ in range(count) for set_row in sets]


def _circuit_note_extra_lines(
    *,
    round_time_lines: list[str],
    comment: str,
) -> tuple[str, ...]:
    lines: list[str] = []
    if round_time_lines:
        lines.append(f"Completed round times: {'; '.join(round_time_lines)}")
    if comment:
        lines.append(f"Athlete comment: {comment}")
    return tuple(lines)


def _choice_review_items(context: ChoiceReviewContext) -> list[BackfillReviewItem]:
    options = _choice_options(context.info)
    performances = _choice_performances(context.comment, options)
    if not options or not performances:
        return []
    review_items = []
    for offset, performance in enumerate(performances):
        matches = _matching_choice_templates(performance.name, context.templates)
        blockers = []
        if not matches:
            blockers.append(
                "Missing Hevy template mapping for Choice Workout Item "
                f"{context.source_id}: {performance.name}"
            )
            choice_decision_reason = "missing_template"
        elif len(matches) > 1:
            ids = ", ".join(template.id for template in matches)
            blockers.append(
                f"Ambiguous Hevy template mapping for Choice Workout Item {context.source_id}: "
                f"{performance.name} ({ids})"
            )
            choice_decision_reason = "ambiguous_template"
        else:
            choice_decision_reason = None
        review_items.append(
            BackfillReviewItem(
                source_id=context.source_id,
                tracker_workout_item_id=context.item.id,
                position=context.position + offset,
                superset_id=context.superset_id,
                name=performance.name,
                info=context.info,
                comment=context.comment,
                selected_hevy_template=matches[0] if len(matches) == 1 else None,
                sets=performance.sets,
                notes=performance.notes,
                warnings=[],
                blockers=blockers,
                choice_template_candidate_ids=[template.id for template in matches],
                choice_decision_reason=choice_decision_reason,
            )
        )
    return review_items


def _choice_options(info: str) -> list[str]:
    if not _looks_like_choice_text(info):
        return []
    normalized = re.sub(r"\bor a combination\b", "", info, flags=re.IGNORECASE)
    normalized = re.sub(r"\bcombination\b", "", normalized, flags=re.IGNORECASE)
    parts = re.split(r",|/|\bor\b", normalized, flags=re.IGNORECASE)
    return [part.strip(" .") for part in parts if part.strip(" .")]


def _looks_like_choice_text(info: str) -> bool:
    return bool(re.search(r",|/|\bor\b|\bcombination\b", info, flags=re.IGNORECASE))


def _choice_performances(comment: str, options: list[str]) -> list[ChoicePerformance]:
    performances = []
    for segment in _comment_segments(comment):
        option = _matching_choice_option(segment, options)
        duration_seconds = _duration_seconds(segment)
        if option is None or duration_seconds is None:
            continue
        notes = _choice_segment_notes(comment, segment)
        performances.append(
            ChoicePerformance(
                name=option,
                sets=[PostWorkoutsRequestSet(type="normal", duration_seconds=duration_seconds)],
                notes=notes,
            )
        )
    return performances


def _duration_performance(
    comment: str,
    template: HevyAppExercise,
) -> DurationPerformance | None:
    if template.type not in {"duration", "distance_duration"}:
        return None
    for segment in _comment_segments(comment):
        duration_seconds = _duration_seconds(segment)
        if duration_seconds is None:
            continue
        return DurationPerformance(
            sets=[PostWorkoutsRequestSet(type="normal", duration_seconds=duration_seconds)],
            notes=_duration_performance_notes(comment, segment),
        )
    return None


def _duration_performance_notes(comment: str, duration_segment: str) -> str:
    note_segments = []
    for segment in _comment_segments(comment):
        note_segment = segment
        if segment == duration_segment:
            note_segment = re.sub(
                r"\b\d+(?:\.\d+)?\s*(?:mins?|minutes?)\b",
                "",
                segment,
                count=1,
                flags=re.IGNORECASE,
            ).strip(" /,-")
        if note_segment:
            note_segments.append(note_segment)
    return f"Athlete comment: {'; '.join(note_segments)}" if note_segments else ""


def _comment_segments(comment: str) -> list[str]:
    return [segment.strip() for segment in re.split(r",|\n|;", comment) if segment.strip()]


def _matching_choice_option(segment: str, options: list[str]) -> str | None:
    normalized_segment = _normalize_choice_text(segment)
    for option in options:
        if _normalize_choice_text(option) in normalized_segment:
            return option
    return None


def _normalize_choice_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _duration_seconds(segment: str) -> int | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:mins?|minutes?)\b", segment, flags=re.IGNORECASE)
    if match is None:
        return None
    return round(float(match.group(1)) * 60)


def _choice_segment_notes(comment: str, performed_segment: str) -> str:
    note_segments = [
        segment
        for segment in _comment_segments(comment)
        if segment.strip() != performed_segment.strip()
    ]
    if not note_segments:
        return ""
    return f"Athlete comment: {', '.join(note_segments)}"


def _matching_choice_templates(
    performance_name: str,
    templates: list[HevyAppExercise],
) -> list[HevyAppExercise]:
    normalized_name = _normalize_choice_text(performance_name)
    return [
        template
        for template in templates
        if _normalize_choice_text(template.name) == normalized_name
    ]


def _is_down_regulate_item(name: str) -> bool:
    return name.casefold().strip() == "down regulate"


def _is_placeholder_rest_item(*, name: str, info: str, comment: str) -> bool:
    if comment.strip():
        return False
    normalized_name = name.casefold().strip()
    normalized_info = info.casefold().strip()
    return normalized_name == "rest" or normalized_info in {"rest", "placeholder"}


def _set_to_request_set(set_row: Sets) -> PostWorkoutsRequestSet:
    return PostWorkoutsRequestSet(
        type=set_row.type,
        weight_kg=set_row.weight_kg,
        reps=set_row.reps,
        distance_meters=set_row.distance_meters,
        duration_seconds=set_row.duration_seconds,
        rpe=set_row.rpe,
    )


def _notes(*, info: str, comment: str, sets: list[PostWorkoutsRequestSet]) -> str:
    parts = []
    if info and not sets:
        parts.append(f"Coach prescription: {info}")
    duration_note = _duration_note_for_structured_set(comment, sets)
    if duration_note is not None:
        if duration_note:
            parts.append(duration_note)
        return "\n".join(parts)
    if info and any(set_row.distance_meters is not None for set_row in sets):
        parts.append(f"Coach prescription: {info}")
    if comment and not _comment_duplicates_structured_sets(comment, sets):
        parts.append(f"Athlete comment: {comment}")
    return "\n".join(parts)


def _duration_note_for_structured_set(
    comment: str,
    sets: list[PostWorkoutsRequestSet],
) -> str | None:
    if len(sets) != 1 or sets[0].duration_seconds is None:
        return None
    for segment in _comment_segments(comment):
        duration_seconds = _duration_seconds(segment)
        if duration_seconds == sets[0].duration_seconds:
            return _duration_performance_notes(comment, segment)
    return None


def _comment_duplicates_structured_sets(
    comment: str,
    sets: list[PostWorkoutsRequestSet],
) -> bool:
    if not sets:
        return False
    comment_signatures = _comment_set_signatures(comment)
    set_signatures = [_set_signature(set_row) for set_row in sets]
    return bool(comment_signatures) and comment_signatures == set_signatures


def _comment_set_signatures(comment: str) -> list[tuple[Any, ...]]:
    signatures = []
    for segment in _comment_segments(comment):
        signature = _comment_segment_signature(segment)
        if signature is None:
            return []
        signatures.append(signature)
    return signatures


def _comment_segment_signature(segment: str) -> tuple[Any, ...] | None:
    normalized = segment.casefold().replace(chr(215), "x").strip()
    explicit_weight_reps = re.fullmatch(
        r"(?P<weight>\d+(?:\.\d+)?)\s*kg\s*x\s*(?P<reps>\d+)",
        normalized,
    )
    if explicit_weight_reps is not None:
        return (
            "weight_reps",
            _metric_number(explicit_weight_reps.group("weight")),
            int(explicit_weight_reps.group("reps")),
        )
    reps_weight = re.fullmatch(
        r"(?P<reps>\d+)\s*x\s*(?P<weight>\d+(?:\.\d+)?)\s*(?:kg)?",
        normalized,
    )
    if reps_weight is not None:
        return (
            "weight_reps",
            _metric_number(reps_weight.group("weight")),
            int(reps_weight.group("reps")),
        )
    duration = re.fullmatch(r"(?P<seconds>\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds?)?", normalized)
    if duration is not None:
        return ("duration_seconds", round(float(duration.group("seconds"))))
    return None


def _set_signature(set_row: PostWorkoutsRequestSet) -> tuple[Any, ...]:
    if set_row.weight_kg is not None and set_row.reps is not None:
        return ("weight_reps", _metric_number(set_row.weight_kg), int(set_row.reps))
    if set_row.duration_seconds is not None:
        return ("duration_seconds", int(set_row.duration_seconds))
    if set_row.distance_meters is not None:
        return ("distance_meters", int(set_row.distance_meters))
    if set_row.reps is not None:
        return ("reps", int(set_row.reps))
    return ("empty",)


def _metric_number(value: str | float) -> float | int:
    number = float(value)
    return int(number) if number.is_integer() else number
