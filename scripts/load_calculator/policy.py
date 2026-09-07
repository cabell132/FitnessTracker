"""Deterministic policy experiments over interpreted, prior-date evidence."""

from dataclasses import dataclass
from datetime import timedelta

from scripts.load_calculator.equipment import canonical_load, step
from scripts.load_calculator.models import (
    Calculation,
    CandidateEffort,
    Performance,
    Prescription,
    Recommendation,
)


def _signature(prescription: Prescription) -> tuple:
    return (
        prescription.structure,
        tuple((e.round, e.part, e.lower_reps, e.upper_reps) for e in prescription.efforts),
    )


def _complete(performance: Performance, *, upper: bool = False) -> bool:
    return all(
        r.reps >= (e.upper_reps if upper else e.lower_reps)
        for r, e in zip(performance.results, performance.prescription.efforts, strict=True)
    )


def _substantial(performance: Performance) -> bool:
    return any(
        r.reps < e.lower_reps if i == 0 else r.reps <= e.lower_reps - 2
        for i, (r, e) in enumerate(
            zip(performance.results, performance.prescription.efforts, strict=True)
        )
    )


def _structure_issue(prescription: Prescription) -> str | None:
    efforts = prescription.efforts
    if prescription.structure == "unsupported" or any(e.lower_reps is None for e in efforts):
        return "unsupported_or_open_ended_prescription"
    if prescription.structure == "straight" and (
        len({(e.lower_reps, e.upper_reps) for e in efforts}) != 1
        or any(e.part != 0 for e in efforts)
    ):
        return "straight_structure_conflict"
    if prescription.structure == "drop":
        rounds = list(dict.fromkeys(e.round for e in efforts))
        expected = [(r, p) for r in rounds for p in (0, 1)]
        if [(e.round, e.part) for e in efforts] != expected:
            return "only_two_part_drop_policy_is_agreed"
    return None


@dataclass
class _Evaluation:
    request: Calculation
    history: tuple[Performance, ...]
    provisional: bool = False

    def result(
        self,
        reason: str,
        *,
        loads: tuple[float | None, ...] | None = None,
        unresolved: tuple[str, ...] = (),
    ) -> Recommendation:
        weights = loads or (None,) * len(self.request.prescription.efforts)
        labels = {o.weight_kg: o.label for o in self.request.equipment.options}
        candidates = tuple(
            CandidateEffort(
                effort=e,
                weight_kg=e.coach_load_kg if e.coach_load_kg is not None else w,
                equipment_label=labels.get(e.coach_load_kg if e.coach_load_kg is not None else w),
                source="coach"
                if e.coach_load_kg is not None
                else ("policy" if w is not None else "unresolved"),
            )
            for e, w in zip(self.request.prescription.efforts, weights, strict=True)
        )
        return Recommendation(
            request=self.request,
            efforts=candidates,
            evidence_ids=tuple(h.evidence_id for h in self.history),
            reason=reason,
            explanation=_EXPLANATIONS[reason],
            provisional=self.provisional,
            unresolved=tuple(
                dict.fromkeys(
                    (
                        *unresolved,
                        *(issue for h in self.history if (issue := self.evidence_issue(h))),
                    )
                )
            ),
        )

    def profile(self, performance: Performance) -> tuple[float | None, ...]:
        return tuple(
            canonical_load(self.request.equipment, r.recorded_kg) for r in performance.results
        )

    def evidence_issue(self, performance: Performance) -> str | None:
        if performance.conditions != "normal":
            return f"{performance.evidence_id}:conditions_{performance.conditions}"
        expected = [(e.round, e.part) for e in performance.prescription.efforts]
        if [(r.round, r.part) for r in performance.results] != expected or any(
            r.reps is None or r.recorded_kg is None for r in performance.results
        ):
            return f"{performance.evidence_id}:incomplete_or_reordered_results"
        if None in self.profile(performance):
            return f"{performance.evidence_id}:unmapped_equipment_load"
        return _structure_issue(performance.prescription)

    def run(self) -> Recommendation:
        prescription = self.request.prescription
        if any(e.coach_load_kg is not None for e in prescription.efforts):
            self.history = ()
            self.provisional = False
            unresolved = (
                ()
                if all(e.coach_load_kg is not None for e in prescription.efforts)
                else ("partially_explicit_loads_require_review",)
            )
            return self.result("coach", unresolved=unresolved)
        issue = _structure_issue(prescription)
        if issue or self.request.context.role == "unknown":
            return self.result("unresolved", unresolved=(issue or "unknown_role",))
        if not self.history:
            return self.result("unresolved", unresolved=("no_same_exercise_setup_role_history",))
        return self.from_history()

    def from_history(self) -> Recommendation:
        dates = [h.performed_on for h in self.history]
        if len(set(dates)) != len(dates):
            return self.result("unresolved", unresolved=("same_date_exposure_order_unknown",))
        latest = self.history[-1]
        issue = self.evidence_issue(latest)
        if issue:
            return self.result("unresolved", unresolved=(issue,))
        if _signature(latest.prescription) != _signature(self.request.prescription):
            return self.result("unresolved", unresolved=("changed_prescription_model_unvalidated",))
        if (
            self.request.context.role == "working"
            and self.request.prescription.structure == "straight"
            and len(set(self.profile(latest))) != 1
        ):
            return self.result("unresolved", unresolved=("straight_loads_not_shared",))
        if self.provisional:
            return self.result("stale", loads=self.profile(latest), unresolved=("stale_history",))
        return self.working()

    def working(self) -> Recommendation:
        if self.request.context.role == "preparatory":
            return self.result(
                "preparatory",
                loads=self.profile(self.history[-1]),
                unresolved=("preparatory_exposure_count_and_calendar_boundary_undecided",),
            )
        structure = self.request.prescription.structure
        if structure == "ladder":
            return self.result(
                "hold",
                loads=self.profile(self.history[-1]),
                unresolved=("ladder_progression_policy_undecided",),
            )
        if structure == "drop":
            return self.drop()
        return self.straight()

    def stepped(self, *, increase: bool) -> Recommendation:
        loads = tuple(
            step(self.request.equipment, w, increase=increase)
            for w in self.profile(self.history[-1])
        )
        if None in loads:
            return self.result("unresolved", unresolved=("equipment_step_unconfirmed",))
        return self.result("progress" if increase else "reduce", loads=loads)

    def previous(self) -> Performance | None:
        if len(self.history) < 2:
            return None
        previous = self.history[-2]
        if self.evidence_issue(previous) or (
            _signature(previous.prescription) != _signature(self.request.prescription)
        ):
            return None
        return previous

    def new_increase(self, previous: Performance) -> bool:
        next_loads = tuple(
            step(self.request.equipment, w, increase=True) for w in self.profile(previous)
        )
        return _complete(previous, upper=True) and next_loads == self.profile(self.history[-1])

    def straight(self) -> Recommendation:
        latest = self.history[-1]
        if _complete(latest, upper=True):
            return self.stepped(increase=True)
        previous = self.previous()
        if _substantial(latest) and previous is not None:
            if self.new_increase(previous):
                return self.result("rollback", loads=self.profile(previous))
            if self.profile(latest) == self.profile(previous) and _substantial(previous):
                return self.stepped(increase=False)
        return self.result("hold", loads=self.profile(latest))

    def drop(self) -> Recommendation:
        latest = self.history[-1]
        profile = self.profile(latest)
        parts = {
            p: {w for e, w in zip(latest.prescription.efforts, profile, strict=True) if e.part == p}
            for p in (0, 1)
        }
        first, second = profile[:2]
        if (
            any(len(weights) != 1 for weights in parts.values())
            or first is None
            or second is None
            or first <= second
        ):
            return self.result(
                "unresolved", unresolved=("drop_load_profile_not_repeated_descending",)
            )
        previous = self.previous()
        if _complete(latest, upper=True):
            retry = self.staged_retry(previous) if previous is not None else None
            if retry is not None:
                return retry
            return self.stepped(increase=True)
        if self.first_efforts_complete(latest):
            if previous is not None and self.new_increase(previous):
                loads = tuple(
                    w if e.part == 0 else old
                    for e, w, old in zip(
                        latest.prescription.efforts, profile, self.profile(previous), strict=True
                    )
                )
                return self.result("rollback_drop", loads=loads)
            return self.result("hold", loads=profile)
        return self.result("unresolved", unresolved=("drop_failure_combination_undecided",))

    def first_efforts_complete(self, performance: Performance) -> bool:
        return all(
            r.reps >= e.upper_reps
            for e, r in zip(performance.prescription.efforts, performance.results, strict=True)
            if e.part == 0
        )

    def staged_retry(self, previous: Performance) -> Recommendation | None:
        if _complete(previous, upper=True) or not self.first_efforts_complete(previous):
            return None
        current = self.profile(self.history[-1])
        failed = self.profile(previous)
        if not all(
            old == new if e.part == 0 else step(self.request.equipment, new, increase=True) == old
            for e, old, new in zip(self.request.prescription.efforts, failed, current, strict=True)
        ):
            return None
        if not self.confirmed_drop_origin(previous):
            return self.result("unresolved", unresolved=("staged_drop_origin_unresolved",))
        return self.result("retry_drop", loads=failed)

    def confirmed_drop_origin(self, previous: Performance) -> bool:
        if len(self.history) < 3:
            return False
        original = self.history[-3]
        if (
            self.evidence_issue(original)
            or _signature(original.prescription) != _signature(previous.prescription)
            or not _complete(original, upper=True)
        ):
            return False
        expected = tuple(
            step(self.request.equipment, w, increase=True) for w in self.profile(original)
        )
        return self.profile(previous) == expected


_EXPLANATIONS = {
    "coach": "Explicit Coach loads take precedence; unfilled efforts need separate review.",
    "unresolved": "Evidence or an agreed rule is missing; no generated load is selected.",
    "stale": "Latest same-prescription load is a provisional starting point from stale history.",
    "preparatory": "Preserve the preparatory sequence while exposure and calendar rules remain undecided.",
    "hold": "Retain the latest load profile while building prescribed reps.",
    "progress": "Every effort reached its upper bound; increase by one confirmed equipment step.",
    "reduce": "Two consecutive comparable substantial shortfalls at this weight; reduce one step.",
    "rollback": "The new equipment step produced a substantial shortfall; restore the successful load.",
    "rollback_drop": "First efforts succeeded at the new step; restore only the failed drop loads.",
    "retry_drop": "The whole staged sequence succeeded; retry the previously failed drop increase.",
}


def calculate(request: Calculation) -> Recommendation:
    """Evaluate agreed policies without fitting a model or applying remote changes.

    Args:
        request (Calculation): Validated Agent-interpreted prescription and evidence.

    Returns:
        Recommendation: Per-effort candidates, cited evidence, and unresolved decisions.
    """
    matching = sorted(
        (
            h
            for h in request.history
            if h.context == request.context and h.performed_on < request.evaluation_date
        ),
        key=lambda h: h.performed_on,
    )
    cutoff = request.evaluation_date - timedelta(days=42)
    recent = [h for h in matching if h.performed_on >= cutoff]
    history = tuple(recent[-3:] if recent else matching[-1:])
    return _Evaluation(request, history, provisional=bool(matching and not recent)).run()
