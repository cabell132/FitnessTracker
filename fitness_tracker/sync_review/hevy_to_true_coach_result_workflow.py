"""Strict automatic Hevy to True Coach result sync workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fitness_tracker.database import Store
from fitness_tracker.sync.ports.true_coach_workout_item_writer import TrueCoachWorkoutItemWriter
from fitness_tracker.sync_review.hevy_to_true_coach_result import (
    HevyToTrueCoachResultApplyResult,
    HevyToTrueCoachResultReviewBundle,
    HevyToTrueCoachResultReviewService,
)
from fitness_tracker.sync_review.workflow import read_json_object


@dataclass(frozen=True)
class HevyToTrueCoachResultSyncWorkflowResult:
    """Outcome of one strict automatic Result sync attempt."""

    status: str
    review_bundle: HevyToTrueCoachResultReviewBundle
    apply_result: HevyToTrueCoachResultApplyResult | None = None
    reasons: list[str] = field(default_factory=list)
    plan_warnings: list[str] = field(default_factory=list)
    item_warnings: list[str] = field(default_factory=list)
    item_blockers: list[str] = field(default_factory=list)
    decision_blockers: list[str] = field(default_factory=list)
    decision_warnings: list[str] = field(default_factory=list)


class HevyToTrueCoachResultSyncWorkflow:
    """Safely sync one performed Hevy Workout to True Coach results."""

    def __init__(self, store: Store, output_root: Path = Path("reports")) -> None:
        """Create a strict Result sync workflow.

        Args:
            store (Store): Local database snapshot.
            output_root (Path): Root under which result sync review artifacts are written.
        """
        self._review_service = HevyToTrueCoachResultReviewService(
            store=store,
            output_root=output_root,
        )

    def sync_one(
        self,
        hevy_workout_id: str,
        *,
        workout_item_writer: TrueCoachWorkoutItemWriter,
        decisions_path: Path | None = None,
    ) -> HevyToTrueCoachResultSyncWorkflowResult:
        """Write review artifacts and auto-apply only strict-safe result sync plans.

        Args:
            hevy_workout_id (str): Hevy Workout primary key to sync.
            workout_item_writer (TrueCoachWorkoutItemWriter): True Coach mutation port.
            decisions_path (Path | None): Optional editable decisions JSON to validate.

        Returns:
            HevyToTrueCoachResultSyncWorkflowResult: Applied or review-required outcome.
        """
        bundle = self._review_service.write_review(hevy_workout_id, decisions_path=decisions_path)
        strict_safety = _strict_safety(
            read_json_object(bundle.plan_path),
            read_json_object(bundle.decision_validation_path),
        )
        if strict_safety.reasons:
            return HevyToTrueCoachResultSyncWorkflowResult(
                status="review_required",
                review_bundle=bundle,
                reasons=strict_safety.reasons,
                plan_warnings=strict_safety.plan_warnings,
                item_warnings=strict_safety.item_warnings,
                item_blockers=strict_safety.item_blockers,
                decision_blockers=strict_safety.decision_blockers,
                decision_warnings=strict_safety.decision_warnings,
            )
        apply_result = self._review_service.apply(
            hevy_workout_id,
            workout_item_writer=workout_item_writer,
            decisions_path=bundle.decisions_path,
        )
        return HevyToTrueCoachResultSyncWorkflowResult(
            status="applied",
            review_bundle=apply_result.review_bundle,
            apply_result=apply_result,
        )


@dataclass(frozen=True)
class _StrictSafety:
    reasons: list[str]
    plan_warnings: list[str]
    item_warnings: list[str]
    item_blockers: list[str]
    decision_blockers: list[str]
    decision_warnings: list[str]


def _strict_safety(plan: dict[str, Any], validation: dict[str, Any]) -> _StrictSafety:
    plan_warnings = [str(warning) for warning in plan.get("warnings", [])]
    item_warnings = [
        str(warning) for item in plan.get("items", []) for warning in item.get("warnings", [])
    ]
    item_blockers = [
        str(blocker) for item in plan.get("items", []) for blocker in item.get("blockers", [])
    ]
    decision_blockers = [str(blocker) for blocker in validation.get("blockers", [])]
    decision_warnings = [str(warning) for warning in validation.get("warnings", [])]
    reasons = []
    if plan_warnings:
        reasons.append("plan_warnings")
    if item_warnings:
        reasons.append("item_warnings")
    if item_blockers:
        reasons.append("item_blockers")
    if decision_blockers:
        reasons.append("decision_blockers")
    return _StrictSafety(
        reasons=reasons,
        plan_warnings=plan_warnings,
        item_warnings=item_warnings,
        item_blockers=item_blockers,
        decision_blockers=decision_blockers,
        decision_warnings=decision_warnings,
    )
