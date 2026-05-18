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
from fitness_tracker.database.models.hevy_app import HevyAppExercise
from fitness_tracker.database.models.tracker import Sets, Workout as TrackerWorkout
from fitness_tracker.database.models.true_coach import TrueCoachWorkout
from fitness_tracker.sync.ports import HevyWorkoutWriter


class WorkoutBackfillReviewError(Exception):
    """Raised when a Workout backfill review cannot be produced."""


class WorkoutBackfillApplyError(Exception):
    """Raised when a Workout backfill request is not safe to apply."""


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
    name: str
    info: str
    comment: str
    selected_hevy_template: HevyAppExercise | None
    sets: list[PostWorkoutsRequestSet]
    notes: str
    warnings: list[str]
    blockers: list[str]


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
        request_body = PostWorkoutsRequestBody(**request_data)
        _validate_apply_request(plan, decision_validation, request_body)
        return WorkoutBackfillApplyResult(
            review_bundle=bundle,
            request_path=bundle.request_path,
            request_body=request_body,
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
        workout_writer.create_workout(result.request_body)
        return result

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

            items = [
                _review_item(item)
                for item in sorted(
                    tracker_workout.workout_items,
                    key=lambda item: (item.position, item.id),
                )
            ]
            plan = _plan(workout, tracker_workout, items)
            apple_health_evidence = _apple_health_evidence(uow.session, workout.due)
            resolved_decisions = decisions or _decision_template(workout_id)
            decision_validation = _validate_decisions(workout_id, resolved_decisions)
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


def _review_item(item: Any) -> BackfillReviewItem:
    true_coach_item = item.true_coach
    template = item.exercise.hevy_app if item.exercise is not None else None
    sets = [
        _set_to_request_set(set_row) for set_row in sorted(item.sets, key=lambda row: row.index)
    ]
    info = true_coach_item.info or "" if true_coach_item is not None else ""
    comment = true_coach_item.comment or "" if true_coach_item is not None else ""
    name = true_coach_item.name if true_coach_item is not None else item.exercise.name
    if not sets and _is_down_regulate_item(name):
        sets = [PostWorkoutsRequestSet(type="normal", duration_seconds=240)]
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
    return BackfillReviewItem(
        source_id=true_coach_item.id if true_coach_item is not None else None,
        tracker_workout_item_id=item.id,
        position=item.position,
        name=name,
        info=info,
        comment=comment,
        selected_hevy_template=template if isinstance(template, HevyAppExercise) else None,
        sets=sets,
        notes=_notes(
            info=info,
            comment=comment,
            sets=sets,
        ),
        warnings=warnings,
        blockers=blockers,
    )


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
    if comment and not _comment_duplicates_structured_sets(comment, sets):
        parts.append(f"Athlete comment: {comment}")
    return "\n".join(parts)


def _comment_duplicates_structured_sets(
    comment: str,
    sets: list[PostWorkoutsRequestSet],
) -> bool:
    if not sets:
        return False
    normalized_comment = _normalize_metric_text(comment)
    if not normalized_comment:
        return False
    structured_tokens = [_set_metric_token(set_row) for set_row in sets]
    return bool(structured_tokens) and normalized_comment == _normalize_metric_text(
        ", ".join(token for token in structured_tokens if token)
    )


def _set_metric_token(set_row: PostWorkoutsRequestSet) -> str:
    parts = []
    if set_row.weight_kg is not None:
        parts.append(f"{set_row.weight_kg:g}kg")
    if set_row.reps is not None:
        parts.append(f"x {set_row.reps:g}")
    if set_row.distance_meters is not None:
        parts.append(f"{set_row.distance_meters:g}m")
    if set_row.duration_seconds is not None:
        parts.append(f"{set_row.duration_seconds:g}s")
    if set_row.rpe is not None:
        parts.append(f"rpe {set_row.rpe:g}")
    return " ".join(parts)


def _normalize_metric_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace(" x ", " x ")).strip()


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
    return {
        "source_id": item.source_id,
        "tracker_workout_item_id": item.tracker_workout_item_id,
        "position": item.position,
        "name": item.name,
        "info": item.info,
        "comment": item.comment,
        "selected_hevy_template": _template_to_dict(item.selected_hevy_template),
        "sets": [_set_to_dict(set_row) for set_row in item.sets],
        "notes": item.notes,
        "warnings": item.warnings,
        "blockers": item.blockers,
    }


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


def _decision_template(workout_id: int) -> dict[str, Any]:
    return {
        "version": 1,
        "workout": {
            "id": workout_id,
            "selected_start_time": None,
            "selected_end_time": None,
        },
    }


def _validate_decisions(workout_id: int, decisions: dict[str, Any]) -> dict[str, list[str]]:
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
    return {"blockers": blockers, "warnings": warnings}


def _build_hevy_workout_request(
    plan: dict[str, Any],
    decisions: dict[str, Any] | None = None,
) -> PostWorkoutsRequestBody:
    workout = plan["workout"]
    due = workout.get("due")
    due_date = due[:10] if isinstance(due, str) and len(due) >= 10 else "undated"
    workout_decisions = decisions.get("workout", {}) if decisions is not None else {}
    return PostWorkoutsRequestBody.build(
        title=f"{due_date} {workout.get('title') or 'Untitled'}",
        description=f"Backfill from True Coach Workout {workout['id']}",
        start_time=workout_decisions.get("selected_start_time"),
        end_time=workout_decisions.get("selected_end_time"),
        exercises=[
            _request_exercise(item)
            for item in plan["items"]
            if item["selected_hevy_template"] is not None and item["sets"]
        ],
    )


def _request_exercise(item: dict[str, Any]) -> PostWorkoutsRequestExercise:
    return PostWorkoutsRequestExercise(
        exercise_template_id=item["selected_hevy_template"]["id"],
        notes=item["notes"] or None,
        sets=[PostWorkoutsRequestSet(**set_row) for set_row in item["sets"]],
    )


def _validate_apply_request(
    plan: dict[str, Any],
    decision_validation: dict[str, list[str]],
    request_body: PostWorkoutsRequestBody,
) -> None:
    blockers = [*plan.get("blockers", []), *decision_validation.get("blockers", [])]
    workout = request_body.workout
    if not workout.start_time or not workout.end_time:
        blocker = "Missing required decision: selected Workout timestamps"
        if blocker not in blockers:
            blockers.append(blocker)
    blockers.extend(
        f"Missing Hevy template mapping for performed item: {item['name']}"
        for item in plan.get("items", [])
        if item.get("sets") and item.get("selected_hevy_template") is None
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
            AppleHealthDataType.name == "Heart Rate",
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
        summary = _heart_rate_summary(context.heart_rates, workout)
        if workout.start_date.date() != context.due.date():
            continue
        if summary is not None and summary["max_bpm"] >= 120:
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
    lines = [
        f"## {index}. {item['name']}",
        "",
        f"True Coach Workout Item: {item['source_id'] or 'none'}",
        f"Tracker WorkoutItem: {item['tracker_workout_item_id']}",
        f"Coach prescription: {item['info'] or 'none'}",
        f"Athlete comment: {item['comment'] or 'none'}",
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
