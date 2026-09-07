"""Executable examples for the experimental load calculator."""

from copy import deepcopy

import pytest

from scripts.load_calculator import Calculation, calculate, dumbbell_equipment


def request(reps=(10, 10, 10), weight=14):
    efforts = [{"round": i, "part": 0, "lower_reps": 8, "upper_reps": 10} for i in range(3)]
    context = {
        "exercise_id": "db-press",
        "setup_id": "dumbbells",
        "role": "working",
        "execution": "bilateral; controlled tempo; per hand",
    }
    prescription = {"structure": "straight", "efforts": efforts}
    return {
        "evaluation_date": "2026-09-06",
        "context": context,
        "prescription": prescription,
        "equipment": dumbbell_equipment().model_dump(mode="json"),
        "history": [
            {
                "evidence_id": "workout-1/item-1",
                "performed_on": "2026-09-01",
                "context": context,
                "prescription": prescription,
                "conditions": "normal",
                "results": [
                    {"round": i, "part": 0, "reps": r, "recorded_kg": weight}
                    for i, r in enumerate(reps)
                ],
            }
        ],
    }


def test_completed_upper_bounds_progress_to_next_union_option():
    result = calculate(Calculation.model_validate(request()))

    assert [effort.weight_kg for effort in result.efforts] == [15, 15, 15]
    assert result.reason == "progress"
    assert result.evidence_ids == ("workout-1/item-1",)
    assert result.provisional is False


@pytest.mark.parametrize("reps", [(8, 8, 8), (10, 9, 7), (7, 6, 5), (10, 7, 5)])
def test_single_exposure_holds_until_progression_or_repeated_shortfall(reps):
    result = calculate(Calculation.model_validate(request(reps)))
    assert result.reason == "hold"
    assert [e.weight_kg for e in result.efforts] == [14] * 3


def add_previous(data, *, reps=(10, 10, 10), date="2026-08-25"):
    previous = deepcopy(data["history"][-1])
    previous.update(evidence_id=f"previous-{date}", performed_on=date)
    for result, value in zip(previous["results"], reps, strict=True):
        result.update(reps=value, recorded_kg=14)
    data["history"].insert(0, previous)
    return previous


def test_two_consecutive_substantial_shortfalls_reduce_one_step():
    data = request((10, 7, 5))
    add_previous(data, reps=(7, 6, 5))
    result = calculate(Calculation.model_validate(data))
    assert result.reason == "reduce"
    assert [e.weight_kg for e in result.efforts] == [12.5] * 3


def test_failed_new_increase_rolls_back_immediately():
    data = request((7, 6, 5), weight=15)
    add_previous(data)
    result = calculate(Calculation.model_validate(data))
    assert result.reason == "rollback"
    assert [e.weight_kg for e in result.efforts] == [14] * 3


def test_minor_shortfall_at_new_load_holds():
    data = request((10, 9, 7), weight=15)
    add_previous(data)
    assert calculate(Calculation.model_validate(data)).reason == "hold"


def test_interruption_between_failures_breaks_consecutive_failure_rule():
    data = request((7, 6, 5))
    add_previous(data, reps=(7, 6, 5), date="2026-08-18")
    interrupted = add_previous(data, date="2026-08-25")
    interrupted["conditions"] = "interrupted"
    assert calculate(Calculation.model_validate(data)).reason == "hold"


@pytest.mark.parametrize("condition", ["unknown", "interrupted", "substitution"])
def test_latest_uncertain_exposure_does_not_prove_inability(condition):
    data = request((7, 6, 5))
    data["history"][-1]["conditions"] = condition
    result = calculate(Calculation.model_validate(data))
    assert result.reason == "unresolved"
    assert all(e.weight_kg is None for e in result.efforts)


def test_missing_effort_is_unresolved_rather_than_a_shortfall():
    data = request()
    data["history"][-1]["results"].pop()
    result = calculate(Calculation.model_validate(data))
    assert "incomplete_or_reordered_results" in result.unresolved[0]


def test_recent_changed_prescription_wins_over_old_exact_match():
    data = request()
    add_previous(data, date="2026-06-01")
    latest = data["history"][-1]
    latest["prescription"] = deepcopy(latest["prescription"])
    latest["prescription"]["efforts"].pop()
    latest["results"].pop()
    result = calculate(Calculation.model_validate(data))
    assert result.unresolved == ("changed_prescription_model_unvalidated",)
    assert result.evidence_ids == ("workout-1/item-1",)


def test_stale_same_prescription_is_provisional_and_does_not_progress():
    data = request()
    data["history"][-1]["performed_on"] = "2026-06-01"
    result = calculate(Calculation.model_validate(data))
    assert result.provisional is True
    assert result.reason == "stale"
    assert [e.weight_kg for e in result.efforts] == [14] * 3


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("exercise_id", "different-exercise"),
        ("setup_id", "other-station"),
        ("role", "preparatory"),
        ("execution", "single arm; per hand"),
    ],
)
def test_other_exercise_setup_role_or_execution_cannot_supply_strength(field, value):
    data = request()
    data["history"][-1]["context"] = {**data["context"], field: value}
    assert calculate(Calculation.model_validate(data)).evidence_ids == ()


def test_history_is_limited_to_three_prior_date_exposures_within_six_weeks():
    data = request()
    for date in ["2026-07-25", "2026-07-26", "2026-08-01", "2026-09-06", "2026-09-07"]:
        add_previous(data, date=date)
    result = calculate(Calculation.model_validate(data))
    assert result.evidence_ids == ("previous-2026-07-26", "previous-2026-08-01", "workout-1/item-1")


def test_no_history_is_explicitly_unresolved():
    data = request()
    data["history"] = []
    assert calculate(Calculation.model_validate(data)).reason == "unresolved"


def test_explicit_coach_loads_survive_without_history_or_equipment_match():
    data = request()
    data["history"] = []
    for effort in data["prescription"]["efforts"]:
        effort["coach_load_kg"] = 13.25
    result = calculate(Calculation.model_validate(data))
    assert result.reason == "coach"
    assert [e.weight_kg for e in result.efforts] == [13.25] * 3
    assert all(e.source == "coach" for e in result.efforts)


def test_partial_coach_load_does_not_silently_fill_other_efforts():
    data = request()
    data["prescription"]["efforts"][0]["coach_load_kg"] = 0
    result = calculate(Calculation.model_validate(data))
    assert [e.weight_kg for e in result.efforts] == [0, None, None]
    assert result.unresolved == ("partially_explicit_loads_require_review",)


def test_numeric_preparatory_ladder_preserves_per_effort_loads():
    data = request(reps=(15, 12, 10))
    data["context"]["role"] = "preparatory"
    data["prescription"]["structure"] = "ladder"
    for e, r, reps, weight in zip(
        data["prescription"]["efforts"],
        data["history"][-1]["results"],
        (15, 12, 10),
        (10, 12, 14),
        strict=True,
    ):
        e.update(lower_reps=reps, upper_reps=reps)
        r["recorded_kg"] = weight
    result = calculate(Calculation.model_validate(data))
    assert result.reason == "preparatory"
    assert [e.weight_kg for e in result.efforts] == [10, 12, 14]
    assert "preparatory_exposure_count" in result.unresolved[0]


def test_ladder_progression_remains_unresolved():
    data = request()
    data["prescription"]["structure"] = "ladder"
    result = calculate(Calculation.model_validate(data))
    assert result.unresolved == ("ladder_progression_policy_undecided",)
    assert [e.weight_kg for e in result.efforts] == [14] * 3


def test_open_ended_effort_remains_unresolved():
    data = request()
    data["prescription"]["efforts"][-1].update(lower_reps=None, upper_reps=None)
    result = calculate(Calculation.model_validate(data))
    assert result.reason == "unresolved"
    assert all(e.weight_kg is None for e in result.efforts)


def test_preceding_work_context_changes_no_numeric_adjustment():
    data = request()
    baseline = calculate(Calculation.model_validate(data))
    data["preceding_context"] = "Moved after three compound exercises; rest timer purpose unknown."
    result = calculate(Calculation.model_validate(data))
    assert result.efforts == baseline.efforts
    assert result.request.preceding_context == data["preceding_context"]


def drop_request(reps=(10, 10, 10, 10, 10, 10), profile=(24, 21.5)):
    data = request()
    data["context"]["setup_id"] = "narrow-cable"
    data["equipment"] = {
        "setup_id": "narrow-cable",
        "recording_convention": "kg on narrow station",
        "options": [{"label": f"{w} kg", "weight_kg": w} for w in (21.5, 24, 26)],
        "steps": [(21.5, 24), (24, 26)],
    }
    data["prescription"].update(
        structure="drop",
        efforts=[
            {"round": r, "part": p, "lower_reps": 10, "upper_reps": 10}
            for r in range(3)
            for p in range(2)
        ],
    )
    data["history"][-1]["results"] = [
        {"round": i // 2, "part": i % 2, "reps": r, "recorded_kg": profile[i % 2]}
        for i, r in enumerate(reps)
    ]
    return data


def test_completed_linked_drop_sequence_progresses_both_parts():
    result = calculate(Calculation.model_validate(drop_request()))
    assert result.reason == "progress"
    assert [e.weight_kg for e in result.efforts] == [26, 24] * 3


def test_incomplete_drop_does_not_progress_first_efforts():
    result = calculate(Calculation.model_validate(drop_request((10, 10, 10, 10, 10, 7))))
    assert result.reason == "hold"
    assert [e.weight_kg for e in result.efforts] == [24, 21.5] * 3


def test_failed_new_drop_increase_rolls_back_only_drop_and_then_retries_it():
    data = drop_request((10, 10, 10, 10, 10, 7), profile=(26, 24))
    old = deepcopy(drop_request()["history"][-1])
    old.update(performed_on="2026-08-25", evidence_id="original-success")
    data["history"].insert(0, old)
    rollback = calculate(Calculation.model_validate(data))
    assert rollback.reason == "rollback_drop"
    assert [e.weight_kg for e in rollback.efforts] == [26, 21.5] * 3

    completed = deepcopy(drop_request(profile=(26, 21.5))["history"][-1])
    completed.update(performed_on="2026-09-05", evidence_id="staged-success")
    data["history"].append(completed)
    retry = calculate(Calculation.model_validate(data))
    assert retry.reason == "retry_drop"
    assert [e.weight_kg for e in retry.efforts] == [26, 24] * 3


def test_unagreed_drop_failure_combination_is_unresolved():
    result = calculate(Calculation.model_validate(drop_request((7, 10, 10, 10, 10, 7))))
    assert result.unresolved == ("drop_failure_combination_undecided",)


def test_unknown_next_equipment_step_cannot_be_invented():
    data = request(weight=50)
    result = calculate(Calculation.model_validate(data))
    assert result.unresolved == ("equipment_step_unconfirmed",)


def test_explicit_recording_alias_is_not_a_strength_increase():
    data = request(reps=(8, 8, 8))
    option = next(o for o in data["equipment"]["options"] if o["weight_kg"] == 14)
    option["recorded_aliases_kg"] = [13.99]
    data["history"][-1]["results"][0]["recorded_kg"] = 13.99
    result = calculate(Calculation.model_validate(data))
    assert result.reason == "hold"
    assert [e.weight_kg for e in result.efforts] == [14] * 3


def test_preparatory_straight_sets_can_keep_separate_weights():
    data = request()
    data["context"]["role"] = "preparatory"
    for effort, weight in zip(data["history"][-1]["results"], (10, 12, 14), strict=True):
        effort["recorded_kg"] = weight
    result = calculate(Calculation.model_validate(data))
    assert result.reason == "preparatory"
    assert [e.weight_kg for e in result.efforts] == [10, 12, 14]


def test_optional_rpe_is_preserved_without_changing_the_recommendation():
    data = request()
    baseline = calculate(Calculation.model_validate(data))
    data["history"][-1]["results"][-1]["rpe"] = 6
    result = calculate(Calculation.model_validate(data))
    assert result.efforts == baseline.efforts
    assert result.request.history[-1].results[-1].rpe == 6


def test_staged_drop_without_original_increase_evidence_is_unresolved():
    data = drop_request(profile=(26, 21.5))
    prior = deepcopy(drop_request((10, 10, 10, 10, 10, 7), profile=(26, 24))["history"][-1])
    prior.update(performed_on="2026-08-25", evidence_id="failed-unknown-origin")
    data["history"].insert(0, prior)
    result = calculate(Calculation.model_validate(data))
    assert result.unresolved == ("staged_drop_origin_unresolved",)


def test_future_outcomes_cannot_change_recommendation_and_inputs_are_unchanged():
    data = request()
    before = deepcopy(data)
    baseline = calculate(Calculation.model_validate(data))
    assert data == before
    add_previous(data, reps=(0, 0, 0), date="2026-09-07")
    result = calculate(Calculation.model_validate(data))
    assert result.efforts == baseline.efforts
    assert result.evidence_ids == baseline.evidence_ids


def test_same_day_exposure_order_is_not_inferred():
    data = request()
    add_previous(data, date="2026-09-01")
    result = calculate(Calculation.model_validate(data))
    assert result.unresolved == ("same_date_exposure_order_unknown",)
