"""Unit tests for the consolidated True Coach HTML parsing module."""

import pytest

from fitness_tracker.sync._true_coach_html import (
    build_superset_index,
    extract_notes,
    fallback_sets,
    parse_workout_order,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal HTML fragments matching True Coach structure
# ---------------------------------------------------------------------------

SIMPLE_HTML = """
<p class="name-and-info">
A) Bench Press<br/>
B) Squat<br/>
C) Deadlift
</p>
"""

SUPERSET_HTML = """
<p class="name-and-info">
A1) Bench Press<br/>
A2) Incline DB Press<br/>
B) Squat<br/>
C1) RDL<br/>
C2) Leg Curl
</p>
"""

EMPTY_HTML = "<div>no workout elements</div>"


# ---------------------------------------------------------------------------
# parse_workout_order
# ---------------------------------------------------------------------------


def test_parse_workout_order_simple() -> None:
    order = parse_workout_order(SIMPLE_HTML)

    assert len(order) == 3
    assert order[1]["exercise_name"] == "Bench Press"
    assert order[1]["is_superset"] is False
    assert order[1]["superset_group"] is None


def test_parse_workout_order_superset_markers() -> None:
    order = parse_workout_order(SUPERSET_HTML)

    assert order[1]["is_superset"] is True
    assert order[1]["superset_group"] == "A"
    assert order[1]["superset_order"] == 1
    assert order[2]["superset_group"] == "A"
    assert order[2]["superset_order"] == 2

    assert order[3]["is_superset"] is False
    assert order[3]["superset_group"] is None


def test_parse_workout_order_raises_on_missing_structure() -> None:
    with pytest.raises(ValueError, match="No workout elements found"):
        parse_workout_order(EMPTY_HTML)


# ---------------------------------------------------------------------------
# build_superset_index
# ---------------------------------------------------------------------------


def test_build_superset_index_returns_none_for_no_supersets() -> None:
    order = parse_workout_order(SIMPLE_HTML)
    assert build_superset_index(order) is None


def test_build_superset_index_maps_groups() -> None:
    order = parse_workout_order(SUPERSET_HTML)
    index = build_superset_index(order)

    assert index is not None
    assert "A" in index
    assert "C" in index
    assert isinstance(index["A"], int)


def test_build_superset_index_empty_order() -> None:
    assert build_superset_index({}) is None


# ---------------------------------------------------------------------------
# extract_notes
# ---------------------------------------------------------------------------


def test_extract_notes_from_html() -> None:
    notes = extract_notes(SIMPLE_HTML)
    assert "Bench Press" in notes
    assert "Squat" in notes


def test_extract_notes_returns_empty_for_missing_block() -> None:
    assert extract_notes(EMPTY_HTML) == ""


# ---------------------------------------------------------------------------
# fallback_sets
# ---------------------------------------------------------------------------


def test_fallback_sets_returns_single_default() -> None:
    sets = fallback_sets("anything")
    assert len(sets) == 1
    assert sets[0].type == "normal"
    assert sets[0].duration_seconds == 60


def test_fallback_sets_uses_rep_range_upper_bound() -> None:
    sets = fallback_sets("3 x 10-12")

    assert [set_.model_dump(exclude_none=True) for set_ in sets] == [
        {"type": "normal", "reps": 12},
        {"type": "normal", "reps": 12},
        {"type": "normal", "reps": 12},
    ]


def test_fallback_sets_preserves_explicit_coach_load() -> None:
    sets = fallback_sets("3 x 12 @ 90kg")

    assert [set_.model_dump(exclude_none=True) for set_ in sets] == [
        {"type": "normal", "weight_kg": 90.0, "reps": 12},
        {"type": "normal", "weight_kg": 90.0, "reps": 12},
        {"type": "normal", "weight_kg": 90.0, "reps": 12},
    ]


def test_fallback_sets_parses_plus_notation_as_dropsets() -> None:
    sets = fallback_sets("3 x 10+10")

    assert [set_.model_dump(exclude_none=True) for set_ in sets] == [
        {"type": "normal", "reps": 10},
        {"type": "dropset", "reps": 10},
        {"type": "normal", "reps": 10},
        {"type": "dropset", "reps": 10},
        {"type": "normal", "reps": 10},
        {"type": "dropset", "reps": 10},
    ]


def test_fallback_sets_parses_greater_than_notation_as_dropsets() -> None:
    sets = fallback_sets("3 x 8>8>8")

    assert [set_.model_dump(exclude_none=True) for set_ in sets] == [
        {"type": "normal", "reps": 8},
        {"type": "dropset", "reps": 8},
        {"type": "dropset", "reps": 8},
        {"type": "normal", "reps": 8},
        {"type": "dropset", "reps": 8},
        {"type": "dropset", "reps": 8},
        {"type": "normal", "reps": 8},
        {"type": "dropset", "reps": 8},
        {"type": "dropset", "reps": 8},
    ]
