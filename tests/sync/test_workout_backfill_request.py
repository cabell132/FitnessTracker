from __future__ import annotations

from fitness_tracker.sync_review.workout_backfill_request import (
    WorkoutBackfillApplyValidationContext,
    build_hevy_workout_backfill_request,
    build_workout_backfill_decision_template,
    validate_workout_backfill_decisions,
    workout_backfill_apply_blockers,
)


def test_workout_backfill_request_uses_decisions_and_allocates_expanded_supersets() -> None:
    plan = {
        "workout": {
            "id": 455045484,
            "title": "Upper",
            "due": "2024-04-10T00:00:00",
        },
        "items": [
            {
                "source_id": 8101,
                "tracker_workout_item_id": 1,
                "position": 1,
                "superset_id": 0,
                "name": "Bench Press",
                "selected_hevy_template": {"id": "hevy-bench"},
                "sets": [{"type": "normal", "weight_kg": 80.0, "reps": 8}],
                "notes": "",
                "blockers": [],
            },
            {
                "source_id": 8106,
                "tracker_workout_item_id": 3,
                "position": 3,
                "superset_id": None,
                "name": "Burpees",
                "selected_hevy_template": {"id": "hevy-burpees"},
                "sets": [{"type": "normal", "reps": 10}],
                "notes": "Round 1",
                "blockers": [],
                "movement_target": "10 Burpees",
                "original_prescription_text": "2 Rounds\n10 Burpees\nPlank 30s",
                "completed_round_count": 2,
            },
            {
                "source_id": 8106,
                "tracker_workout_item_id": 3,
                "position": 3,
                "superset_id": None,
                "name": "Plank",
                "selected_hevy_template": None,
                "sets": [{"type": "normal", "duration_seconds": 30}],
                "notes": "Round 1",
                "blockers": ["Missing Hevy template mapping for Circuit Workout Item 8106: Plank"],
                "movement_target": "Plank 30s",
                "original_prescription_text": "2 Rounds\n10 Burpees\nPlank 30s",
                "completed_round_count": 2,
                "circuit_template_candidates": ["hevy-plank"],
                "circuit_decision_reason": "missing_template",
            },
        ],
    }
    decisions = build_workout_backfill_decision_template(455045484, plan)
    decisions["workout"]["selected_start_time"] = "2024-04-10T17:05:00Z"
    decisions["workout"]["selected_end_time"] = "2024-04-10T18:02:00Z"
    decisions["circuit_items"][0]["selected_hevy_template_id"] = "hevy-plank"

    validation = validate_workout_backfill_decisions(455045484, decisions, plan)
    request = build_hevy_workout_backfill_request(plan, decisions)

    assert validation == {"blockers": [], "warnings": []}
    assert request.workout.start_time == "2024-04-10T17:05:00Z"
    assert request.workout.end_time == "2024-04-10T18:02:00Z"
    assert [exercise.exercise_template_id for exercise in request.workout.exercises] == [
        "hevy-bench",
        "hevy-burpees",
        "hevy-plank",
    ]
    assert [exercise.superset_id for exercise in request.workout.exercises] == [0, 1, 1]
    assert (
        workout_backfill_apply_blockers(
            WorkoutBackfillApplyValidationContext(
                plan=plan,
                decision_validation=validation,
                request_body=request,
                decisions=decisions,
            )
        )
        == []
    )
