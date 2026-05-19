from __future__ import annotations

from fitness_tracker.sync_review.split_circuit.core import (
    SplitCircuitExerciseNoteContext,
    SplitCircuitPrescription,
    SplitCircuitTemplateRef,
    SplitCircuitTemplateRequirement,
    plan_prescription_split_circuit,
    render_split_circuit_exercise_notes,
)


def test_split_circuit_core_plans_resolved_round_circuit_without_request_objects() -> None:
    plan = plan_prescription_split_circuit(
        prescription=SplitCircuitPrescription(
            name="3 Rounds of:",
            text="""
            10 Burpees
            Plank 30s
            Rest 15s between each exercise and 60s between each round
            """,
        ),
        resolve_template=lambda name, source_text: (
            SplitCircuitTemplateRef(
                id=f"hevy-{name.casefold().replace(' ', '-')}",
                name=name,
                type="reps",
                equipment="bodyweight",
            ),
            [],
        ),
    )

    assert plan is not None
    assert plan.kind == "circuit"
    assert plan.round_count == 3
    assert plan.grouping_intent.inherit_superset_context is False
    assert plan.grouping_intent.numeric_superset_id is None
    assert [exercise.name for exercise in plan.exercises] == ["Burpees", "Plank"]
    assert [exercise.set_rows for exercise in plan.exercises] == [
        [{"type": "normal", "reps": 10}],
        [{"type": "normal", "duration_seconds": 30}],
    ]
    assert [exercise.selected_template.id for exercise in plan.exercises] == [
        "hevy-burpees",
        "hevy-plank",
    ]
    assert plan.rests[0].durations_seconds == [15, 60]
    assert all(not exercise.blockers for exercise in plan.exercises)


def test_split_circuit_core_treats_body_round_count_line_as_metadata() -> None:
    plan = plan_prescription_split_circuit(
        prescription=SplitCircuitPrescription(
            name="Conditioning Circuit",
            text="""
            3 Rounds
            10 Burpees
            Plank 30s
            """,
        ),
        resolve_template=lambda name, source_text: (
            SplitCircuitTemplateRef(
                id=f"hevy-{name.casefold().replace(' ', '-')}",
                name=name,
                type="reps",
                equipment="bodyweight",
            ),
            [],
        ),
    )

    assert plan is not None
    assert plan.round_count == 3
    assert [exercise.name for exercise in plan.exercises] == ["Burpees", "Plank"]


def test_split_circuit_core_plans_multi_exercise_amrap() -> None:
    plan = plan_prescription_split_circuit(
        prescription=SplitCircuitPrescription(
            name="12 min AMRAP",
            text="""
            Bike 500m
            10 Burpees
            """,
        ),
        resolve_template=lambda name, source_text: (
            SplitCircuitTemplateRef(
                id=f"hevy-{name.casefold().replace(' ', '-')}",
                name=name,
                type="reps",
                equipment="bodyweight",
            ),
            [],
        ),
    )

    assert plan is not None
    assert plan.kind == "amrap"
    assert plan.amrap_time_cap_seconds == 720
    assert [exercise.set_rows for exercise in plan.exercises] == [
        [{"type": "normal", "distance_meters": 500}],
        [{"type": "normal", "reps": 10}],
    ]


def test_split_circuit_core_does_not_plan_single_exercise_blocks() -> None:
    assert (
        plan_prescription_split_circuit(
            prescription=SplitCircuitPrescription(name="3 Round Circuit", text="10 Push Ups"),
            resolve_template=lambda name, source_text: (None, []),
        )
        is None
    )
    assert (
        plan_prescription_split_circuit(
            prescription=SplitCircuitPrescription(name="8 min AMRAP", text="10 Push Ups"),
            resolve_template=lambda name, source_text: (None, []),
        )
        is None
    )


def test_split_circuit_core_carries_template_blockers() -> None:
    requirement = SplitCircuitTemplateRequirement(
        title="Single-Leg Isometric Calf Raise",
        expected_type="duration",
        equipment_category="bodyweight",
        muscle_group="calves",
        other_muscles=(),
        status="missing",
        matching_template_ids=(),
    )

    plan = plan_prescription_split_circuit(
        prescription=SplitCircuitPrescription(
            name="Circuit",
            text="""
            Bodyweight Calf Raise 20s
            10 Push Ups
            """,
        ),
        resolve_template=lambda name, source_text: (
            (None, [requirement])
            if name == "Bodyweight Calf Raise"
            else (
                SplitCircuitTemplateRef(
                    id="hevy-push-up",
                    name="Push Ups",
                    type="reps",
                    equipment="bodyweight",
                ),
                [],
            )
        ),
    )

    assert plan is not None
    assert plan.exercises[0].template_requirements == (requirement,)
    assert plan.exercises[0].blockers == (
        "Missing required Hevy exercise mapping: Bodyweight Calf Raise",
        "Missing required Hevy template: Single-Leg Isometric Calf Raise",
    )


def test_split_circuit_core_allows_useful_notes_only_generated_exercises() -> None:
    plan = plan_prescription_split_circuit(
        prescription=SplitCircuitPrescription(
            name="Circuit",
            text="""
            15 cals Bike
            Broad Jumps
            """,
        ),
        resolve_template=lambda name, source_text: (
            SplitCircuitTemplateRef(
                id=f"hevy-{name.casefold().replace(' ', '-')}",
                name=name,
                type="reps",
                equipment="bodyweight",
            ),
            [],
        ),
    )

    assert plan is not None
    assert [exercise.set_rows for exercise in plan.exercises] == [[], []]
    assert [exercise.notes_only for exercise in plan.exercises] == [True, False]
    assert plan.exercises[0].warnings == ("No deterministic set parser result found.",)
    assert plan.exercises[0].blockers == ()
    assert plan.exercises[1].blockers == (
        "Generated Circuit exercise has no deterministic sets or target details: Broad Jumps",
    )


def test_split_circuit_core_records_inherited_grouping_intent_without_numeric_id() -> None:
    plan = plan_prescription_split_circuit(
        prescription=SplitCircuitPrescription(
            name="Circuit",
            text="""
            10 Burpees
            30s Plank
            """,
            inherit_superset_context=True,
        ),
        resolve_template=lambda name, source_text: (
            SplitCircuitTemplateRef(
                id=f"hevy-{name.casefold().replace(' ', '-')}",
                name=name,
                type="reps",
                equipment="bodyweight",
            ),
            [],
        ),
    )

    assert plan is not None
    assert plan.grouping_intent.inherit_superset_context is True
    assert plan.grouping_intent.numeric_superset_id is None


def test_split_circuit_core_renders_generated_exercise_notes() -> None:
    plan = plan_prescription_split_circuit(
        prescription=SplitCircuitPrescription(
            name="3 Round Circuit",
            text=("10 Burpees\nPlank 30s\nRest 15s between exercises and 60s between rounds"),
        ),
        resolve_template=lambda name, source_text: (
            SplitCircuitTemplateRef(
                id=f"hevy-{name.casefold().replace(' ', '-')}",
                name=name,
                type="reps",
                equipment="bodyweight",
            ),
            [],
        ),
    )

    assert plan is not None
    notes = render_split_circuit_exercise_notes(
        SplitCircuitExerciseNoteContext(
            exercise=plan.exercises[0],
            plan=plan,
            source_text=plan.original_source_text,
            round_count_label="Prescribed rounds",
            extra_lines=("Completed round times: 2 min 10 sec; 2 min 15 sec",),
        )
    )

    assert notes == (
        "10 Burpees\n"
        "Movement: Burpees\n"
        "Movement target: 10\n"
        "Prescribed rounds: 3\n"
        "Completed round times: 2 min 10 sec; 2 min 15 sec\n"
        "Rest lines: Rest 15s between exercises and 60s between rounds\n"
        "Source: 10 Burpees\n"
        "Plank 30s\n"
        "Rest 15s between exercises and 60s between rounds"
    )
