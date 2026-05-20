"""Build deterministic True Coach Workout backfill review bundles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from fitness_tracker.apis.hevy_app.types.workout_request_body import PostWorkoutsRequestBody
from fitness_tracker.apis.hevy_app.types.workout_requests import PostWorkoutsRequestSet
from fitness_tracker.database import Store
from fitness_tracker.database.models.apple_health import (
    AppleHealthDataRecord,
    AppleHealthDataType,
    AppleHealthWorkout,
    AppleHealthWorkoutType,
)
from fitness_tracker.database.models.hevy_app import HevyAppExercise
from fitness_tracker.database.models.tracker import (
    Workout as TrackerWorkout,
)
from fitness_tracker.database.models.true_coach import TrueCoachWorkout
from fitness_tracker.sync._true_coach_html import build_superset_index, parse_workout_order
from fitness_tracker.sync.ports import HevyWorkoutWriter
from fitness_tracker.sync_review.workout_backfill_request import (
    WorkoutBackfillApplyValidationContext,
    build_hevy_workout_backfill_request,
    build_workout_backfill_decision_template,
    validate_workout_backfill_decisions,
    workout_backfill_apply_blockers,
)
from fitness_tracker.sync_review.workout_backfill_performed_work import (
    BackfillReviewItem,
    plan_performed_work_items,
)
from fitness_tracker.sync_review.workflow import (
    load_decisions_file,
    read_json_object,
    review_bundle_dir,
    write_json_artifact,
)
from fitness_tracker.sync_review.workout_backfill_apply import (
    WorkoutBackfillApplyError,
    WorkoutBackfillApplyResult,
    WorkoutBackfillApplyService,
)


class WorkoutBackfillReviewError(Exception):
    """Raised when a Workout backfill review cannot be produced."""


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
class WorkoutBackfillPipelineReview:
    """Artifact-first review directory written by the Workout backfill pipeline."""

    directory: Path
    manifest_path: Path
    plan_path: Path
    decisions_path: Path
    decision_validation_path: Path
    apple_health_evidence_path: Path
    report_path: Path


@dataclass(frozen=True)
class WorkoutBackfillReviewOptions:
    """Options for regenerating an artifact-first Workout backfill review."""

    force: bool = False
    preserve_decisions: bool = False
    reset_decisions: bool = False


@dataclass(frozen=True)
class WorkoutBackfillInspectResult:
    """Review data loaded through a Workout backfill review manifest."""

    review_dir: Path
    manifest: dict[str, Any]
    plan: dict[str, Any]
    decision_validation: dict[str, Any]


@dataclass(frozen=True)
class WorkoutBackfillPipelinePaths:
    """Artifact paths for one pipeline review directory."""

    manifest: Path
    plan: Path
    decisions: Path
    decision_validation: Path
    apple_health_evidence: Path
    report: Path


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


PIPELINE_REVIEW_DIRNAME = "workout-backfill"
PIPELINE_MANIFEST_FILENAME = "review-manifest.json"
PIPELINE_ARTIFACT_FILENAMES = {
    "plan": "plan.json",
    "decisions": "decisions.json",
    "decision_validation": "decision-validation.json",
    "apple_health_evidence": "apple-health-evidence.json",
    "report": "report.md",
}
PIPELINE_REQUEST_FILENAMES = ("hevy-workout-request.json", "request-manifest.json")


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
        self._apply_service = WorkoutBackfillApplyService(store)

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
        decisions = (
            load_decisions_file(decisions_path, error_cls=WorkoutBackfillReviewError)
            if decisions_path is not None
            else None
        )
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
        write_json_artifact(plan_path, artifacts.plan)
        write_json_artifact(request_path, artifacts.request)
        write_json_artifact(output_decisions_path, artifacts.decisions)
        write_json_artifact(decision_validation_path, artifacts.decision_validation)
        write_json_artifact(apple_health_evidence_path, artifacts.apple_health_evidence)
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

    def build_review_artifacts(
        self,
        workout_id: int,
        decisions: dict[str, Any] | None = None,
    ) -> WorkoutBackfillReviewArtifacts:
        """Render review artifacts without writing them.

        Args:
            workout_id (int): True Coach Workout id.
            decisions (dict[str, Any] | None): Optional editable decisions payload.

        Returns:
            WorkoutBackfillReviewArtifacts: Rendered plan, decisions, evidence, and report.
        """
        return self._build_artifacts(workout_id, decisions)

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
        plan = read_json_object(bundle.plan_path)
        request_data = read_json_object(bundle.request_path)
        decision_validation = read_json_object(bundle.decision_validation_path)
        decisions = read_json_object(bundle.decisions_path)
        request_body = PostWorkoutsRequestBody(**request_data)
        _validate_apply_request(
            WorkoutBackfillApplyValidationContext(
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
        plan = read_json_object(result.review_bundle.plan_path) if result.review_bundle else {}
        decisions = (
            read_json_object(result.review_bundle.decisions_path) if result.review_bundle else {}
        )
        return self._apply_service.apply(
            workout_id=workout_id,
            result=result,
            workout_writer=workout_writer,
            plan=plan,
            decisions=decisions,
        )

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
        return self._apply_service.apply_manual_request(
            request_path,
            workout_id=workout_id,
            workout_writer=workout_writer,
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
        """
        result = self.write_apply_request(workout_id, decisions_path=decisions_path)
        plan = read_json_object(result.review_bundle.plan_path) if result.review_bundle else {}
        decisions = (
            read_json_object(result.review_bundle.decisions_path) if result.review_bundle else {}
        )
        return self._apply_service.repair_local_links(
            workout_id=workout_id,
            result=result,
            workout_writer=workout_writer,
            plan=plan,
            decisions=decisions,
        )

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
            items = plan_performed_work_items(
                sorted(
                    tracker_workout.workout_items,
                    key=lambda item: (item.position, item.id),
                ),
                templates,
                _superset_ids_by_position(workout),
            )
            plan = _plan(workout, tracker_workout, items)
            apple_health_evidence = _apple_health_evidence(uow.session, workout.due)
            resolved_decisions = decisions or build_workout_backfill_decision_template(
                workout_id,
                plan,
            )
            decision_validation = validate_workout_backfill_decisions(
                workout_id,
                resolved_decisions,
                plan,
            )
            return WorkoutBackfillReviewArtifacts(
                plan=plan,
                request=build_hevy_workout_backfill_request(plan, resolved_decisions),
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


class WorkoutBackfillPipeline:
    """Artifact-first Workout backfill review and inspect pipeline."""

    def __init__(self, store: Store, output_root: Path = Path("reports")) -> None:
        """Create the pipeline.

        Args:
            store (Store): Local database snapshot.
            output_root (Path): Root under which pipeline artifacts are written.
        """
        self._review_service = TrueCoachWorkoutBackfillReviewService(
            store=store,
            output_root=output_root,
        )
        self._output_root = output_root

    def review(
        self,
        workout_id: int,
        options: WorkoutBackfillReviewOptions | None = None,
    ) -> WorkoutBackfillPipelineReview:
        """Write an artifact-first review directory for one True Coach Workout.

        Args:
            workout_id (int): True Coach Workout id.
            options (WorkoutBackfillReviewOptions | None): Regeneration options.

        Returns:
            WorkoutBackfillPipelineReview: Paths written for the review.
        """
        options = options or WorkoutBackfillReviewOptions()
        review_dir = self._output_root / PIPELINE_REVIEW_DIRNAME / str(workout_id)
        decisions_path = review_dir / "decisions.json"
        _validate_pipeline_review_write(review_dir, decisions_path, options)
        decisions = _load_pipeline_review_decisions(decisions_path, options)
        artifacts = self._review_service.build_review_artifacts(workout_id, decisions)
        review_dir.mkdir(parents=True, exist_ok=True)
        paths = _pipeline_review_paths(review_dir)
        _write_pipeline_review_artifacts(paths, workout_id, artifacts)
        return WorkoutBackfillPipelineReview(
            directory=review_dir,
            manifest_path=paths.manifest,
            plan_path=paths.plan,
            decisions_path=paths.decisions,
            decision_validation_path=paths.decision_validation,
            apple_health_evidence_path=paths.apple_health_evidence,
            report_path=paths.report,
        )

    def inspect(self, review_dir: Path) -> WorkoutBackfillInspectResult:
        """Load review status through the review manifest.

        Args:
            review_dir (Path): Existing review directory containing a manifest.

        Returns:
            WorkoutBackfillInspectResult: Manifest-backed inspect data.

        Raises:
            WorkoutBackfillReviewError: If the manifest does not list required artifacts.
        """
        manifest_path = review_dir / PIPELINE_MANIFEST_FILENAME
        manifest = read_json_object(manifest_path)
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict):
            msg = f"Review manifest {manifest_path} must contain an artifacts object"
            raise WorkoutBackfillReviewError(msg)
        plan = read_json_object(_manifest_artifact_path(review_dir, artifacts, "plan"))
        decision_validation = read_json_object(
            _manifest_artifact_path(review_dir, artifacts, "decision_validation")
        )
        return WorkoutBackfillInspectResult(
            review_dir=review_dir,
            manifest=manifest,
            plan=plan,
            decision_validation=decision_validation,
        )


def _bundle_paths(
    output_root: Path,
    workout_id: int,
) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    bundle_dir = review_bundle_dir(output_root, "truecoach-workout-backfill", workout_id)
    return (
        bundle_dir,
        bundle_dir / "plan.json",
        bundle_dir / "hevy-workout-request.json",
        bundle_dir / "apple-health-evidence.json",
        bundle_dir / "report.md",
        bundle_dir / "backfill-decisions.json",
        bundle_dir / "decision-validation.json",
    )


def _pipeline_review_paths(review_dir: Path) -> WorkoutBackfillPipelinePaths:
    return WorkoutBackfillPipelinePaths(
        manifest=review_dir / PIPELINE_MANIFEST_FILENAME,
        plan=review_dir / PIPELINE_ARTIFACT_FILENAMES["plan"],
        decisions=review_dir / PIPELINE_ARTIFACT_FILENAMES["decisions"],
        decision_validation=review_dir / PIPELINE_ARTIFACT_FILENAMES["decision_validation"],
        apple_health_evidence=review_dir / PIPELINE_ARTIFACT_FILENAMES["apple_health_evidence"],
        report=review_dir / PIPELINE_ARTIFACT_FILENAMES["report"],
    )


def _validate_pipeline_review_write(
    review_dir: Path,
    decisions_path: Path,
    options: WorkoutBackfillReviewOptions,
) -> None:
    if options.preserve_decisions and options.reset_decisions:
        msg = "--preserve-decisions and --reset-decisions cannot be combined"
        raise WorkoutBackfillReviewError(msg)
    if review_dir.exists() and not options.force:
        msg = f"Workout backfill review directory already exists: {review_dir}"
        raise WorkoutBackfillReviewError(msg)
    if (
        options.force
        and decisions_path.exists()
        and not options.preserve_decisions
        and not options.reset_decisions
    ):
        msg = (
            "Existing decisions.json found; use --preserve-decisions or "
            "--reset-decisions with --force"
        )
        raise WorkoutBackfillReviewError(msg)


def _load_pipeline_review_decisions(
    decisions_path: Path,
    options: WorkoutBackfillReviewOptions,
) -> dict[str, Any] | None:
    if options.preserve_decisions and decisions_path.exists():
        return load_decisions_file(decisions_path, error_cls=WorkoutBackfillReviewError)
    return None


def _write_pipeline_review_artifacts(
    paths: WorkoutBackfillPipelinePaths,
    workout_id: int,
    artifacts: WorkoutBackfillReviewArtifacts,
) -> None:
    _remove_request_artifacts(paths.manifest.parent)
    write_json_artifact(paths.manifest, _pipeline_review_manifest(workout_id))
    write_json_artifact(paths.plan, artifacts.plan)
    write_json_artifact(paths.decisions, artifacts.decisions)
    write_json_artifact(paths.decision_validation, artifacts.decision_validation)
    write_json_artifact(paths.apple_health_evidence, artifacts.apple_health_evidence)
    paths.report.write_text(artifacts.report, encoding="utf-8")


def _pipeline_review_manifest(workout_id: int) -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "workout-backfill-review",
        "workout_id": workout_id,
        "artifacts": dict(PIPELINE_ARTIFACT_FILENAMES),
        "request_status": "not-written",
    }


def _remove_request_artifacts(review_dir: Path) -> None:
    for filename in PIPELINE_REQUEST_FILENAMES:
        path = review_dir / filename
        if path.exists():
            path.unlink()


def _manifest_artifact_path(
    review_dir: Path,
    artifacts: dict[str, Any],
    artifact_name: str,
) -> Path:
    artifact_path = artifacts.get(artifact_name)
    if not isinstance(artifact_path, str):
        msg = f"Review manifest is missing artifact path: {artifact_name}"
        raise WorkoutBackfillReviewError(msg)
    return review_dir / artifact_path


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


def _validate_apply_request(context: WorkoutBackfillApplyValidationContext) -> None:
    blockers = workout_backfill_apply_blockers(context)
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
