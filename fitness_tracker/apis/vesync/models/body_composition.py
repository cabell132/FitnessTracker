"""Body composition result model."""

from __future__ import annotations

from fitness_tracker.apis.vesync.models._base import VeSyncModel


class BodyComposition(VeSyncModel):
    """Body composition metrics derived from BIA (bioelectrical impedance analysis).

    All fields default to zero so partial results are still usable.
    """

    bmi: float = 0.0
    body_fat_pct: float = 0.0
    fat_free_weight_kg: float = 0.0
    muscle_mass_kg: float = 0.0
    bone_mass_kg: float = 0.0
    body_water_pct: float = 0.0
    visceral_fat: int = 0
    subcutaneous_fat_pct: float = 0.0
    bmr: int = 0
    skeletal_muscle_pct: float = 0.0
    protein_pct: float = 0.0
    metabolic_age: int = 0
