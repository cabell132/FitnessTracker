"""Build deterministic True Coach Workout backfill review bundles."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
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
from fitness_tracker.database.models.hevy_app import (
    HevyAppExercise,
    HevyAppSets,
    HevyAppWorkout,
    HevyAppWorkoutItem,
)
from fitness_tracker.database.models.tracker import (
    Workout as TrackerWorkout,
)
from fitness_tracker.database.models.true_coach import TrueCoachWorkout
from fitness_tracker.sync._true_coach_html import build_superset_index, parse_workout_order
from fitness_tracker.sync.ports import HevyWorkoutWriter
from fitness_tracker.sync_review.true_coach_workout_backfill_discovery import (
    BackfillCandidatesResult,
    TrueCoachWorkoutBackfillDiscoveryService,
)
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
class WorkoutBackfillPipelineRequest:
    """Request artifacts written for one Workout backfill review directory."""

    review_dir: Path
    request_path: Path
    manifest_path: Path


@dataclass(frozen=True)
class WorkoutBackfillDiffResult:
    """Manifest-verified request diff against a linked local Hevy Workout."""

    review_dir: Path
    request_path: Path
    local_hevy_workout_id: str
    differences: list[str]


@dataclass(frozen=True)
class WorkoutBackfillLinkWorkoutCommand:
    """Manifest-verified artifacts for linking an existing remote Hevy Workout."""

    review_dir: Path
    review_manifest_path: Path
    request_path: Path
    request_manifest_path: Path
    workout_id: int
    request_body: PostWorkoutsRequestBody
    plan: dict[str, Any]
    decisions: dict[str, Any]


@dataclass(frozen=True)
class WorkoutBackfillLinkWorkoutResult:
    """Result of linking an existing remote Hevy Workout from artifacts."""

    review_dir: Path
    request_path: Path
    request_body: PostWorkoutsRequestBody
    action: str


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
class WorkoutBackfillPipelineRequestPaths:
    """Artifact paths consumed and produced by the request-writing step."""

    plan: Path
    decisions: Path
    decision_validation: Path
    request: Path
    request_manifest: Path


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
    request_written: bool = False


PIPELINE_REVIEW_DIRNAME = "workout-backfill"
PIPELINE_MANIFEST_FILENAME = "review-manifest.json"
PIPELINE_REQUEST_MANIFEST_FILENAME = "request-manifest.json"
PIPELINE_REQUEST_FILENAME = "hevy-workout-request.json"
PIPELINE_REQUEST_WORKFLOW = "workout-backfill"
PIPELINE_REQUEST_SCHEMA_VERSION = 1
PIPELINE_ARTIFACT_FILENAMES = {
    "plan": "plan.json",
    "decisions": "decisions.json",
    "decision_validation": "decision-validation.json",
    "apple_health_evidence": "apple-health-evidence.json",
    "report": "report.md",
}
PIPELINE_REQUEST_FILENAMES = (PIPELINE_REQUEST_FILENAME, PIPELINE_REQUEST_MANIFEST_FILENAME)


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
        artifacts = self._build_artifacts(workout_id, decisions, request_written=True)
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
        *,
        request_written: bool = False,
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
                        request_written=request_written,
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
        self._apply_service = WorkoutBackfillApplyService(store)
        self._candidates_service = TrueCoachWorkoutBackfillDiscoveryService(
            store=store,
            output_root=output_root,
        )
        self._store = store
        self._output_root = output_root

    def candidates(self) -> BackfillCandidatesResult:
        """Write Workout backfill candidate artifacts.

        Returns:
            BackfillCandidatesResult: Paths and summary data for generated candidate artifacts.
        """
        return self._candidates_service.write_candidates()

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

    def write_request(
        self,
        review_dir: Path,
        *,
        force: bool = False,
    ) -> WorkoutBackfillPipelineRequest:
        """Write a Hevy Workout request from an existing review directory.

        Args:
            review_dir (Path): Existing artifact-first review directory.
            force (bool): Overwrite existing request artifacts even when edited.

        Returns:
            WorkoutBackfillPipelineRequest: Paths written for the request step.
        """
        manifest, manifest_path, paths = _load_pipeline_review_request_paths(review_dir)
        _validate_existing_pipeline_request(
            paths.request,
            paths.request_manifest,
            force=force,
        )

        plan = read_json_object(paths.plan)
        decisions = read_json_object(paths.decisions)
        request_body, decision_validation = _build_validated_pipeline_request(
            workout_id=manifest["workout_id"],
            plan=plan,
            decisions=decisions,
        )
        write_json_artifact(paths.decision_validation, decision_validation)
        write_json_artifact(paths.request, request_body)
        write_json_artifact(
            paths.request_manifest,
            _pipeline_request_manifest(paths),
        )
        manifest["request_status"] = "written"
        write_json_artifact(manifest_path, manifest)
        return WorkoutBackfillPipelineRequest(
            review_dir=review_dir,
            request_path=paths.request,
            manifest_path=paths.request_manifest,
        )

    def apply(
        self,
        review_dir: Path,
        *,
        workout_writer: HevyWorkoutWriter,
    ) -> WorkoutBackfillApplyResult:
        """Apply the existing manifest-verified request artifact in a review directory.

        Args:
            review_dir (Path): Existing review directory with request artifacts.
            workout_writer (HevyWorkoutWriter): Hevy Workout mutation port.

        Returns:
            WorkoutBackfillApplyResult: Apply result with the performed action.
        """
        manifest, _, paths = _load_pipeline_review_request_paths(review_dir)
        request_manifest = read_json_object(paths.request_manifest)
        _validate_pipeline_request_manifest(paths, request_manifest)
        request_body = _load_pipeline_request(paths.request)
        plan = read_json_object(paths.plan)
        decisions = read_json_object(paths.decisions)
        decision_validation = read_json_object(paths.decision_validation)
        _validate_apply_request(
            WorkoutBackfillApplyValidationContext(
                plan=plan,
                decision_validation=decision_validation,
                request_body=request_body,
                decisions=decisions,
            )
        )
        result = WorkoutBackfillApplyResult(
            review_bundle=_pipeline_apply_bundle(review_dir, paths),
            request_path=paths.request,
            request_body=request_body,
            action="pending",
        )
        return self._apply_service.apply(
            workout_id=manifest["workout_id"],
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
        """Apply an explicit request artifact outside the review-directory lifecycle.

        Args:
            request_path (Path): Hevy Workout request JSON path.
            workout_id (int): Expected source True Coach Workout id marker.
            workout_writer (HevyWorkoutWriter): Hevy Workout mutation port.

        Returns:
            WorkoutBackfillApplyResult: Apply result with the performed action.
        """
        return self._apply_service.apply_manual_request(
            request_path,
            workout_id=workout_id,
            workout_writer=workout_writer,
        )

    def link_workout(
        self,
        review_dir: Path,
        *,
        workout_writer: HevyWorkoutWriter,
    ) -> WorkoutBackfillLinkWorkoutResult:
        """Link an existing remote Hevy Workout using verified review artifacts.

        Args:
            review_dir (Path): Existing review directory with request artifacts.
            workout_writer (HevyWorkoutWriter): Workout reader/writer port.

        Returns:
            WorkoutBackfillLinkWorkoutResult: Link result and consumed request path.
        """
        command = _load_link_workout_command(review_dir)
        result = self._apply_service.repair_local_links(
            workout_id=command.workout_id,
            result=WorkoutBackfillApplyResult(
                review_bundle=None,
                request_path=command.request_path,
                request_body=command.request_body,
                action="link_workout",
            ),
            workout_writer=workout_writer,
            plan=command.plan,
            decisions=command.decisions,
        )
        return WorkoutBackfillLinkWorkoutResult(
            review_dir=command.review_dir,
            request_path=command.request_path,
            request_body=result.request_body,
            action="linked_existing_workout",
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

    def diff(self, review_dir: Path) -> WorkoutBackfillDiffResult:
        """Compare a manifest-verified request artifact to the local Hevy cache.

        Args:
            review_dir (Path): Existing review directory containing request artifacts.

        Returns:
            WorkoutBackfillDiffResult: Linked workout id and normalized differences.

        Raises:
            WorkoutBackfillReviewError: If required artifacts are missing or stale,
                or no linked local Hevy Workout exists.
        """
        manifest_path = review_dir / PIPELINE_MANIFEST_FILENAME
        manifest = read_json_object(manifest_path)
        _validate_pipeline_review_manifest(manifest, manifest_path)
        request_manifest_path = review_dir / PIPELINE_REQUEST_MANIFEST_FILENAME
        if not request_manifest_path.exists():
            msg = (
                f"Missing Workout backfill request manifest: {request_manifest_path}. "
                "Run workout-backfill write-request --review-dir <dir>."
            )
            raise WorkoutBackfillReviewError(msg)
        request_manifest = read_json_object(request_manifest_path)
        paths = _pipeline_request_paths(review_dir, manifest)
        if not paths.request.exists():
            msg = (
                f"Missing Workout backfill request artifact: {paths.request}. "
                "Run workout-backfill write-request --review-dir <dir>."
            )
            raise WorkoutBackfillReviewError(msg)
        _validate_pipeline_request_manifest(paths, request_manifest, request_manifest_path)
        request = read_json_object(paths.request)
        local = _linked_hevy_workout_snapshot(self._store, manifest["workout_id"])
        if local is None:
            msg = (
                f"No linked local Hevy Workout for True Coach Workout {manifest['workout_id']}; "
                "apply or repair the backfill before running workout-backfill diff."
            )
            raise WorkoutBackfillReviewError(msg)
        return WorkoutBackfillDiffResult(
            review_dir=review_dir,
            request_path=paths.request,
            local_hevy_workout_id=local["id"],
            differences=_workout_request_local_differences(request, local),
        )


def _bundle_paths(
    output_root: Path,
    workout_id: int,
) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    bundle_dir = output_root / "workout-backfill" / str(workout_id)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    return (
        bundle_dir,
        bundle_dir / "plan.json",
        bundle_dir / "hevy-workout-request.json",
        bundle_dir / "apple-health-evidence.json",
        bundle_dir / "report.md",
        bundle_dir / "decisions.json",
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


def _pipeline_request_paths(
    review_dir: Path,
    manifest: dict[str, Any],
) -> WorkoutBackfillPipelineRequestPaths:
    artifacts = manifest["artifacts"]
    return WorkoutBackfillPipelineRequestPaths(
        plan=_manifest_artifact_path(review_dir, artifacts, "plan"),
        decisions=_manifest_artifact_path(review_dir, artifacts, "decisions"),
        decision_validation=_manifest_artifact_path(
            review_dir,
            artifacts,
            "decision_validation",
        ),
        request=review_dir / PIPELINE_REQUEST_FILENAME,
        request_manifest=review_dir / PIPELINE_REQUEST_MANIFEST_FILENAME,
    )


def _load_pipeline_review_request_paths(
    review_dir: Path,
) -> tuple[dict[str, Any], Path, WorkoutBackfillPipelineRequestPaths]:
    manifest_path = review_dir / PIPELINE_MANIFEST_FILENAME
    manifest = read_json_object(manifest_path)
    _validate_pipeline_review_manifest(manifest, manifest_path)
    return manifest, manifest_path, _pipeline_request_paths(review_dir, manifest)


def _validate_pipeline_review_manifest(
    manifest: dict[str, Any],
    manifest_path: Path,
) -> None:
    if manifest.get("kind") != "workout-backfill-review":
        msg = f"Review manifest {manifest_path} is not a Workout backfill review"
        raise WorkoutBackfillReviewError(msg)
    if not isinstance(manifest.get("workout_id"), int):
        msg = f"Review manifest {manifest_path} must contain an integer workout_id"
        raise WorkoutBackfillReviewError(msg)
    if not isinstance(manifest.get("artifacts"), dict):
        msg = f"Review manifest {manifest_path} must contain an artifacts object"
        raise WorkoutBackfillReviewError(msg)


def _validate_existing_pipeline_request(
    request_path: Path,
    request_manifest_path: Path,
    *,
    force: bool,
) -> None:
    if force or not request_path.exists():
        return
    if not request_manifest_path.exists():
        msg = f"Existing request has no manifest: {request_manifest_path}"
        raise WorkoutBackfillReviewError(msg)
    manifest = read_json_object(request_manifest_path)
    request_hash = _request_manifest_hash(manifest, request_manifest_path)
    if _sha256_file(request_path) != request_hash:
        msg = f"Existing request has been edited; use --force to overwrite: {request_path}"
        raise WorkoutBackfillReviewError(msg)


def _request_manifest_hash(
    manifest: dict[str, Any],
    manifest_path: Path,
) -> str:
    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict):
        msg = f"Request manifest {manifest_path} is missing request hash"
        raise WorkoutBackfillReviewError(msg)
    request_hash = hashes.get("request")
    if not isinstance(request_hash, str):
        msg = f"Request manifest {manifest_path} is missing request hash"
        raise WorkoutBackfillReviewError(msg)
    return request_hash


def _validate_pipeline_request_manifest(
    paths: WorkoutBackfillPipelineRequestPaths,
    manifest: dict[str, Any],
    manifest_path: Path | None = None,
) -> None:
    manifest_path = manifest_path or paths.request_manifest
    _validate_pipeline_request_manifest_header(manifest, manifest_path)
    _validate_pipeline_request_manifest_artifacts(paths, manifest, manifest_path)
    _validate_pipeline_request_manifest_hashes(paths, manifest, manifest_path)


def _load_link_workout_command(review_dir: Path) -> WorkoutBackfillLinkWorkoutCommand:
    review_manifest_path = review_dir / PIPELINE_MANIFEST_FILENAME
    request_manifest_path = review_dir / PIPELINE_REQUEST_MANIFEST_FILENAME
    manifest = read_json_object(review_manifest_path)
    _validate_pipeline_review_manifest(manifest, review_manifest_path)
    paths = _pipeline_request_paths(review_dir, manifest)
    request_manifest = read_json_object(request_manifest_path)
    _validate_pipeline_request_manifest(paths, request_manifest, request_manifest_path)
    plan = read_json_object(paths.plan)
    decisions = read_json_object(paths.decisions)
    decision_validation = read_json_object(paths.decision_validation)
    request_body = _load_pipeline_request(paths.request)
    _validate_apply_request(
        WorkoutBackfillApplyValidationContext(
            plan=plan,
            decision_validation=decision_validation,
            request_body=request_body,
            decisions=decisions,
        )
    )
    return WorkoutBackfillLinkWorkoutCommand(
        review_dir=review_dir,
        review_manifest_path=review_manifest_path,
        request_path=paths.request,
        request_manifest_path=request_manifest_path,
        workout_id=manifest["workout_id"],
        request_body=request_body,
        plan=plan,
        decisions=decisions,
    )


def _validate_pipeline_request_manifest_header(
    manifest: dict[str, Any],
    manifest_path: Path,
) -> None:
    if manifest.get("workflow") != PIPELINE_REQUEST_WORKFLOW:
        msg = f"Request manifest {manifest_path} is not a Workout backfill request"
        raise WorkoutBackfillReviewError(msg)
    if manifest.get("schema_version") != PIPELINE_REQUEST_SCHEMA_VERSION:
        msg = f"Request manifest {manifest_path} has unsupported schema_version"
        raise WorkoutBackfillReviewError(msg)


def _validate_pipeline_request_manifest_artifacts(
    paths: WorkoutBackfillPipelineRequestPaths,
    manifest: dict[str, Any],
    manifest_path: Path,
) -> None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        msg = f"Request manifest {manifest_path} must contain an artifacts object"
        raise WorkoutBackfillReviewError(msg)
    if artifacts != _expected_pipeline_request_artifacts(paths):
        msg = f"Request manifest {manifest_path} does not match review artifacts"
        raise WorkoutBackfillReviewError(msg)


def _validate_pipeline_request_manifest_hashes(
    paths: WorkoutBackfillPipelineRequestPaths,
    manifest: dict[str, Any],
    manifest_path: Path,
) -> None:
    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict):
        msg = (
            f"Request manifest {manifest_path} is missing artifact hashes; "
            "run workout-backfill write-request --review-dir <dir>."
        )
        raise WorkoutBackfillReviewError(msg)
    for artifact_name, artifact_path in _expected_pipeline_request_paths(paths).items():
        expected_hash = hashes.get(artifact_name)
        if not isinstance(expected_hash, str):
            msg = (
                f"Request manifest {manifest_path} is missing {artifact_name} hash; "
                "run workout-backfill write-request --review-dir <dir>."
            )
            raise WorkoutBackfillReviewError(msg)
        if _sha256_file(artifact_path) != expected_hash:
            if artifact_name == "request":
                msg = (
                    f"Request artifact hash mismatch: {artifact_path}. "
                    "Run workout-backfill write-request --review-dir <dir> --force "
                    "to regenerate it, or use the manual workflow for edited requests."
                )
            else:
                msg = (
                    f"Request artifact is stale because {artifact_name} changed: "
                    f"{artifact_path}. Run workout-backfill write-request --review-dir <dir>."
                )
            raise WorkoutBackfillReviewError(msg)


def _expected_pipeline_request_artifacts(
    paths: WorkoutBackfillPipelineRequestPaths,
) -> dict[str, str]:
    return _pipeline_request_artifacts(paths)


def _expected_pipeline_request_paths(
    paths: WorkoutBackfillPipelineRequestPaths,
) -> dict[str, Path]:
    return _pipeline_request_artifact_paths(paths)


def _load_pipeline_request(request_path: Path) -> PostWorkoutsRequestBody:
    request_data = read_json_object(request_path)
    try:
        return PostWorkoutsRequestBody(**request_data)
    except ValueError as exc:
        msg = f"Invalid Hevy Workout request file {request_path}: {exc}"
        raise WorkoutBackfillApplyError(msg) from exc


def _pipeline_apply_bundle(
    review_dir: Path,
    paths: WorkoutBackfillPipelineRequestPaths,
) -> WorkoutBackfillReviewBundle:
    return WorkoutBackfillReviewBundle(
        directory=review_dir,
        report_path=review_dir / PIPELINE_ARTIFACT_FILENAMES["report"],
        plan_path=paths.plan,
        request_path=paths.request,
        apple_health_evidence_path=review_dir
        / PIPELINE_ARTIFACT_FILENAMES["apple_health_evidence"],
        decisions_path=paths.decisions,
        decision_validation_path=paths.decision_validation,
    )


def _build_validated_pipeline_request(
    *,
    workout_id: int,
    plan: dict[str, Any],
    decisions: dict[str, Any],
) -> tuple[PostWorkoutsRequestBody, dict[str, list[str]]]:
    decision_validation = validate_workout_backfill_decisions(
        workout_id,
        decisions,
        plan,
    )
    request_body = build_hevy_workout_backfill_request(plan, decisions)
    _validate_apply_request(
        WorkoutBackfillApplyValidationContext(
            plan=plan,
            decision_validation=decision_validation,
            request_body=request_body,
            decisions=decisions,
        )
    )
    return request_body, decision_validation


def _pipeline_request_manifest(
    paths: WorkoutBackfillPipelineRequestPaths,
) -> dict[str, Any]:
    return {
        "workflow": PIPELINE_REQUEST_WORKFLOW,
        "schema_version": PIPELINE_REQUEST_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "artifacts": _pipeline_request_artifacts(paths),
        "sha256": {
            name: _sha256_file(path)
            for name, path in _pipeline_request_artifact_paths(paths).items()
        },
    }


def _pipeline_request_artifacts(paths: WorkoutBackfillPipelineRequestPaths) -> dict[str, str]:
    return {name: path.name for name, path in _pipeline_request_artifact_paths(paths).items()}


def _pipeline_request_artifact_paths(
    paths: WorkoutBackfillPipelineRequestPaths,
) -> dict[str, Path]:
    return {
        "plan": paths.plan,
        "decisions": paths.decisions,
        "decision_validation": paths.decision_validation,
        "request": paths.request,
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _linked_hevy_workout_snapshot(
    store: Store,
    true_coach_workout_id: int,
) -> dict[str, Any] | None:
    with store.unit_of_work() as uow:
        tracker_workout = (
            uow.session.query(TrackerWorkout)
            .filter_by(true_coach_id=true_coach_workout_id)
            .one_or_none()
        )
        if tracker_workout is None or tracker_workout.hevy_app_id is None:
            return None
        hevy_workout = (
            uow.session.query(HevyAppWorkout)
            .filter_by(id=tracker_workout.hevy_app_id)
            .one_or_none()
        )
        if hevy_workout is None:
            return None
        exercises = (
            uow.session.query(HevyAppWorkoutItem)
            .filter_by(workout_id=hevy_workout.id)
            .order_by(HevyAppWorkoutItem.index)
            .all()
        )
        sets_by_item: dict[int, list[dict[str, Any]]] = {}
        if exercises:
            exercise_ids = [exercise.id for exercise in exercises]
            set_rows = (
                uow.session.query(HevyAppSets)
                .filter(HevyAppSets.workout_item_id.in_(exercise_ids))
                .order_by(HevyAppSets.workout_item_id, HevyAppSets.index)
                .all()
            )
            for set_row in set_rows:
                sets_by_item.setdefault(set_row.workout_item_id, []).append(
                    {
                        "id": set_row.id,
                        "workout_item_id": set_row.workout_item_id,
                        "index": set_row.index,
                        "type": set_row.type,
                        "weight_kg": set_row.weight_kg,
                        "reps": set_row.reps,
                        "distance_meters": set_row.distance_meters,
                        "duration_seconds": set_row.duration_seconds,
                        "rpe": set_row.rpe,
                    }
                )
        return {
            "id": hevy_workout.id,
            "title": hevy_workout.title,
            "description": hevy_workout.description,
            "start_time": _local_datetime_isoformat(hevy_workout.start_time),
            "end_time": _local_datetime_isoformat(hevy_workout.end_time),
            "exercises": [
                {
                    "id": exercise.id,
                    "index": exercise.index,
                    "name": exercise.name,
                    "notes": exercise.notes,
                    "superset_id": exercise.superset_id,
                    "exercise_template_id": exercise.exercise_id,
                    "sets": sets_by_item.get(exercise.id, []),
                }
                for exercise in exercises
            ],
        }


def _local_datetime_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _workout_request_local_differences(
    request: dict[str, Any],
    local: dict[str, Any],
) -> list[str]:
    workout = request.get("workout", {})
    differences: list[str] = []
    for label in ("title", "description", "start_time", "end_time"):
        request_value = workout.get(label)
        local_value = local.get(label)
        if request_value != local_value:
            differences.append(f"{label} request={request_value!r} local={local_value!r}")
    request_exercises = workout.get("exercises", [])
    local_exercises = local.get("exercises", [])
    if len(request_exercises) != len(local_exercises):
        differences.append(
            f"exercise count request={len(request_exercises)} local={len(local_exercises)}"
        )
    for index, request_exercise in enumerate(request_exercises):
        if index >= len(local_exercises):
            differences.append(f"exercise {index + 1} missing locally")
            continue
        differences.extend(
            _workout_exercise_differences(
                index + 1,
                request_exercise,
                local_exercises[index],
            )
        )
    return differences


def _workout_exercise_differences(
    position: int,
    request_exercise: dict[str, Any],
    local_exercise: dict[str, Any],
) -> list[str]:
    differences: list[str] = []
    comparisons = (
        (
            "template",
            request_exercise.get("exercise_template_id"),
            local_exercise.get("exercise_template_id"),
        ),
        ("superset", request_exercise.get("superset_id"), local_exercise.get("superset_id")),
        ("notes", request_exercise.get("notes") or "", local_exercise.get("notes") or ""),
    )
    for label, request_value, local_value in comparisons:
        if request_value != local_value:
            differences.append(
                f"exercise {position} {label} request={request_value!r} local={local_value!r}"
            )
    request_sets = request_exercise.get("sets") or []
    local_sets = local_exercise.get("sets") or []
    if len(request_sets) != len(local_sets):
        differences.append(
            f"exercise {position} set count request={len(request_sets)} local={len(local_sets)}"
        )
    return differences


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
    request_line = (
        "Hevy Workout request: hevy-workout-request.json"
        if context.request_written
        else "Hevy Workout request: not written; run workout-backfill write-request --review-dir <dir>"
    )
    lines = [
        f"# True Coach Workout Backfill Review: {workout.id}",
        "",
        f"Workout: {workout.title or 'Untitled'}",
        f"Due: {workout.due.isoformat() if workout.due else 'unknown'}",
        request_line,
        "Editable decisions: decisions.json",
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
