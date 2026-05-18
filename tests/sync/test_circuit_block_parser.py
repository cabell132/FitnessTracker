"""Tests for Coach-authored Circuit and AMRAP block parsing."""

from fitness_tracker.sync._circuit_block_parser import parse_circuit_block


def test_parse_circuit_block_extracts_rounds_movements_and_rest_metadata() -> None:
    block = parse_circuit_block(
        name="3 Rounds of:",
        text="""
        - 10 DB Thrusters
        - 12 push ups ES
        - Row Erg 300m
        - Rest 15s between each exercise and 2min between each round
        """,
    )

    assert block is not None
    assert block.kind == "circuit"
    assert block.round_count == 3
    assert block.amrap_time_cap_seconds is None
    assert block.requires_agent_decision is False
    assert [movement.name for movement in block.movements] == [
        "DB Thrusters",
        "push ups",
        "Row Erg",
    ]
    assert [movement.target for movement in block.movements] == ["10", "12 ES", "300m"]
    assert [rest.source_text for rest in block.rests] == [
        "Rest 15s between each exercise and 2min between each round"
    ]
    assert block.rests[0].durations_seconds == [15, 120]


def test_parse_amrap_block_extracts_time_cap_and_numbered_movements() -> None:
    block = parse_circuit_block(
        name="14' AMRAP",
        text="""
        1. 20 cal Bike
        2. 10 Burpees
        3. 2min rest
        """,
    )

    assert block is not None
    assert block.kind == "amrap"
    assert block.round_count is None
    assert block.amrap_time_cap_seconds == 14 * 60
    assert [movement.name for movement in block.movements] == ["Bike", "Burpees"]
    assert [movement.target for movement in block.movements] == ["20 cal", "10"]
    assert block.rests[0].durations_seconds == [120]


def test_parse_active_recovery_block_preserves_duration_distance_and_lengths() -> None:
    block = parse_circuit_block(
        name="Active Recovery Circuit",
        text="""
        Bike 3min easy
        Bear crawl 2 lengths
        Farmer carry 40m each side
        60s rest
        """,
    )

    assert block is not None
    assert [movement.source_text for movement in block.movements] == [
        "Bike 3min easy",
        "Bear crawl 2 lengths",
        "Farmer carry 40m each side",
    ]
    assert [movement.target for movement in block.movements] == [
        "3min easy",
        "2 lengths",
        "40m each side",
    ]
    assert block.rests[0].source_text == "60s rest"


def test_parse_round_specific_rep_ladder_requires_agent_decision() -> None:
    block = parse_circuit_block(
        name="3 Round Circuit",
        text="""
        Goblet Squat
        Push Up
        Round 1: 12 reps
        Round 2: 10 reps
        Round 3: 8 reps
        """,
    )

    assert block is not None
    assert block.round_count == 3
    assert block.requires_agent_decision is True
    assert block.agent_decision_reason == "round_specific_rep_ladder"
    assert [movement.name for movement in block.movements] == ["Goblet Squat", "Push Up"]
    assert [line.source_text for line in block.metadata_lines] == [
        "Round 1: 12 reps",
        "Round 2: 10 reps",
        "Round 3: 8 reps",
    ]
