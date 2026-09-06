"""Equipment inventory and malformed-input boundary checks."""

import pytest
from pydantic import ValidationError

from scripts.load_calculator import Calculation, Equipment, dumbbell_equipment, round_down


def test_dumbbell_collections_form_one_sorted_union():
    weights = [o.weight_kg for o in dumbbell_equipment().options]
    expected = sorted({*range(1, 11), *(i / 2 for i in range(10, 41, 5)), *range(6, 51, 2)})
    assert weights == expected
    assert weights.count(10) == 1


@pytest.mark.parametrize(("estimate", "expected"), [(15.7, 15), (14.5, 14), (0.5, None), (50, 50)])
def test_new_estimate_rounds_down_without_using_proven_load_progression(estimate, expected):
    assert round_down(dumbbell_equipment(), estimate) == expected


def test_alias_conflicts_are_rejected():
    data = dumbbell_equipment().model_dump()
    data["options"][0]["recorded_aliases_kg"] = (2,)
    with pytest.raises(ValidationError, match="unambiguous"):
        Equipment.model_validate(data)


def test_steps_cannot_skip_a_known_option():
    data = dumbbell_equipment().model_dump()
    data["steps"] = ((14, 16),)
    with pytest.raises(ValidationError, match="adjacent"):
        Equipment.model_validate(data)


def test_empty_inventory_cannot_round_an_estimate():
    equipment = Equipment(setup_id="unknown", recording_convention="kg", options=())
    assert round_down(equipment, 20) is None


def test_input_schema_preserves_context_and_rejects_unknown_fields():
    schema = Calculation.model_json_schema()
    assert schema["additionalProperties"] is False
    assert "preceding_context" in schema["properties"]
