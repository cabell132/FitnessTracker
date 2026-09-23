"""Body composition calculation from weight, height, age, sex, and impedance.

Formulas adapted from the unofficial ``etekcity_esf551_ble`` scale library
(https://github.com/ronnnnnnnnnnnnn/etekcity_esf551_ble).

All private helpers accept a ``sex`` parameter as an ``int`` index
(0 = male, 1 = female) used to look up gender-specific constants.
"""

from __future__ import annotations

from math import floor
from typing import TYPE_CHECKING

from fitness_tracker.apis.vesync._health_score import metabolic_age as _metabolic_age
from fitness_tracker.apis.vesync.models.body_composition import BodyComposition

if TYPE_CHECKING:
    from fitness_tracker.apis.vesync.models.weight import WeightMeasurement

# Gender-indexed constants: (male, female)
_AGE_FACTOR = (0.103, 0.097)
_BMI_FACTOR = (1.524, 1.545)
_BFP_CONSTANT = (22.0, 12.7)
_FFW_FACTOR = (0.05, 0.06)
_WATER_FACTOR = (0.76, 0.73)
_SKEL_FACTOR = (0.68, 0.62)
_PROTEIN_BFP_FACTOR = (1.0, 1.05)
_VF_BMI_FACTOR = (0.8666, 0.8895)
_VF_BFP_FACTOR = (0.0082, 0.0943)
_VF_FAT_FACTOR = (0.026, -0.0534)
_VF_CONSTANT = (14.2692, 16.215)
_SF_BFP_FACTOR = (0.965, 0.983)
_SF_VFV_FACTOR = (0.22, 0.303)

# VeSync API gender codes → sex index
_GENDER_MAP: dict[str, int] = {"2": 0, "1": 1}


def _bmi(weight_kg: float, height_cm: float) -> float:
    """Calculate Body Mass Index.

    Args:
        weight_kg (float): Weight in kilograms.
        height_cm (float): Height in centimetres.

    Returns:
        float: BMI value truncated to two decimal places.
    """
    height_m = height_cm / 100.0
    return floor(weight_kg / (height_m**2) * 100) / 100


def _body_fat_pct(  # noqa: PLR0913 - formula inputs are independent measurements
    age: int, bmi: float, impedance: float, sex: int, *, athlete: bool
) -> float:
    """Calculate body fat percentage, clamped to 5-75.

    Args:
        age (int): Age in years.
        bmi (float): Body mass index.
        impedance (float): Bioelectrical impedance in ohms.
        sex (int): Sex index (0=male, 1=female).
        athlete (bool): Whether to apply the athlete-mode adjustment.

    Returns:
        float: Body fat percentage.
    """
    bfp = _AGE_FACTOR[sex] * age + _BMI_FACTOR[sex] * bmi - 500 / impedance - _BFP_CONSTANT[sex]
    if athlete:
        bfp = bfp / (3.5, 3.0)[sex] + bmi / (3.0, 2.4)[sex]
    bfp = floor(bfp * 10) / 10
    return max(5.0, min(75.0, bfp))


def _fat_free_weight(weight_kg: float, body_fat_pct: float) -> float:
    """Calculate fat-free weight.

    Args:
        weight_kg (float): Weight in kilograms.
        body_fat_pct (float): Body fat percentage.

    Returns:
        float: Fat-free weight in kilograms.
    """
    return round(weight_kg * (1 - body_fat_pct / 100), 2)


def _bone_mass(ffw: float, sex: int) -> float:
    """Calculate bone mass, minimum 1.0 kg.

    Args:
        ffw (float): Fat-free weight in kilograms.
        sex (int): Sex index (0=male, 1=female).

    Returns:
        float: Bone mass in kilograms.
    """
    return max(1.0, round(_FFW_FACTOR[sex] * ffw, 2))


def _muscle_mass(ffw: float, sex: int) -> float:
    """Calculate muscle mass.

    Args:
        ffw (float): Fat-free weight in kilograms.
        sex (int): Sex index (0=male, 1=female).

    Returns:
        float: Muscle mass in kilograms.
    """
    ff = max(1.0, _FFW_FACTOR[sex] * ffw)
    return round(ffw - ff, 2)


def _body_water_pct(ffw: float, weight_kg: float, sex: int) -> float:
    """Calculate body water percentage, clamped to 10-80.

    Args:
        ffw (float): Fat-free weight in kilograms.
        weight_kg (float): Total weight in kilograms.
        sex (int): Sex index (0=male, 1=female).

    Returns:
        float: Body water percentage.
    """
    ff1 = max(1.0, _FFW_FACTOR[sex] * ffw)
    bwp = round(_WATER_FACTOR[sex] * (ffw - ff1) / weight_kg * 100, 1)
    return max(10.0, min(80.0, bwp))


def _visceral_fat(bmi: float, bfp: float, fat_kg: float, sex: int) -> int:  # noqa: PLR0913
    """Calculate visceral fat level, clamped to 1-30.

    Args:
        bmi (float): Body mass index.
        bfp (float): Body fat percentage.
        fat_kg (float): Fat mass in kilograms (weight minus FFW).
        sex (int): Sex index (0=male, 1=female).

    Returns:
        int: Visceral fat level.
    """
    vfv = int(
        _VF_BMI_FACTOR[sex] * bmi
        + _VF_BFP_FACTOR[sex] * bfp
        + _VF_FAT_FACTOR[sex] * fat_kg
        - _VF_CONSTANT[sex]
    )
    return max(1, min(30, vfv))


def _subcutaneous_fat_pct(bfp: float, vfv: int, sex: int) -> float:
    """Calculate subcutaneous fat percentage.

    Args:
        bfp (float): Body fat percentage.
        vfv (int): Visceral fat level.
        sex (int): Sex index (0=male, 1=female).

    Returns:
        float: Subcutaneous fat percentage.
    """
    return round(_SF_BFP_FACTOR[sex] * bfp - _SF_VFV_FACTOR[sex] * vfv, 1)


def _bmr(ffw: float) -> int:
    """Calculate basal metabolic rate (Cunningham equation), clamped to 900-2500 kcal.

    Args:
        ffw (float): Fat-free weight in kilograms.

    Returns:
        int: Basal metabolic rate in kcal.
    """
    return max(900, min(2500, int(ffw * 21.6 + 370)))


def _skeletal_muscle_pct(ffw: float, weight_kg: float, sex: int) -> float:
    """Calculate skeletal muscle percentage.

    Args:
        ffw (float): Fat-free weight in kilograms.
        weight_kg (float): Total weight in kilograms.
        sex (int): Sex index (0=male, 1=female).

    Returns:
        float: Skeletal muscle percentage.
    """
    ff1 = max(1.0, _FFW_FACTOR[sex] * ffw)
    return round(_SKEL_FACTOR[sex] * (ffw - ff1) / weight_kg * 100, 1)


def _protein_pct(  # noqa: PLR0913 - formula inputs are independent measurements
    bfp: float, bone_mass: float, weight_kg: float, water_pct: float, sex: int
) -> float:
    """Calculate protein percentage, minimum 5.

    Args:
        bfp (float): Body fat percentage.
        bone_mass (float): Bone mass in kilograms.
        weight_kg (float): Total weight in kilograms.
        water_pct (float): Body water percentage.
        sex (int): Sex index (0=male, 1=female).

    Returns:
        float: Protein percentage.
    """
    bpp = round(
        100 - _PROTEIN_BFP_FACTOR[sex] * bfp - bone_mass / weight_kg * 100 - water_pct,
        1,
    )
    return max(5.0, bpp)


def calculate(measurement: WeightMeasurement, *, athlete: bool = False) -> BodyComposition | None:
    """Compute body composition from a weight measurement.

    Returns ``None`` when impedance, height, or age are missing/zero.

    Args:
        measurement (WeightMeasurement): A weight measurement with profile data.
        athlete (bool): Whether to apply the athlete-mode adjustment.

    Returns:
        BodyComposition | None: Computed body composition, or ``None``.
    """
    if not measurement.impedance or not measurement.height_cm or not measurement.age:
        return None

    sex = _GENDER_MAP.get(measurement.gender)
    if sex is None:
        return None

    bmi = _bmi(measurement.weight_kg, measurement.height_cm)
    bfp = _body_fat_pct(measurement.age, bmi, measurement.impedance, sex, athlete=athlete)
    ffw = _fat_free_weight(measurement.weight_kg, bfp)
    fat_kg = measurement.weight_kg - ffw
    bone = _bone_mass(ffw, sex)
    muscle = _muscle_mass(ffw, sex)
    water = _body_water_pct(ffw, measurement.weight_kg, sex)
    vf = _visceral_fat(bmi, bfp, fat_kg, sex)
    sf = _subcutaneous_fat_pct(bfp, vf, sex)
    bmr_val = _bmr(ffw)
    skel = _skeletal_muscle_pct(ffw, measurement.weight_kg, sex)
    protein = _protein_pct(bfp, bone, measurement.weight_kg, water, sex)
    met_age = _metabolic_age(
        measurement.weight_kg,
        measurement.height_cm,
        bfp,
        bmi,
        measurement.age,
        sex,
    )

    return BodyComposition(
        bmi=bmi,
        body_fat_pct=bfp,
        fat_free_weight_kg=ffw,
        muscle_mass_kg=muscle,
        bone_mass_kg=bone,
        body_water_pct=water,
        visceral_fat=vf,
        subcutaneous_fat_pct=sf,
        bmr=bmr_val,
        skeletal_muscle_pct=skel,
        protein_pct=protein,
        metabolic_age=met_age,
    )
