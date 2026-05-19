"""Build deterministic True Coach Workout backfill review bundles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from fitness_tracker.apis.hevy_app.types.workout_request_body import PostWorkoutsRequestBody
from fitness_tracker.apis.hevy_app.types.workout_requests import (
    PostWorkoutsRequestExercise,
    PostWorkoutsRequestSet,
)
from fitness_tracker.database import Store
from fitness_tracker.database.models.apple_health import (
    AppleHealthDataRecord,
    AppleHealthDataType,
    AppleHealthWorkout,
    AppleHealthWorkoutType,
)
from fitness_tracker.database.models.hevy_app import HevyAppExercise, HevyAppWorkoutItem
from fitness_tracker.database.models.tracker import (
    Exercise as TrackerExercise,
    Sets,
    Workout as TrackerWorkout,
    WorkoutItem as TrackerWorkoutItem,
)
from fitness_tracker.database.models.true_coach import TrueCoachWorkout
from fitness_tracker.sync._circuit_block_parser import (
    ParsedCircuitBlock,
    parse_circuit_block,
)
from fitness_tracker.sync._true_coach_html import build_superset_index, parse_workout_order
from fitness_tracker.sync.ports import HevyWorkoutWriter
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


class WorkoutBackfillReviewError(Exception):
    """Raised when a Workout backfill review cannot be produced."""


class WorkoutBackfillApplyError(Exception):
    """Raised when a Workout backfill request is not safe to apply."""


_EMPTY_WORKOUT_BACKFILL_REQUEST_BLOCKER = (
    "No performed exercise blocks are requestable for Workout backfill"
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
class WorkoutBackfillReviewBundle:
    """Paths written for one Workout backfill review."""

    directory: Path
    report_path: Path
    plan_path: Path
    request_path: Path
    apple_health_evidence_path: Path
    decisions_path: Path
    decision_validation_path: Path


@dataclass(frozen=True)
class WorkoutBackfillApplyResult:
    """Paths and request body produced for a Workout backfill apply attempt."""

    review_bundle: WorkoutBackfillReviewBundle | None
    request_path: Path
    request_body: PostWorkoutsRequestBody
    action: str


@dataclass(frozen=True)
class WorkoutBackfillReviewArtifacts:
    """Rendered artifacts for one Workout backfill review."""

    plan: dict[str, Any]
    request: PostWorkoutsRequestBody
    decisions: dict[str, Any]
    decision_validation: dict[str, list[str]]
    apple_health_evidence: dict[str, Any]
    report: str


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
class AppleHealthEvidenceContext:
    """Apple Health rows scoped to one True Coach due date."""

    workouts: list[AppleHealthWorkout]
    heart_rates: list[AppleHealthDataRecord]
    heart_rate_blocks: list[list[AppleHealthDataRecord]]
    due: datetime


@dataclass(frozen=True)
class BackfillReportContext:
    """Inputs for rendering a Workout backfill review report."""

    workout: TrueCoachWorkout
    plan: dict[str, Any]
    apple_health_evidence: dict[str, Any]
    decision_validation: dict[str, list[str]]


@dataclass(frozen=True)
class ApplyRequestValidationContext:
    """Inputs for validating a dry-run Hevy Workout apply request."""

    plan: dict[str, Any]
    decision_validation: dict[str, list[str]]
    request_body: PostWorkoutsRequestBody
    decisions: dict[str, Any]


@dataclass(frozen=True)
class BackfillLinkContext:
    """Inputs needed to link a remote Hevy Workout to local tracker rows."""

    workout_id: int
    workout: Any
    plan: dict[str, Any]
    decisions: dict[str, Any]


@dataclass(frozen=True)
class CreatedWorkoutItemLinkContext:
    """Inputs needed to link one created Hevy item to a tracker item."""

    tracker_workout: TrackerWorkout
    item: dict[str, Any]
    decisions: dict[str, Any]


class TrueCoachWorkoutBackfillReviewService:
    """Create a review bundle for one completed True Coach Workout backfill."""

    def __init__(self, store: Store, output_root: Path = Path("reports")) -> None:
        """Create the service.

        Args:
            store (Store): Local database snapshot.
            output_root (Path): Root under which review artifacts are written.
        """
        self._store = store
        self._output_root = output_root

    def write_review(
        self,
        workout_id: int,
        decisions_path: Path | None = None,
    ) -> WorkoutBackfillReviewBundle:
        """Write deterministic plan, draft Hevy Workout request, and report.

        Args:
            workout_id (int): True Coach Workout id.
            decisions_path (Path | None): Optional editable decisions JSON to apply.

        Returns:
            WorkoutBackfillReviewBundle: Paths written by the service.
        """
        decisions = _load_decisions(decisions_path) if decisions_path is not None else None
        artifacts = self._build_artifacts(workout_id, decisions)
        (
            bundle_dir,
            plan_path,
            request_path,
            apple_health_evidence_path,
            report_path,
            output_decisions_path,
            decision_validation_path,
        ) = _bundle_paths(self._output_root, workout_id)
        plan_path.write_text(
            json.dumps(artifacts.plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        request_path.write_text(
            json.dumps(artifacts.request.model_dump(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        output_decisions_path.write_text(
            json.dumps(artifacts.decisions, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        decision_validation_path.write_text(
            json.dumps(artifacts.decision_validation, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        apple_health_evidence_path.write_text(
            json.dumps(artifacts.apple_health_evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report_path.write_text(artifacts.report, encoding="utf-8")
        return WorkoutBackfillReviewBundle(
            directory=bundle_dir,
            report_path=report_path,
            plan_path=plan_path,
            request_path=request_path,
            apple_health_evidence_path=apple_health_evidence_path,
            decisions_path=output_decisions_path,
            decision_validation_path=decision_validation_path,
        )

    def write_apply_request(
        self,
        workout_id: int,
        decisions_path: Path | None = None,
    ) -> WorkoutBackfillApplyResult:
        """Validate and write the exact Hevy Workout request body for dry-run apply.

        Args:
            workout_id (int): True Coach Workout id.
            decisions_path (Path | None): Optional editable decisions JSON to apply.

        Returns:
            WorkoutBackfillApplyResult: Validated request path and typed body.
        """
        bundle = self.write_review(workout_id, decisions_path=decisions_path)
        plan = json.loads(bundle.plan_path.read_text(encoding="utf-8"))
        request_data = json.loads(bundle.request_path.read_text(encoding="utf-8"))
        decision_validation = json.loads(
            bundle.decision_validation_path.read_text(encoding="utf-8")
        )
        decisions = json.loads(bundle.decisions_path.read_text(encoding="utf-8"))
        request_body = PostWorkoutsRequestBody(**request_data)
        _validate_apply_request(
            ApplyRequestValidationContext(
                plan=plan,
                decision_validation=decision_validation,
                request_body=request_body,
                decisions=decisions,
            )
        )
        return WorkoutBackfillApplyResult(
            review_bundle=bundle,
            request_path=bundle.request_path,
            request_body=request_body,
            action="dry_run",
        )

    def apply(
        self,
        workout_id: int,
        *,
        workout_writer: HevyWorkoutWriter,
        decisions_path: Path | None = None,
    ) -> WorkoutBackfillApplyResult:
        """Create a Hevy Workout from a validated backfill request.

        Args:
            workout_id (int): True Coach Workout id.
            workout_writer (HevyWorkoutWriter): Workout writer port.
            decisions_path (Path | None): Optional editable decisions JSON to apply.

        Returns:
            WorkoutBackfillApplyResult: Request body and local artifacts.
        """
        result = self.write_apply_request(workout_id, decisions_path=decisions_path)
        if self._tracker_workout_is_linked(workout_id):
            return _apply_result_with_action(result, "already_linked")
        plan = _load_json_file(result.review_bundle.plan_path) if result.review_bundle else {}
        decisions = (
            _load_json_file(result.review_bundle.decisions_path) if result.review_bundle else {}
        )
        existing_remote = _find_remote_backfill(workout_writer, workout_id)
        if existing_remote is not None:
            unlinked = self._sync_and_link_created_workout(
                BackfillLinkContext(
                    workout_id=workout_id,
                    workout=existing_remote,
                    plan=plan,
                    decisions=decisions,
                )
            )
            _raise_for_unlinked_created_rows(result, existing_remote.id, unlinked)
            return _apply_result_with_action(result, "repaired_existing_remote")
        response = workout_writer.create_workout(result.request_body)
        if response and response.workout:
            unlinked = self._sync_and_link_created_workout(
                BackfillLinkContext(
                    workout_id=workout_id,
                    workout=response.workout[0],
                    plan=plan,
                    decisions=decisions,
                )
            )
            _raise_for_unlinked_created_rows(result, response.workout[0].id, unlinked)
        return _apply_result_with_action(result, "created")

    def apply_manual_request(
        self,
        request_path: Path,
        *,
        workout_id: int,
        workout_writer: HevyWorkoutWriter,
    ) -> WorkoutBackfillApplyResult:
        """Create a Hevy Workout from an Agent-edited request artifact.

        Args:
            request_path (Path): Edited Hevy Workout request JSON.
            workout_id (int): Expected source True Coach Workout id marker.
            workout_writer (HevyWorkoutWriter): Workout writer port.

        Returns:
            WorkoutBackfillApplyResult: Submitted request body.
        """
        request_body = _load_manual_request(request_path)
        _validate_manual_apply_request(request_body, workout_id=workout_id)
        workout_writer.create_workout(request_body)
        return WorkoutBackfillApplyResult(
            review_bundle=None,
            request_path=request_path,
            request_body=request_body,
            action="created",
        )

    def repair_local_links(
        self,
        workout_id: int,
        *,
        workout_writer: HevyWorkoutWriter,
        decisions_path: Path | None = None,
    ) -> WorkoutBackfillApplyResult:
        """Repair local tracker links without creating a remote Hevy Workout.

        Args:
            workout_id (int): True Coach Workout id.
            workout_writer (HevyWorkoutWriter): Workout reader/writer port.
            decisions_path (Path | None): Optional editable decisions JSON to apply.

        Returns:
            WorkoutBackfillApplyResult: Validated request and repair action.

        Raises:
            WorkoutBackfillApplyError: If no linked or marked remote Hevy Workout exists.
        """
        result = self.write_apply_request(workout_id, decisions_path=decisions_path)
        plan = _load_json_file(result.review_bundle.plan_path) if result.review_bundle else {}
        decisions = (
            _load_json_file(result.review_bundle.decisions_path) if result.review_bundle else {}
        )
        remote = self._linked_remote_workout(workout_id, workout_writer)
        if remote is None:
            remote = _find_remote_backfill(workout_writer, workout_id)
        if remote is None:
            msg = (
                f"No linked or marked remote Hevy Workout found for True Coach Workout {workout_id}"
            )
            raise WorkoutBackfillApplyError(msg)
        unlinked = self._sync_and_link_created_workout(
            BackfillLinkContext(
                workout_id=workout_id,
                workout=remote,
                plan=plan,
                decisions=decisions,
            )
        )
        _raise_for_unlinked_created_rows(result, remote.id, unlinked)
        return _apply_result_with_action(result, "repaired_existing_remote")

    def _build_artifacts(
        self,
        workout_id: int,
        decisions: dict[str, Any] | None = None,
    ) -> WorkoutBackfillReviewArtifacts:
        with self._store.unit_of_work() as uow:
            workout = uow.true_coach.get_workout(id=workout_id)
            if workout is None:
                msg = f"True Coach workout {workout_id} was not found in the local DB"
                raise WorkoutBackfillReviewError(msg)
            tracker_workout = workout.tracker
            if not isinstance(tracker_workout, TrackerWorkout):
                msg = f"True Coach workout {workout_id} has no local tracker Workout row"
                raise WorkoutBackfillReviewError(msg)

            templates = list(
                uow.session.execute(
                    select(HevyAppExercise).order_by(HevyAppExercise.name)
                ).scalars()
            )
            items = _review_items(
                sorted(
                    tracker_workout.workout_items,
                    key=lambda item: (item.position, item.id),
                ),
                templates,
                _superset_ids_by_position(workout),
            )
            plan = _plan(workout, tracker_workout, items)
            apple_health_evidence = _apple_health_evidence(uow.session, workout.due)
            resolved_decisions = decisions or _decision_template(workout_id, plan)
            decision_validation = _validate_decisions(workout_id, resolved_decisions, plan)
            return WorkoutBackfillReviewArtifacts(
                plan=plan,
                request=_build_hevy_workout_request(plan, resolved_decisions),
                decisions=resolved_decisions,
                decision_validation=decision_validation,
                apple_health_evidence=apple_health_evidence,
                report=_report(
                    BackfillReportContext(
                        workout=workout,
                        plan=plan,
                        apple_health_evidence=apple_health_evidence,
                        decision_validation=decision_validation,
                    )
                ),
            )

    def _tracker_workout_is_linked(self, workout_id: int) -> bool:
        with self._store.unit_of_work() as uow:
            tracker_workout = uow.tracker.get_workout(true_coach_id=workout_id)
            return bool(tracker_workout and tracker_workout.hevy_app_id)

    def _linked_remote_workout(
        self,
        workout_id: int,
        workout_writer: HevyWorkoutWriter,
    ) -> Any | None:
        getter = getattr(workout_writer, "get_workout", None)
        if getter is None:
            return None
        with self._store.unit_of_work() as uow:
            tracker_workout = uow.tracker.get_workout(true_coach_id=workout_id)
            hevy_app_id = tracker_workout.hevy_app_id if tracker_workout is not None else None
        return getter(hevy_app_id) if hevy_app_id else None

    def _sync_and_link_created_workout(self, context: BackfillLinkContext) -> list[int]:  # noqa: PLR0915
        unlinked_tracker_item_ids: list[int] = []
        with self._store.unit_of_work() as uow:
            uow.hevy.add_workout(context.workout)
            tracker_workout = uow.tracker.get_workout(true_coach_id=context.workout_id)
            if tracker_workout is None:
                return [
                    item["tracker_workout_item_id"]
                    for item in _requestable_plan_items(context.plan, context.decisions)
                ]
            tracker_workout.hevy_app_id = context.workout.id
            tracker_workout.start_date = datetime.fromisoformat(context.workout.start_time)
            tracker_workout.end_date = datetime.fromisoformat(context.workout.end_time)
            uow.session.flush()
            for request_index, item in enumerate(
                _requestable_plan_items(context.plan, context.decisions)
            ):
                tracker_item = _tracker_item_for_created_hevy_row(
                    uow.session,
                    CreatedWorkoutItemLinkContext(
                        tracker_workout=tracker_workout,
                        item=item,
                        decisions=context.decisions,
                    ),
                )
                hevy_item = uow.session.execute(
                    select(HevyAppWorkoutItem).where(
                        HevyAppWorkoutItem.workout_id == context.workout.id,
                        HevyAppWorkoutItem.index == request_index,
                    )
                ).scalar_one_or_none()
                if tracker_item is None or hevy_item is None:
                    unlinked_tracker_item_ids.append(item["tracker_workout_item_id"])
                    continue
                tracker_item.hevy_app_id = hevy_item.id
                local_sets = sorted(tracker_item.sets, key=lambda row: row.index)
                hevy_sets = sorted(hevy_item.sets, key=lambda row: row.index)
                if not local_sets and item.get("sets"):
                    local_sets = _create_missing_local_sets(tracker_item, item, hevy_sets)
                    uow.session.flush()
                if len(local_sets) != len(hevy_sets):
                    unlinked_tracker_item_ids.append(item["tracker_workout_item_id"])
                for local_set, hevy_set in zip(
                    local_sets,
                    hevy_sets,
                    strict=False,
                ):
                    local_set.hevy_app_id = hevy_set.id
        return unlinked_tracker_item_ids


def _tracker_item_for_created_hevy_row(
    session: Any,
    context: CreatedWorkoutItemLinkContext,
) -> TrackerWorkoutItem | None:
    item = context.item
    if not _is_expanded_circuit_movement_item(item):
        return session.get(TrackerWorkoutItem, id=item["tracker_workout_item_id"])
    template_id = _request_exercise_template_id(item, context.decisions)
    if template_id is None:
        return None
    exercise = _tracker_exercise_for_synthetic_item(
        session=session,
        name=item["name"],
        hevy_app_id=template_id,
    )
    tracker_item = _existing_synthetic_tracker_item(
        session,
        context,
        exercise_id=exercise.id,
    )
    if tracker_item is not None:
        return tracker_item
    tracker_item = TrackerWorkoutItem(
        workout_id=context.tracker_workout.id,
        position=item["position"],
        exercise_id=exercise.id,
        true_coach_id=item["source_id"],
    )
    session.add(tracker_item)
    session.flush()
    return tracker_item


def _tracker_exercise_for_synthetic_item(
    *,
    session: Any,
    name: str,
    hevy_app_id: str,
) -> TrackerExercise:
    exercise = session.execute(
        select(TrackerExercise).where(TrackerExercise.hevy_app_id == hevy_app_id)
    ).scalar_one_or_none()
    if exercise is not None:
        return exercise
    exercise = session.execute(
        select(TrackerExercise).where(TrackerExercise.name == name)
    ).scalar_one_or_none()
    if exercise is not None:
        exercise.hevy_app_id = hevy_app_id
        session.flush()
        return exercise
    exercise = TrackerExercise(name=name, hevy_app_id=hevy_app_id)
    session.add(exercise)
    session.flush()
    return exercise


def _existing_synthetic_tracker_item(
    session: Any,
    context: CreatedWorkoutItemLinkContext,
    *,
    exercise_id: int,
) -> TrackerWorkoutItem | None:
    source_id = context.item["source_id"]
    if source_id is None:
        return None
    return session.execute(
        select(TrackerWorkoutItem).where(
            TrackerWorkoutItem.workout_id == context.tracker_workout.id,
            TrackerWorkoutItem.true_coach_id == source_id,
            TrackerWorkoutItem.exercise_id == exercise_id,
        )
    ).scalar_one_or_none()


def _create_missing_local_sets(
    tracker_item: TrackerWorkoutItem,
    item: dict[str, Any],
    hevy_sets: list[Any],
) -> list[Sets]:
    local_sets = []
    for index, set_data in enumerate(item.get("sets", [])):
        hevy_set = hevy_sets[index] if index < len(hevy_sets) else None
        local_set = Sets(
            workout_item_id=tracker_item.id,
            index=index,
            type=set_data["type"],
            weight_kg=set_data.get("weight_kg"),
            reps=set_data.get("reps"),
            distance_meters=set_data.get("distance_meters"),
            duration_seconds=set_data.get("duration_seconds"),
            rpe=set_data.get("rpe"),
            hevy_app_id=hevy_set.id if hevy_set is not None else None,
        )
        tracker_item.sets.append(local_set)
        local_sets.append(local_set)
    return local_sets


def _bundle_paths(
    output_root: Path,
    workout_id: int,
) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    bundle_dir = output_root / "sync-review" / "truecoach-workout-backfill" / str(workout_id)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    return (
        bundle_dir,
        bundle_dir / "plan.json",
        bundle_dir / "hevy-workout-request.json",
        bundle_dir / "apple-health-evidence.json",
        bundle_dir / "report.md",
        bundle_dir / "backfill-decisions.json",
        bundle_dir / "decision-validation.json",
    )


def _review_items(
    tracker_items: list[Any],
    templates: list[HevyAppExercise],
    superset_ids_by_position: dict[int, int],
) -> list[BackfillReviewItem]:
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


@dataclass(frozen=True)
class ReplacementMovement:
    """A named performed replacement from an Athlete backfill comment."""

    omitted_name: str
    name: str
    source_text: str


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


def _plan(
    workout: TrueCoachWorkout,
    tracker_workout: TrackerWorkout,
    items: list[BackfillReviewItem],
) -> dict[str, Any]:
    item_plans = [_plan_item(item) for item in items]
    return {
        "blockers": [blocker for item in item_plans for blocker in item["blockers"]],
        "warnings": [warning for item in item_plans for warning in item["warnings"]],
        "workout": {
            "id": workout.id,
            "title": workout.title,
            "due": workout.due.isoformat() if workout.due else None,
            "state": workout.state,
            "tracker_workout_id": tracker_workout.id,
            "tracker_hevy_app_id": tracker_workout.hevy_app_id,
        },
        "items": item_plans,
    }


def _plan_item(item: BackfillReviewItem) -> dict[str, Any]:
    plan = {
        "source_id": item.source_id,
        "tracker_workout_item_id": item.tracker_workout_item_id,
        "position": item.position,
        "superset_id": item.superset_id,
        "name": item.name,
        "info": item.info,
        "comment": item.comment,
        "selected_hevy_template": _template_to_dict(item.selected_hevy_template),
        "sets": [_set_to_dict(set_row) for set_row in item.sets],
        "notes": item.notes,
        "warnings": item.warnings,
        "blockers": item.blockers,
    }
    if item.movement_target is not None:
        plan["movement_target"] = item.movement_target
    if item.original_prescription_text is not None:
        plan["original_prescription_text"] = item.original_prescription_text
    if item.completed_round_count is not None:
        plan["completed_round_count"] = item.completed_round_count
    if item.choice_decision_reason is not None:
        plan["choice_template_candidates"] = item.choice_template_candidate_ids or []
        plan["choice_decision_reason"] = item.choice_decision_reason
    if item.circuit_decision_reason is not None:
        plan["circuit_template_candidates"] = item.circuit_template_candidate_ids or []
        plan["circuit_decision_reason"] = item.circuit_decision_reason
    if item.replacement_for_movement_name is not None:
        plan["replacement_for_movement_name"] = item.replacement_for_movement_name
    if item.replacement_source_comment is not None:
        plan["replacement_source_comment"] = item.replacement_source_comment
    return plan


def _template_to_dict(template: HevyAppExercise | None) -> dict[str, str] | None:
    if template is None:
        return None
    return {
        "id": template.id,
        "name": template.name,
        "type": template.type,
        "equipment": template.equipment,
    }


def _set_to_dict(set_row: PostWorkoutsRequestSet) -> dict[str, int | float | str]:
    return set_row.model_dump(exclude_none=True)


def _load_decisions(decisions_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(decisions_path.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"Could not read decisions file {decisions_path}: {exc}"
        raise WorkoutBackfillReviewError(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"Could not parse decisions file {decisions_path}: {exc}"
        raise WorkoutBackfillReviewError(msg) from exc
    if not isinstance(data, dict):
        msg = f"Decisions file {decisions_path} must contain a JSON object"
        raise WorkoutBackfillReviewError(msg)
    return data


def _load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_remote_backfill(workout_writer: HevyWorkoutWriter, workout_id: int) -> Any | None:
    finder = getattr(workout_writer, "find_workout_by_true_coach_id", None)
    if finder is None:
        return None
    return finder(workout_id)


def _raise_for_unlinked_created_rows(
    result: WorkoutBackfillApplyResult,
    remote_workout_id: str,
    unlinked_tracker_workout_item_ids: list[int],
) -> None:
    if not unlinked_tracker_workout_item_ids:
        return
    if result.review_bundle is not None:
        recovery_path = result.review_bundle.directory / "backfill-recovery.json"
        recovery_path.write_text(
            json.dumps(
                {
                    "true_coach_workout_id": _source_workout_id(result.request_body),
                    "remote_hevy_workout_id": remote_workout_id,
                    "request_path": str(result.request_path),
                    "plan_path": str(result.review_bundle.plan_path),
                    "unlinked_tracker_workout_item_ids": unlinked_tracker_workout_item_ids,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    msg = "Could not link all created Hevy rows; recovery artifact written"
    raise WorkoutBackfillApplyError(msg)


def _apply_result_with_action(
    result: WorkoutBackfillApplyResult,
    action: str,
) -> WorkoutBackfillApplyResult:
    return WorkoutBackfillApplyResult(
        review_bundle=result.review_bundle,
        request_path=result.request_path,
        request_body=result.request_body,
        action=action,
    )


def _source_workout_id(request_body: PostWorkoutsRequestBody) -> int | None:
    marker = re.search(r"True Coach Workout (\d+)", request_body.workout.description or "")
    return int(marker.group(1)) if marker else None


def _requestable_plan_items(
    plan: dict[str, Any],
    decisions: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        item
        for item in plan.get("items", [])
        if item.get("sets") and _request_exercise_template_id(item, decisions) is not None
    ]


def _decision_template(workout_id: int, plan: dict[str, Any] | None = None) -> dict[str, Any]:
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


def _validate_decisions(
    workout_id: int,
    decisions: dict[str, Any],
    plan: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
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
    return {"blockers": blockers, "warnings": warnings}


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


def _build_hevy_workout_request(
    plan: dict[str, Any],
    decisions: dict[str, Any] | None = None,
) -> PostWorkoutsRequestBody:
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


def _request_exercises(
    items: list[dict[str, Any]],
    decisions: dict[str, Any] | None,
    superset_allocator: _WorkoutRequestSupersetAllocator,
) -> list[PostWorkoutsRequestExercise]:
    exercises = []
    for item in items:
        template_id = _request_exercise_template_id(item, decisions)
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
        if not _is_expanded_circuit_movement_item(item):
            return None
        key = (item.get("source_id"), int(item["tracker_workout_item_id"]))
        if key not in self._expanded_circuit_superset_ids:
            self._expanded_circuit_superset_ids[key] = self._next_id
            self._next_id += 1
        return self._expanded_circuit_superset_ids[key]


def _is_expanded_circuit_movement_item(item: dict[str, Any]) -> bool:
    return (
        "movement_target" in item
        and "original_prescription_text" in item
        and "completed_round_count" in item
    )


def _request_exercise(
    item: dict[str, Any],
    *,
    template_id: str | None,
    superset_id: int | None,
) -> PostWorkoutsRequestExercise:
    if template_id is None:
        msg = f"Missing Hevy template for request exercise: {item['name']}"
        raise WorkoutBackfillReviewError(msg)
    return PostWorkoutsRequestExercise(
        exercise_template_id=template_id,
        superset_id=superset_id,
        notes=item["notes"] or None,
        sets=[PostWorkoutsRequestSet(**set_row) for set_row in item["sets"]],
    )


def _request_exercise_template_id(
    item: dict[str, Any],
    decisions: dict[str, Any] | None,
) -> str | None:
    if item["selected_hevy_template"] is not None:
        return item["selected_hevy_template"]["id"]
    if decisions is None:
        return None
    decision = _manual_template_decision_for(item, decisions)
    if decision is None:
        return None
    selected_template_id = decision.get("selected_hevy_template_id")
    return selected_template_id if isinstance(selected_template_id, str) else None


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


def _validate_apply_request(context: ApplyRequestValidationContext) -> None:
    blockers = [
        blocker
        for item in context.plan.get("items", [])
        for blocker in item.get("blockers", [])
        if _request_exercise_template_id(item, context.decisions) is None
        or blocker.startswith(AGENT_DECISION_BLOCKER_PREFIX)
    ]
    blockers.extend(context.decision_validation.get("blockers", []))
    workout = context.request_body.workout
    if not workout.start_time or not workout.end_time:
        blocker = "Missing required decision: selected Workout timestamps"
        if blocker not in blockers:
            blockers.append(blocker)
    if not workout.exercises:
        blockers.append(_EMPTY_WORKOUT_BACKFILL_REQUEST_BLOCKER)
    blockers.extend(
        f"Missing Hevy template mapping for performed item: {item['name']}"
        for item in context.plan.get("items", [])
        if item.get("sets") and _request_exercise_template_id(item, context.decisions) is None
    )
    if blockers:
        raise WorkoutBackfillApplyError("; ".join(blockers))


def _load_manual_request(request_path: Path) -> PostWorkoutsRequestBody:
    try:
        data = json.loads(request_path.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"Could not read Hevy Workout request file {request_path}: {exc}"
        raise WorkoutBackfillApplyError(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"Could not parse Hevy Workout request file {request_path}: {exc}"
        raise WorkoutBackfillApplyError(msg) from exc
    try:
        return PostWorkoutsRequestBody(**data)
    except ValueError as exc:
        msg = f"Invalid Hevy Workout request file {request_path}: {exc}"
        raise WorkoutBackfillApplyError(msg) from exc


def _validate_manual_apply_request(
    request_body: PostWorkoutsRequestBody,
    *,
    workout_id: int,
) -> None:
    blockers: list[str] = []
    workout = request_body.workout
    if not workout.start_time or not workout.end_time:
        blockers.append("Missing required Hevy Workout timestamps")
    marker = f"True Coach Workout {workout_id}"
    if marker not in (workout.description or ""):
        blockers.append(f"Missing source True Coach Workout id marker: {workout_id}")
    if not workout.exercises:
        blockers.append(_EMPTY_WORKOUT_BACKFILL_REQUEST_BLOCKER)
    for index, exercise in enumerate(workout.exercises, start=1):
        if not exercise.exercise_template_id:
            blockers.append(f"Missing Hevy template mapping for request exercise {index}")
        if not exercise.sets:
            blockers.append(f"Invalid set payload for request exercise {index}: no sets")
    if blockers:
        raise WorkoutBackfillApplyError("; ".join(blockers))


def _apple_health_evidence(session: Any, due: datetime | None) -> dict[str, Any]:
    if due is None:
        return {
            "true_coach_due_date": None,
            "search_window": {"start": None, "end": None},
            "workout_intervals": [],
            "heart_rate_summaries": [],
            "candidate_windows": [],
        }
    window_start = datetime.combine(due.date() - timedelta(days=1), time.min)
    window_end = datetime.combine(due.date() + timedelta(days=1), time(23, 59, 59))
    workouts = _apple_workouts(session, window_start, window_end)
    heart_rates = _heart_rates(session, window_start, window_end)
    context = AppleHealthEvidenceContext(
        workouts=workouts,
        heart_rates=heart_rates,
        heart_rate_blocks=_elevated_heart_rate_blocks(heart_rates, due),
        due=due,
    )
    summaries = [_heart_rate_summary(heart_rates, workout) for workout in workouts]
    summaries = [summary for summary in summaries if summary is not None]
    summaries.extend(
        _heart_rate_block_summary(block)
        for block in context.heart_rate_blocks
        if not _block_overlaps_workouts(block, workouts)
    )
    return {
        "true_coach_due_date": due.date().isoformat(),
        "search_window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
        },
        "workout_intervals": [_workout_interval_dict(workout) for workout in workouts],
        "heart_rate_summaries": summaries,
        "candidate_windows": _candidate_windows(context),
    }


def _apple_workouts(session: Any, start: datetime, end: datetime) -> list[AppleHealthWorkout]:
    statement = (
        select(AppleHealthWorkout)
        .join(
            AppleHealthWorkoutType,
            AppleHealthWorkout.workout_type_id == AppleHealthWorkoutType.id,
        )
        .where(AppleHealthWorkout.start_date.between(start, end))
        .order_by(AppleHealthWorkout.start_date)
    )
    return list(session.execute(statement).scalars().all())


def _heart_rates(
    session: Any,
    start: datetime,
    end: datetime,
) -> list[AppleHealthDataRecord]:
    statement = (
        select(AppleHealthDataRecord)
        .join(
            AppleHealthDataType,
            AppleHealthDataRecord.data_type_id == AppleHealthDataType.id,
        )
        .where(
            AppleHealthDataType.name.in_(("Heart Rate", "Heart Rate [Avg]")),
            AppleHealthDataRecord.timestamp.between(start, end),
        )
        .order_by(AppleHealthDataRecord.timestamp)
    )
    return list(session.execute(statement).scalars().all())


def _workout_interval_dict(workout: AppleHealthWorkout) -> dict[str, Any]:
    return {
        "type": workout.workout_type.name,
        "start": workout.start_date.isoformat(),
        "end": workout.end_date.isoformat(),
        "duration_minutes": round(
            (workout.end_date - workout.start_date).total_seconds() / 60,
            1,
        ),
    }


def _heart_rate_summary(
    heart_rates: list[AppleHealthDataRecord],
    workout: AppleHealthWorkout,
) -> dict[str, Any] | None:
    window_start = workout.start_date - timedelta(minutes=30)
    window_end = workout.end_date + timedelta(minutes=30)
    values = [
        float(row.value) for row in heart_rates if window_start <= row.timestamp <= window_end
    ]
    if not values:
        return None
    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "sample_count": len(values),
        "average_bpm": round(sum(values) / len(values), 1),
        "max_bpm": round(max(values), 1),
    }


def _candidate_windows(context: AppleHealthEvidenceContext) -> list[dict[str, str]]:
    candidates = []
    for workout in context.workouts:
        interval_values = _heart_rate_values(
            context.heart_rates,
            workout.start_date,
            workout.end_date,
        )
        if workout.start_date.date() != context.due.date():
            continue
        if interval_values and max(interval_values) >= 120:
            candidates.append(
                {
                    "source": "apple_workout_interval",
                    "confidence": "high",
                    "start": workout.start_date.isoformat(),
                    "end": workout.end_date.isoformat(),
                    "reason": "Apple Health workout interval with elevated heart-rate samples.",
                }
            )
        else:
            candidates.append(
                {
                    "source": "apple_workout_interval",
                    "confidence": "medium",
                    "start": workout.start_date.isoformat(),
                    "end": workout.end_date.isoformat(),
                    "reason": "Apple Health workout interval on the True Coach due date.",
                }
            )
    for block in context.heart_rate_blocks:
        if _block_overlaps_workouts(block, context.workouts):
            continue
        candidates.append(
            {
                "source": "heart_rate_block",
                "confidence": "medium",
                "start": block[0].timestamp.isoformat(),
                "end": block[-1].timestamp.isoformat(),
                "reason": "Elevated heart-rate block without a matching Apple Health workout interval.",
            }
        )
    return candidates


def _heart_rate_values(
    heart_rates: list[AppleHealthDataRecord],
    start: datetime,
    end: datetime,
) -> list[float]:
    return [float(row.value) for row in heart_rates if start <= row.timestamp <= end]


def _elevated_heart_rate_blocks(
    heart_rates: list[AppleHealthDataRecord],
    due: datetime,
) -> list[list[AppleHealthDataRecord]]:
    blocks: list[list[AppleHealthDataRecord]] = []
    current: list[AppleHealthDataRecord] = []
    for row in heart_rates:
        if row.timestamp.date() == due.date() and row.value >= 120:
            current.append(row)
        else:
            _append_elevated_block(blocks, current)
            current = []
    _append_elevated_block(blocks, current)
    return blocks


def _append_elevated_block(
    blocks: list[list[AppleHealthDataRecord]],
    current: list[AppleHealthDataRecord],
) -> None:
    if len(current) >= 3:
        blocks.append(current.copy())


def _heart_rate_block_summary(block: list[AppleHealthDataRecord]) -> dict[str, Any]:
    values = [float(row.value) for row in block]
    return {
        "window_start": block[0].timestamp.isoformat(),
        "window_end": block[-1].timestamp.isoformat(),
        "sample_count": len(values),
        "average_bpm": round(sum(values) / len(values), 1),
        "max_bpm": round(max(values), 1),
    }


def _block_overlaps_workouts(
    block: list[AppleHealthDataRecord],
    workouts: list[AppleHealthWorkout],
) -> bool:
    block_start = block[0].timestamp
    block_end = block[-1].timestamp
    return any(
        block_start <= workout.end_date and block_end >= workout.start_date for workout in workouts
    )


def _report(context: BackfillReportContext) -> str:
    workout = context.workout
    lines = [
        f"# True Coach Workout Backfill Review: {workout.id}",
        "",
        f"Workout: {workout.title or 'Untitled'}",
        f"Due: {workout.due.isoformat() if workout.due else 'unknown'}",
        "Draft Hevy Workout request: hevy-workout-request.json",
        "Editable decisions: backfill-decisions.json",
        "Decision validation: decision-validation.json",
        "Apple Health evidence: apple-health-evidence.json",
        "",
    ]
    lines.extend(_report_review_validation(context.plan))
    lines.extend(_report_decision_validation(context.decision_validation))
    if context.apple_health_evidence["candidate_windows"]:
        lines.append("Candidate timing windows:")
        lines.extend(
            f"- {candidate['confidence']}: {candidate['start']} to {candidate['end']}"
            for candidate in context.apple_health_evidence["candidate_windows"]
        )
    lines.append("")
    for index, item in enumerate(context.plan["items"], start=1):
        lines.extend(_report_item(index, item))
    return "\n".join(lines).rstrip() + "\n"


def _report_review_validation(plan: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if plan["blockers"]:
        lines.append("Blockers:")
        lines.extend(f"- {blocker}" for blocker in plan["blockers"])
    else:
        lines.append("Blockers: none")
    if plan["warnings"]:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in plan["warnings"])
    return lines


def _report_decision_validation(decision_validation: dict[str, list[str]]) -> list[str]:
    lines: list[str] = []
    if decision_validation["blockers"]:
        lines.append("Decision blockers:")
        lines.extend(f"- {blocker}" for blocker in decision_validation["blockers"])
    else:
        lines.append("Decision blockers: none")
    if decision_validation["warnings"]:
        lines.append("Decision warnings:")
        lines.extend(f"- {warning}" for warning in decision_validation["warnings"])
    return lines


def _report_item(index: int, item: dict[str, Any]) -> list[str]:
    template = item["selected_hevy_template"]
    details = [
        f"True Coach Workout Item: {item['source_id'] or 'none'}",
        f"Tracker WorkoutItem: {item['tracker_workout_item_id']}",
        f"Coach prescription: {item['info'] or 'none'}",
        f"Athlete comment: {item['comment'] or 'none'}",
    ]
    if item.get("movement_target") is not None:
        details.append(f"Movement target: {item['movement_target'] or 'none'}")
    if item.get("replacement_for_movement_name") is not None:
        details.append(
            f"Replacement for generated movement: {item['replacement_for_movement_name']}"
        )
    if item.get("replacement_source_comment") is not None:
        details.append(f"Replacement source comment: {item['replacement_source_comment']}")
    if item.get("completed_round_count") is not None:
        details.append(f"Completed rounds: {item['completed_round_count']}")
    lines = [
        f"## {index}. {item['name']}",
        "",
        *details,
        (
            f"Selected Hevy template: {template['name']} ({template['id']})"
            if template is not None
            else "Selected Hevy template: missing"
        ),
        "Structured sets:",
    ]
    if item["sets"]:
        lines.extend(f"- {_format_set(set_row)}" for set_row in item["sets"])
    else:
        lines.append("- none")
    if item["notes"]:
        lines.append(f"Draft notes: {item['notes']}")
    lines.extend(f"WARNING: {warning}" for warning in item["warnings"])
    lines.extend(f"BLOCKER: {blocker}" for blocker in item["blockers"])
    lines.append("")
    return lines


def _format_set(set_row: dict[str, Any]) -> str:
    return "; ".join(f"{key}: {value}" for key, value in set_row.items())
