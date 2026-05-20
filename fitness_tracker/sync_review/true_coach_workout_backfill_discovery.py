"""Discover completed True Coach Workouts that can be reviewed for backfill."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import distinct, func

from fitness_tracker.database import Store
from fitness_tracker.database.models.tracker import (
    Sets,
    Workout as TrackerWorkout,
    WorkoutItem as TrackerWorkoutItem,
)
from fitness_tracker.database.models.true_coach import TrueCoachWorkout

CandidateStatus = Literal["structured-results", "placeholder-or-no-results"]


@dataclass(frozen=True)
class BackfillCandidate:
    """One completed True Coach Workout that is not linked to Hevy."""

    true_coach_id: int
    due: str | None
    title: str | None
    tracker_workout_id: int | None
    workout_item_count: int
    set_count: int
    candidate_status: CandidateStatus


@dataclass(frozen=True)
class BackfillDiscoveryBundle:
    """Paths written for a backfill discovery report."""

    directory: Path
    report_path: Path
    candidates_path: Path
    manifest_path: Path
    candidate_count: int


@dataclass(frozen=True)
class BackfillCandidatesResult:
    """CLI-neutral result for Workout backfill candidate artifact generation."""

    directory: Path
    report_path: Path
    candidates_path: Path
    manifest_path: Path
    candidate_count: int


class TrueCoachWorkoutBackfillDiscoveryService:
    """Find completed, non-rest, unlinked True Coach Workouts for backfill review."""

    def __init__(self, store: Store, output_root: Path = Path("reports")) -> None:
        """Create the service.

        Args:
            store (Store): Local database snapshot.
            output_root (Path): Report root directory.
        """
        self._store = store
        self._output_root = output_root

    def discover(self) -> list[BackfillCandidate]:
        """Return completed, non-rest True Coach Workouts without a Hevy link.

        Returns:
            list[BackfillCandidate]: Candidate rows ordered by due date and id.
        """
        with self._store.unit_of_work() as uow:
            rows = (
                uow.session.query(
                    TrueCoachWorkout.id,
                    TrueCoachWorkout.due,
                    TrueCoachWorkout.title,
                    TrackerWorkout.id,
                    func.count(distinct(TrackerWorkoutItem.id)),
                    func.count(distinct(Sets.id)),
                )
                .outerjoin(TrackerWorkout, TrackerWorkout.true_coach_id == TrueCoachWorkout.id)
                .outerjoin(TrackerWorkoutItem, TrackerWorkoutItem.workout_id == TrackerWorkout.id)
                .outerjoin(Sets, Sets.workout_item_id == TrackerWorkoutItem.id)
                .filter(TrueCoachWorkout.state == "completed")
                .filter(TrueCoachWorkout.rest_day.is_(False))
                .filter(TrackerWorkout.hevy_app_id.is_(None))
                .group_by(
                    TrueCoachWorkout.id,
                    TrueCoachWorkout.due,
                    TrueCoachWorkout.title,
                    TrackerWorkout.id,
                )
                .order_by(TrueCoachWorkout.due, TrueCoachWorkout.id)
                .all()
            )

        return [
            BackfillCandidate(
                true_coach_id=row[0],
                due=row[1].isoformat() if row[1] is not None else None,
                title=row[2],
                tracker_workout_id=row[3],
                workout_item_count=row[4],
                set_count=row[5],
                candidate_status=_candidate_status(row[5]),
            )
            for row in rows
        ]

    def write_report(self) -> BackfillDiscoveryBundle:
        """Write Markdown and JSON discovery artifacts.

        Returns:
            BackfillDiscoveryBundle: Paths written by the service.
        """
        result = self.write_candidates()
        return BackfillDiscoveryBundle(
            directory=result.directory,
            report_path=result.report_path,
            candidates_path=result.candidates_path,
            manifest_path=result.manifest_path,
            candidate_count=result.candidate_count,
        )

    def write_candidates(self) -> BackfillCandidatesResult:
        """Write candidate discovery artifacts and manifest.

        Returns:
            BackfillCandidatesResult: Paths and summary data for the generated artifacts.
        """
        candidates = self.discover()
        bundle_dir = self._output_root / "workout-backfill" / "candidates"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        report_path = bundle_dir / "report.md"
        candidates_path = bundle_dir / "candidates.json"
        manifest_path = bundle_dir / "candidates-manifest.json"
        report_path.write_text(_render_report(candidates), encoding="utf-8")
        candidates_path.write_text(
            json.dumps([asdict(candidate) for candidate in candidates], indent=2) + "\n",
            encoding="utf-8",
        )
        manifest_path.write_text(
            json.dumps(_candidates_manifest(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return BackfillCandidatesResult(
            directory=bundle_dir,
            report_path=report_path,
            candidates_path=candidates_path,
            manifest_path=manifest_path,
            candidate_count=len(candidates),
        )


def _candidate_status(set_count: int) -> CandidateStatus:
    if set_count > 0:
        return "structured-results"
    return "placeholder-or-no-results"


def _render_report(candidates: list[BackfillCandidate]) -> str:
    lines = [
        "# True Coach Workout Backfill Candidates",
        "",
        "| True Coach id | Due | Title | Tracker Workout id | Workout Items | Sets | Status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        (
            "| "
            f"{candidate.true_coach_id} | "
            f"{candidate.due or 'unknown'} | "
            f"{candidate.title or 'Untitled'} | "
            f"{candidate.tracker_workout_id or 'none'} | "
            f"{candidate.workout_item_count} | "
            f"{candidate.set_count} | "
            f"{candidate.candidate_status} |"
        )
        for candidate in candidates
    )
    if not candidates:
        lines.append("| none | none | none | none | 0 | 0 | placeholder-or-no-results |")
    return "\n".join(lines) + "\n"


def _candidates_manifest() -> dict[str, object]:
    return {
        "workflow": "workout-backfill-candidates",
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "artifacts": {
            "report": "report.md",
            "candidates": "candidates.json",
        },
    }
