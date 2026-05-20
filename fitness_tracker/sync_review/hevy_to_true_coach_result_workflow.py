"""Strict automatic Hevy to True Coach result sync workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from fitness_tracker.database import Store
from fitness_tracker.sync.ports.true_coach_workout_item_writer import TrueCoachWorkoutItemWriter
from fitness_tracker.sync_review.hevy_to_true_coach_result import (
    HevyToTrueCoachResultApplyResult,
    HevyToTrueCoachResultReviewBundle,
    HevyToTrueCoachResultReviewService,
)
from fitness_tracker.sync_review.workflow import read_json_object

_PLAN_WARNINGS = "plan_warnings"
_ITEM_WARNINGS = "item_warnings"
_ITEM_BLOCKERS = "item_blockers"
_DECISION_BLOCKERS = "decision_blockers"

_STRICT_REVIEW_REASONS = (
    _PLAN_WARNINGS,
    _ITEM_WARNINGS,
    _ITEM_BLOCKERS,
    _DECISION_BLOCKERS,
)

type HevyToTrueCoachResultSyncWorkflowStatus = Literal["applied", "review_required"]


@dataclass(frozen=True)
class HevyToTrueCoachResultSyncWorkflowResult:
    """Outcome of one strict automatic Result sync attempt."""

    status: HevyToTrueCoachResultSyncWorkflowStatus
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
        if strict_safety.requires_review:
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

    @property
    def requires_review(self) -> bool:
        return bool(self.reasons)


def _strict_safety(plan: dict[str, Any], validation: dict[str, Any]) -> _StrictSafety:
    plan_warnings = _messages_from(plan.get("warnings", []))
    item_warnings = _item_messages_from(plan, "warnings")
    item_blockers = _item_messages_from(plan, "blockers")
    decision_blockers = _messages_from(validation.get("blockers", []))
    decision_warnings = _messages_from(validation.get("warnings", []))
    reasons = _review_reasons(
        {
            _PLAN_WARNINGS: plan_warnings,
            _ITEM_WARNINGS: item_warnings,
            _ITEM_BLOCKERS: item_blockers,
            _DECISION_BLOCKERS: decision_blockers,
        }
    )
    return _StrictSafety(
        reasons=reasons,
        plan_warnings=plan_warnings,
        item_warnings=item_warnings,
        item_blockers=item_blockers,
        decision_blockers=decision_blockers,
        decision_warnings=decision_warnings,
    )


def _messages_from(messages: Any) -> list[str]:
    return [str(message) for message in messages]


def _item_messages_from(plan: dict[str, Any], key: str) -> list[str]:
    return [str(message) for item in plan.get("items", []) for message in item.get(key, [])]


def _review_reasons(messages_by_reason: dict[str, list[str]]) -> list[str]:
    return [reason for reason in _STRICT_REVIEW_REASONS if messages_by_reason[reason]]
