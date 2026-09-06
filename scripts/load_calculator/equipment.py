"""Equipment operations on confirmed options, without generic increments."""

from itertools import pairwise

from scripts.load_calculator.models import Equipment, LoadOption


def dumbbell_equipment() -> Equipment:
    """Build the Athlete's interchangeable dumbbell inventory.

    Returns:
        Equipment: Sorted union, recorded as kilograms per dumbbell.
    """
    weights = sorted({*range(1, 11), *(5 + 2.5 * i for i in range(7)), *range(6, 51, 2)})
    return Equipment(
        setup_id="dumbbells",
        recording_convention="kg per dumbbell",
        options=tuple(LoadOption(label=f"{w:g} kg", weight_kg=w) for w in weights),
        steps=tuple(pairwise(weights)),
        inventory_complete=True,
    )


def canonical_load(equipment: Equipment, recorded: float | None) -> float | None:
    """Resolve a recorded load only through explicit options and aliases.

    Args:
        equipment (Equipment): Confirmed inventory and recording mappings.
        recorded (float | None): Historical recorded kilograms.

    Returns:
        float | None: Canonical recorded kilograms, or unknown.
    """
    return next(
        (
            o.weight_kg
            for o in equipment.options
            if recorded in (o.weight_kg, *o.recorded_aliases_kg)
        ),
        None,
    )


def step(equipment: Equipment, weight: float | None, *, increase: bool) -> float | None:
    """Select a confirmed next or previous equipment step.

    Args:
        equipment (Equipment): Confirmed inventory and adjacency.
        weight (float | None): Canonical recorded kilograms, or unknown.
        increase (bool): Whether to move upward.

    Returns:
        float | None: Adjacent load, or unknown at an unconfirmed boundary.
    """
    return next(
        (
            high if increase else low
            for low, high in equipment.steps
            if (low if increase else high) == weight
        ),
        None,
    )


def round_down(equipment: Equipment, estimate_kg: float) -> float | None:
    """Floor an externally supplied estimate to a known equipment option.

    Args:
        equipment (Equipment): Confirmed load options.
        estimate_kg (float): Unrounded estimate; this function supplies no model.

    Returns:
        float | None: Greatest known option below the estimate, or no option.
    """
    return next(
        (o.weight_kg for o in reversed(equipment.options) if o.weight_kg <= estimate_kg),
        None,
    )
